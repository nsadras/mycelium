"""Offline consolidation from durable short-term claims into the canonical wiki."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime

from mycelium.artifacts import (
    ArtifactStore,
    ClaimScopeDecision,
    DreamClaimDecision,
    DreamRunAudit,
    MemoryClaim,
    SourceDocument,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimEvidence, ClaimRouter
from mycelium.consolidation import placement_from_route
from mycelium.facts import FactConsolidator
from mycelium.materialization import PageMaterializer
from mycelium.organization import OrganizationAuditor
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

        evidence, decisions = self._build_evidence(sources, queued_claim_ids)
        routing = await self.router.route(evidence) if evidence else None
        if routing is not None:
            failed_claim_ids: set[str] = set()
            for failure in routing.failures:
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
            current_claim_ids={item.claim.claim_id for item in evidence},
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

        referenced_entity_ids = {
            route.owner_entity_id for route in successful_routes if route.owner_entity_id
        } | {
            entity_id for route in successful_routes for entity_id in route.linked_entity_ids
        } | {
            encounter.entity_id
            for encounter in (routing.encounters if routing is not None else [])
        } | {
            entity.entity_id
            for entity in (routing.new_entities if routing is not None else [])
            if entity.entity_type in {"person", "project"}
        }
        retained_new_entities = [
            entity for entity in (routing.new_entities if routing is not None else [])
            if entity.entity_id in referenced_entity_ids
        ]
        discarded_new_ids = {
            entity.entity_id for entity in (routing.new_entities if routing is not None else [])
        } - referenced_entity_ids
        if discarded_new_ids:
            successful_routes = [
                replace(route, linked_entity_ids=tuple(
                    entity_id for entity_id in route.linked_entity_ids
                    if entity_id not in discarded_new_ids
                ))
                for route in successful_routes
            ]
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
            retired_fact_ids=fact_result.retired_fact_ids,
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
            elif route.disposition == "source_only":
                self._set_decision(
                    decisions, route.claim_id, "source_only", route.reason
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
            OrganizationAuditor(self.artifacts).audit()

        report = DreamReport(
            pages_updated=len(materialized.updated_slugs),
            pages_created=len(materialized.created_slugs),
            entries_consolidated=len(completed_source_ids),
            completed_source_ids=completed_source_ids,
            pending_source_ids=pending_source_ids,
            failures=failures,
            taxonomy_failures=[],
            reconsolidation_proposal_ids=[
                proposal.proposal_id for proposal in proposals
            ],
        )
        if not dry_run:
            self._persist_audit(run_id, started_at, raw_entries, report, decisions)
        return report

    def _build_evidence(
        self,
        sources: list[SourceDocument],
        queued_claim_ids: set[str],
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
            admitted = self._claim_is_admitted(claim, source_by_id)
            is_legacy_derivation = bool(claim.derivation_operation)
            decisions[claim.claim_id] = DreamClaimDecision(
                claim_id=claim.claim_id,
                evidence_id=f"{claim.claim_id}::claim",
                source_id=matching_source.source_id,
                raw_log_entry_id=raw_log_id,
                disposition=(
                    "ignored_semantic"
                    if is_legacy_derivation
                    else "pending" if admitted else "excluded_assistant"
                ),
                reason=(
                    "Legacy Dream-derived claims are not part of the source-grounded pipeline."
                    if is_legacy_derivation
                    else "Awaiting page assignment."
                    if admitted
                    else "Assistant or system output remains source history, not durable memory."
                ),
            )
            if admitted and not is_legacy_derivation:
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
            taxonomy_failures=list(report.taxonomy_failures),
            reconsolidation_proposal_ids=list(report.reconsolidation_proposal_ids),
        ))
