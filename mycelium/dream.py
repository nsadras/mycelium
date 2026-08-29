"""Offline consolidation from durable short-term claims into the canonical wiki."""

from __future__ import annotations

import uuid
from datetime import datetime

from mycelium.artifacts import (
    ArtifactStore,
    ClaimScopeDecision,
    DreamClaimDecision,
    DreamRunAudit,
    EntityRecord,
    MemoryClaim,
    NonWikiRetentionRecord,
    ScopeCohort,
    SourceDocument,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimEvidence, ClaimRouter, RoutingResult
from mycelium.consolidation import placement_from_route
from mycelium.facts import FactConsolidator
from mycelium.materialization import PageMaterializer
from mycelium.reconsolidation import ClaimReconsolidator, add_claim_link
from mycelium.short_term import ShortTermMemoryQueue
from mycelium.models import DreamReport, LogEntry
from mycelium.ollama import OllamaClient
from mycelium.store import LogStore, WikiStore


class DreamProcess:
    def __init__(
        self,
        llm: OllamaClient,
        wiki: WikiStore,
        logs: LogStore,
        config: Config,
        artifacts: ArtifactStore,
    ) -> None:
        self.llm = llm
        self.wiki = wiki
        self.logs = logs
        self.config = config
        self.artifacts = artifacts
        self.router = ClaimRouter(llm, artifacts)
        self.materializer = PageMaterializer(wiki, artifacts, config)
        self.reconsolidator = ClaimReconsolidator(llm, artifacts)
        self.fact_consolidator = FactConsolidator(llm, artifacts)
        self.short_term = ShortTermMemoryQueue(artifacts, config.dream)

    async def run(
        self, *, dry_run: bool = False, include_deferred: bool = False
    ) -> DreamReport:
        started_at = datetime.now().astimezone().isoformat()
        run_id = f"dream-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        queued_claims = self.short_term.claims_for_dream(
            include_deferred=include_deferred
        )
        incoming_claim_ids = {claim.claim_id for claim in queued_claims}
        queued_claims = self._initial_scope_claims(queued_claims)
        queued_claim_ids = {claim.claim_id for claim in queued_claims}
        queued_source_ids = {
            provenance.source_id
            for claim in queued_claims
            for provenance in claim.provenance
        }
        raw_entries = [
            entry
            for entry in self.logs.get_unconsolidated(days=None)
            if entry.durability == "durable" and entry.content.strip()
        ]
        raw_ids = {entry.entry_id for entry in raw_entries}
        sources = [
            source
            for source in self.artifacts.list_sources()
            if source.source_id in queued_source_ids
            or source.raw_log_entry_id in raw_ids
        ]
        sources_by_log = {
            source.raw_log_entry_id: source
            for source in sources
            if source.raw_log_entry_id
        }
        episodes_by_source = {
            episode.source_id: episode for episode in self.artifacts.list_episodes()
        }

        failures: list[dict[str, str]] = []
        failed_source_ids: set[str] = set()
        for entry in raw_entries:
            source = sources_by_log.get(entry.entry_id)
            if source is None:
                failed_source_ids.add(entry.entry_id)
                failures.append({
                    "stage": "preparation",
                    "source_id": entry.entry_id,
                    "reason": "No structured source artifact exists for this log entry",
                })
                continue
            episode = episodes_by_source.get(source.source_id)
            if (
                episode is None
                or episode.extraction_status == "failed"
                or (
                    episode.extraction_status == "partial"
                    and not episode.claim_ids
                )
            ):
                failed_source_ids.add(entry.entry_id)
                failures.append({
                    "stage": "extraction",
                    "source_id": entry.entry_id,
                    "reason": (
                        episode.extraction_error
                        if episode and episode.extraction_error
                        else "Claim extraction did not produce any routable claims"
                    ),
                })

        retention_records = self._retention_records(
            sources, queued_claim_ids, episodes_by_source
        )
        evidence, decisions = self._build_evidence(
            sources, queued_claim_ids, episodes_by_source, incoming_claim_ids
        )
        incoming_source_ids = {
            provenance.source_id
            for claim_id in incoming_claim_ids
            for provenance in self.artifacts.get_claim(claim_id).provenance
        }
        routing = await self.router.route(
            evidence,
            dream_run_id=run_id,
            participant_source_ids=incoming_source_ids,
        ) if evidence else None
        newly_materialized = [
            entity for entity in (routing.new_entities if routing is not None else [])
            if entity.materialization_state == "materialized"
        ]
        if newly_materialized:
            revision_claims = self._scope_revision_claims(
                queued_claims, newly_materialized
            )
            revision_claim_ids = {claim.claim_id for claim in revision_claims}
            revision_source_ids = {
                provenance.source_id
                for claim in revision_claims
                for provenance in claim.provenance
            }
            revision_sources = [
                source for source in self.artifacts.list_sources()
                if source.source_id in revision_source_ids
            ]
            revision_evidence, revision_decisions = self._build_evidence(
                revision_sources,
                revision_claim_ids,
                episodes_by_source,
                incoming_claim_ids,
            )
            initial_evidence_ids = {item.claim.claim_id for item in evidence}
            revision_routing = await self.router.route(
                revision_evidence,
                dream_run_id=run_id,
                seed_entities=(routing.new_entities if routing is not None else []),
                participant_source_ids=incoming_source_ids,
            ) if (
                revision_evidence
                and {item.claim.claim_id for item in revision_evidence}
                > initial_evidence_ids
            ) else None
            if revision_routing is not None:
                routing = self._merge_revision_routing(routing, revision_routing)
                evidence = revision_evidence
                decisions = revision_decisions
        if routing is not None:
            failed_claim_ids: set[str] = set()
            for failure in routing.failures:
                if failure.claim_id not in incoming_claim_ids:
                    continue
                failed_claim_ids.add(failure.claim_id)
                failures.append({
                    "stage": "routing",
                    "source_id": failure.raw_log_entry_id,
                    "reason": failure.reason,
                })
                self._set_decision(
                    decisions,
                    failure.claim_id,
                    "routing_failed",
                    failure.reason,
                )
            successful_routes = [
                route
                for route in routing.routes
                if route.claim_id not in failed_claim_ids
            ]
        else:
            successful_routes = []

        reconciliation = await self.reconsolidator.analyze(
            [route for route in successful_routes if route.placed],
            current_claim_ids=incoming_claim_ids,
            dream_run_id=run_id,
        ) if successful_routes else None
        if reconciliation is not None:
            recon_failed_claim_ids: set[str] = set()
            for recon_failure in reconciliation.failures:
                recon_failed_claim_ids.add(recon_failure.claim_id)
                failures.append({
                    "stage": "reconsolidation",
                    "source_id": recon_failure.raw_log_entry_id,
                    "reason": recon_failure.reason,
                })
                self._set_decision(
                    decisions,
                    recon_failure.claim_id,
                    "routing_failed",
                    recon_failure.reason,
                )
            successful_routes = [
                route for route in successful_routes
                if route.claim_id not in recon_failed_claim_ids
            ]
            successful_claim_ids = {route.claim_id for route in successful_routes}
            supporting_relations = [
                relation for relation in reconciliation.supporting_relations
                if relation.incoming_claim_id in successful_claim_ids
            ]
            proposals = [
                proposal for proposal in reconciliation.proposals
                if proposal.incoming_claim_id in successful_claim_ids
            ]
        else:
            supporting_relations = []
            proposals = []

        if not dry_run:
            for relation in supporting_relations:
                incoming = self.artifacts.get_claim(relation.incoming_claim_id)
                target = self.artifacts.get_claim(relation.target_claim_id)
                add_claim_link(incoming, "supports", target.claim_id)
                add_claim_link(target, "supported_by", incoming.claim_id)
                self.artifacts.save_claim(incoming)
                self.artifacts.save_claim(target)
            for proposal in proposals:
                self.artifacts.save_reconsolidation_proposal(proposal)

        retained_new_entities = list(
            routing.new_entities if routing is not None else []
        )
        materialized_entity_ids = {
            entity_id
            for route in successful_routes
            if route.placed
            for entity_id in [route.owner_entity_id, *route.linked_entity_ids]
            if entity_id
        } | {
            encounter.entity_id
            for encounter in (routing.encounters if routing is not None else [])
        }
        for entity in retained_new_entities:
            if (
                entity.materialization_state == "materialized"
                and entity.entity_id not in materialized_entity_ids
                and entity.entity_id != "you"
            ):
                entity.materialization_state = "provisional"
        placed_routes = [route for route in successful_routes if route.placed]
        affected_fact_entities = {
            route.owner_entity_id for route in placed_routes if route.owner_entity_id
        }
        pending_fact_claim_ids = (
            self.artifacts.pending_reconsolidation_claim_ids()
            | {
                claim_id for proposal in proposals
                for claim_id in (proposal.incoming_claim_id, proposal.target_claim_id)
            }
        )
        fact_result = await self.fact_consolidator.consolidate(
            [placement_from_route(route) for route in placed_routes],
            affected_entity_ids={
                value for value in affected_fact_entities if value is not None
            },
            pending_claim_ids=pending_fact_claim_ids,
        )
        materialized = self.materializer.stage(
            successful_routes,
            retained_new_entities,
            facts=fact_result.facts,
            deleted_fact_ids=fact_result.deleted_fact_ids,
        )
        routed_entities = {
            entity.entity_id: entity
            for entity in [
                *self.artifacts.list_entities(),
                *retained_new_entities,
            ]
        }
        for route in successful_routes:
            if route.placed:
                assert route.owner_entity_id is not None
                entity = routed_entities[route.owner_entity_id]
                self._set_decision(
                    decisions,
                    route.claim_id,
                    "routed",
                    f"Owned by {entity.entity_id} in {route.section_key}.",
                    page_slugs=[entity.slug],
                )
            else:
                self._set_decision(
                    decisions, route.claim_id, "deferred", route.reason
                )

        for decision in decisions.values():
            if decision.disposition == "pending":
                decision.disposition = "routing_failed"
                decision.reason = "No terminal routing decision was recorded."

        completed_source_ids = [
            entry.entry_id for entry in raw_entries if entry.entry_id not in failed_source_ids
        ]
        pending_source_ids = [
            entry.entry_id for entry in raw_entries if entry.entry_id in failed_source_ids
        ]

        if not dry_run:
            self.materializer.persist(materialized)
            for record in retention_records:
                self.artifacts.save_retention_record(record)
            for identity_decision in (
                routing.entity_decisions if routing is not None else []
            ):
                self.artifacts.save_entity_resolution_decision(identity_decision)
            for reference in (
                routing.entity_references if routing is not None else []
            ):
                self.artifacts.save_entity_reference(reference)
            retained_new_entity_ids = {
                entity.entity_id for entity in retained_new_entities
            }
            for encounter in (routing.encounters if routing is not None else []):
                if encounter.entity_id in retained_new_entity_ids or any(
                    entity.entity_id == encounter.entity_id
                    for entity in self.artifacts.list_entities()
                ):
                    self.artifacts.save_encounter(encounter)
            encounter_entity_ids = {
                encounter.entity_id
                for encounter in (routing.encounters if routing is not None else [])
            }
            if encounter_entity_ids:
                encounter_pages = self.materializer.regenerate(encounter_entity_ids | {"you"})
                materialized.changed_pages.update(encounter_pages.changed_pages)
                materialized.created_slugs.update(encounter_pages.created_slugs)
                materialized.updated_slugs.update(encounter_pages.updated_slugs)
                materialized.deleted_slugs.update(encounter_pages.deleted_slugs)
            now = datetime.now().astimezone().isoformat()
            for route in successful_routes:
                self.artifacts.save_scope_decision(ClaimScopeDecision(
                    decision_id=f"scope-{uuid.uuid4().hex[:12]}",
                    claim_id=route.claim_id,
                    owner_entity_id=route.owner_entity_id,
                    section_key=route.section_key,
                    linked_entity_ids=list(route.linked_entity_ids),
                    supporting_claim_ids=list(route.supporting_claim_ids),
                    confidence=route.confidence,
                    reason=route.reason,
                    origin="automatic",
                    dream_run_id=run_id,
                    status="active",
                    created_at=now,
                ))
            routed_entity_ids = {
                route.owner_entity_id for route in successful_routes if route.owner_entity_id
            }
            pending_related_ids = {
                entity_id for proposal in proposals for entity_id in proposal.affected_entity_ids
                if entity_id not in routed_entity_ids
            }
            if pending_related_ids:
                related_pages = self.materializer.regenerate(pending_related_ids)
                materialized.changed_pages.update(related_pages.changed_pages)
                materialized.created_slugs.update(related_pages.created_slugs)
                materialized.updated_slugs.update(related_pages.updated_slugs)
                materialized.deleted_slugs.update(related_pages.deleted_slugs)
            if completed_source_ids:
                self.logs.mark_consolidated(completed_source_ids)
            self.artifacts.save_scope_cohort(ScopeCohort(
                cohort_id=f"cohort-{uuid.uuid4().hex[:12]}",
                dream_run_id=run_id,
                claim_ids=sorted(incoming_claim_ids),
                source_ids=sorted({
                    provenance.source_id
                    for claim_id in incoming_claim_ids
                    for provenance in self.artifacts.get_claim(claim_id).provenance
                }),
                revision_entity_ids=sorted({
                    entity.entity_id for entity in retained_new_entities
                }),
                created_at=now,
            ))

        report = DreamReport(
            pages_updated=len(materialized.updated_slugs),
            pages_created=len(materialized.created_slugs),
            entries_consolidated=len(completed_source_ids),
            completed_source_ids=completed_source_ids,
            pending_source_ids=pending_source_ids,
            failures=failures,
            reconsolidation_proposal_ids=[
                proposal.proposal_id for proposal in proposals
            ],
        )
        if not dry_run:
            self._persist_audit(run_id, started_at, raw_entries, report, decisions)
        return report

    def _initial_scope_claims(
        self, queued_claims: list[MemoryClaim]
    ) -> list[MemoryClaim]:
        """Join incoming evidence only to explicitly deferred scope."""
        if not queued_claims:
            return []
        claim_ids = {claim.claim_id for claim in queued_claims}
        claim_ids.update(
            placement.claim_id
            for placement in self.artifacts.list_placements(status="deferred")
        )
        claims = {
            claim.claim_id: claim
            for claim in self.artifacts.list_claims(status="active")
            if claim.dream_disposition != "excluded_source_policy"
        }
        return sorted(
            (claims[claim_id] for claim_id in claim_ids if claim_id in claims),
            key=lambda item: (item.recorded_at, item.claim_id),
        )

    def _scope_revision_claims(
        self,
        queued_claims: list[MemoryClaim],
        revision_entities: list[EntityRecord],
    ) -> list[MemoryClaim]:
        """Expand a Dream with explicit prior scope neighborhoods, never lexical similarity."""
        if not queued_claims:
            return []
        claim_ids = {claim.claim_id for claim in queued_claims}

        # The immediately preceding consolidation cohort is the persisted semantic
        # context in which an early description may have been assigned before a
        # later name or identity became available.
        cohorts = self.artifacts.list_scope_cohorts()
        if cohorts:
            claim_ids.update(cohorts[-1].claim_ids)

        # You and deferred are explicit scope states. They are the two places from
        # which a newly established, more specific entity most often needs to take
        # ownership; neither selection consults claim text or surface aliases.
        for placement in self.artifacts.list_placements():
            if placement.status == "deferred" or placement.owner_entity_id == "you":
                claim_ids.add(placement.claim_id)

        # Stable entity endpoints extend the neighborhood across prior cohorts.
        current_entity_ids = {
            entity.entity_id for entity in revision_entities
        } | {
            reference.entity_id
            for claim in queued_claims
            for reference in self.artifacts.list_entity_references(
                claim_id=claim.claim_id, status="active"
            )
            if reference.entity_id
        }
        if current_entity_ids:
            claim_ids.update(
                reference.claim_id
                for reference in self.artifacts.list_entity_references(status="active")
                if reference.entity_id in current_entity_ids
            )

        claims = {
            claim.claim_id: claim
            for claim in self.artifacts.list_claims(status="active")
            if claim.dream_disposition != "excluded_source_policy"
        }
        return sorted(
            (claims[claim_id] for claim_id in claim_ids if claim_id in claims),
            key=lambda item: (item.recorded_at, item.claim_id),
        )

    @staticmethod
    def _merge_revision_routing(
        initial: RoutingResult, revision: RoutingResult
    ) -> RoutingResult:
        """Keep initial identity evidence while making revised routes authoritative."""
        entities = {
            entity.entity_id: entity
            for entity in [*initial.new_entities, *revision.new_entities]
        }
        decisions = {
            decision.decision_id: decision
            for decision in [
                *initial.entity_decisions,
                *revision.entity_decisions,
            ]
        }
        encounters = {
            encounter.encounter_id: encounter
            for encounter in [*initial.encounters, *revision.encounters]
        }
        revision.new_entities = list(entities.values())
        revision.entity_decisions = list(decisions.values())
        revision.encounters = list(encounters.values())
        return revision

    def _retention_records(
        self,
        sources: list[SourceDocument],
        claim_ids: set[str],
        episodes_by_source: dict,
    ) -> list[NonWikiRetentionRecord]:
        """Compile structural/extraction exclusions before ownership planning."""
        now = datetime.now().astimezone().isoformat()
        records: dict[str, NonWikiRetentionRecord] = {}
        source_by_id = {source.source_id: source for source in sources}

        for source in sources:
            episode = episodes_by_source.get(source.source_id)
            if episode is None:
                continue
            segments = {segment.segment_id: segment for segment in source.segments}
            for segment_id in episode.ignored_segment_ids:
                segment = segments.get(segment_id)
                role = str(
                    (segment.role or segment.speaker) if segment else ""
                ).strip().lower()
                if role == "assistant":
                    reason = "assistant_unadopted"
                    origin = "source_structure"
                elif role == "system":
                    reason = "system_control"
                    origin = "source_structure"
                else:
                    reason = "extractor_rejected"
                    origin = "extraction"
                record_id = f"retention-segment-{segment_id}"
                records[record_id] = NonWikiRetentionRecord(
                    retention_id=record_id,
                    target_type="segment",
                    source_id=source.source_id,
                    segment_ids=[segment_id],
                    reason=reason,
                    policy_origin=origin,
                    created_at=now,
                )

        for claim in self.artifacts.list_claims(status="active"):
            if claim.claim_id not in claim_ids:
                continue
            ignored_segment_ids = {
                segment_id
                for provenance in claim.provenance
                for segment_id in (
                    episodes_by_source.get(provenance.source_id).ignored_segment_ids
                    if episodes_by_source.get(provenance.source_id) is not None
                    else []
                )
            }
            claim_segment_ids = {
                segment_id
                for provenance in claim.provenance
                for segment_id in provenance.segment_ids
            }
            excluded_by_extraction = bool(
                claim_segment_ids and claim_segment_ids <= ignored_segment_ids
            )
            admitted = self._claim_is_admitted(claim, source_by_id)
            if admitted and not excluded_by_extraction:
                continue
            for provenance in claim.provenance:
                if provenance.source_id not in source_by_id:
                    continue
                if excluded_by_extraction:
                    reason = "extractor_rejected"
                    origin = "extraction"
                else:
                    source = source_by_id[provenance.source_id]
                    wanted = set(provenance.segment_ids)
                    roles = {
                        str(segment.role or segment.speaker or "").strip().lower()
                        for segment in source.segments
                        if segment.segment_id in wanted
                    }
                    reason = (
                        "system_control" if "system" in roles
                        else "assistant_unadopted"
                    )
                    origin = "source_structure"
                record_id = f"retention-claim-{claim.claim_id}"
                records[record_id] = NonWikiRetentionRecord(
                    retention_id=record_id,
                    target_type="claim",
                    source_id=provenance.source_id,
                    segment_ids=list(provenance.segment_ids),
                    claim_id=claim.claim_id,
                    reason=reason,
                    policy_origin=origin,
                    created_at=now,
                )
        return list(records.values())

    def _build_evidence(
        self,
        sources: list[SourceDocument],
        queued_claim_ids: set[str],
        episodes_by_source: dict,
        incoming_claim_ids: set[str],
    ) -> tuple[list[ClaimEvidence], dict[str, DreamClaimDecision]]:
        source_by_id = {source.source_id: source for source in sources}
        evidence: list[ClaimEvidence] = []
        decisions: dict[str, DreamClaimDecision] = {}
        for claim in self.artifacts.list_claims(status="active"):
            if claim.claim_id not in queued_claim_ids:
                continue
            matching_source = next(
                (
                    source_by_id.get(provenance.source_id)
                    for provenance in claim.provenance
                    if provenance.source_id in source_by_id
                ),
                None,
            )
            if matching_source is None:
                continue
            raw_log_id = matching_source.raw_log_entry_id
            ignored_segment_ids = {
                segment_id
                for provenance in claim.provenance
                for segment_id in (
                    episodes_by_source.get(provenance.source_id).ignored_segment_ids
                    if episodes_by_source.get(provenance.source_id) is not None
                    else []
                )
            }
            claim_segment_ids = {
                segment_id
                for provenance in claim.provenance
                for segment_id in provenance.segment_ids
            }
            excluded_by_extraction = bool(
                claim_segment_ids and claim_segment_ids <= ignored_segment_ids
            )
            admitted = (
                self._claim_is_admitted(claim, source_by_id)
                and not excluded_by_extraction
            )
            existing_placement = self.artifacts.placement_for_claim(claim.claim_id)
            revising_existing = claim.claim_id not in incoming_claim_ids
            previous_disposition = claim.dream_disposition
            previous_reason = claim.dream_disposition_reason
            previous_slugs: list[str] = []
            if existing_placement and existing_placement.owner_entity_id:
                previous_slugs = [
                    self.artifacts.get_entity(existing_placement.owner_entity_id).slug
                ]
            decisions[claim.claim_id] = DreamClaimDecision(
                claim_id=claim.claim_id,
                evidence_id=f"{claim.claim_id}::claim",
                source_id=matching_source.source_id,
                raw_log_entry_id=raw_log_id,
                disposition=(
                    previous_disposition
                    if revising_existing
                    else
                    "pending" if admitted
                    else "excluded_source_policy"
                ),
                reason=(
                    previous_reason or "Awaiting scope revision."
                    if revising_existing
                    else
                    "Excluded by the typed extraction-retention policy."
                    if excluded_by_extraction
                    else "Awaiting page assignment."
                    if admitted
                    else "Excluded by the typed source-structure retention policy."
                ),
                page_slugs=previous_slugs if revising_existing else [],
            )
            if admitted:
                evidence.append(ClaimEvidence(claim, matching_source))
        return evidence, decisions

    @staticmethod
    def _claim_is_admitted(
        claim: MemoryClaim, source_by_id: dict[str, SourceDocument]
    ) -> bool:
        for provenance in claim.provenance:
            source = source_by_id.get(provenance.source_id)
            if source is None:
                continue
            if source.source_type != "agent_conversation":
                return True
            wanted = set(provenance.segment_ids)
            roles = {
                str(value).strip().lower()
                for segment in source.segments
                if segment.segment_id in wanted
                for value in (segment.role, segment.speaker)
                if value
            }
            if provenance.speaker:
                roles.add(provenance.speaker.strip().lower())
            if "user" in roles or roles - {"assistant", "system", "tool", "unknown"}:
                return True
        return False

    @staticmethod
    def _set_decision(
        decisions: dict[str, DreamClaimDecision],
        claim_id: str,
        disposition: str,
        reason: str,
        *,
        page_slugs: list[str] | None = None,
    ) -> None:
        decision = decisions.get(claim_id)
        if decision is None:
            return
        decision.disposition = disposition
        decision.reason = reason
        decision.page_slugs = list(page_slugs or [])

    def _persist_audit(
        self,
        run_id: str,
        started_at: str,
        raw_entries: list[LogEntry],
        report: DreamReport,
        decisions: dict[str, DreamClaimDecision],
    ) -> None:
        completed_at = datetime.now().astimezone().isoformat()
        if report.pending_source_ids and not report.completed_source_ids:
            status = "failed"
        elif report.pending_source_ids or report.failures:
            status = "partial"
        else:
            status = "completed"
        self.artifacts.persist_dream_audit(DreamRunAudit(
            run_id=run_id,
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            source_ids=sorted({
                *[entry.entry_id for entry in raw_entries],
                *[
                    decision.raw_log_entry_id
                    for decision in decisions.values()
                    if decision.raw_log_entry_id
                ],
            }),
            completed_source_ids=list(report.completed_source_ids),
            pending_source_ids=list(report.pending_source_ids),
            pages_created=report.pages_created,
            pages_updated=report.pages_updated,
            claim_decisions=sorted(decisions.values(), key=lambda item: item.claim_id),
            failures=list(report.failures),
            reconsolidation_proposal_ids=list(report.reconsolidation_proposal_ids),
        ))
