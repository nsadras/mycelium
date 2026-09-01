"""Scope, retention, and audit policy for a Dream run."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from mycelium.artifacts import (
    ArtifactStore,
    DreamClaimDecision,
    DreamRunAudit,
    EntityRecord,
    MemoryClaim,
    NonWikiRetentionRecord,
    SourceDocument,
)
from mycelium.consolidation_models import ClaimEvidence, RoutingResult
from mycelium.models import DreamReport, LogEntry


class DreamPolicy:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    def initial_scope_claims(
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

    def scope_revision_claims(
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
        current_entity_ids = {entity.entity_id for entity in revision_entities} | {
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
    def merge_revision_routing(
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
        assessments = {
            assessment.assessment_id: assessment
            for assessment in [
                *initial.maturity_assessments,
                *revision.maturity_assessments,
            ]
        }
        revision.new_entities = list(entities.values())
        revision.entity_decisions = list(decisions.values())
        revision.encounters = list(encounters.values())
        revision.maturity_assessments = list(assessments.values())
        initial_routes = {route.claim_id: route for route in initial.routes}
        revision_routes = {route.claim_id: route for route in revision.routes}
        merged_routes = []
        for claim_id in dict.fromkeys([*revision_routes, *initial_routes]):
            current = revision_routes.get(claim_id)
            prior = initial_routes.get(claim_id)
            if prior is None:
                assert current is not None
                merged_routes.append(current)
                continue
            if not prior.identity_blocker_ids:
                merged_routes.append(current or prior)
                continue
            if current is None or current.placed:
                merged_routes.append(prior)
                continue
            merged_routes.append(replace(
                current,
                identity_blocker_ids=tuple(sorted({
                    *prior.identity_blocker_ids,
                    *current.identity_blocker_ids,
                })),
            ))
        revision.routes = merged_routes
        return revision

    def retention_records(
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
            for disposition in episode.segment_dispositions:
                if disposition.disposition != "source_only":
                    continue
                segment_id = disposition.segment_id
                segment = segments.get(segment_id)
                role = (
                    str((segment.role or segment.speaker) if segment else "")
                    .strip()
                    .lower()
                )
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
            source_only_segment_ids = {
                disposition.segment_id
                for provenance in claim.provenance
                for disposition in (
                    episodes_by_source.get(provenance.source_id).segment_dispositions
                    if episodes_by_source.get(provenance.source_id) is not None
                    else []
                )
                if disposition.disposition == "source_only"
            }
            claim_segment_ids = {
                segment_id
                for provenance in claim.provenance
                for segment_id in provenance.segment_ids
            }
            excluded_by_extraction = bool(
                claim_segment_ids and claim_segment_ids <= source_only_segment_ids
            )
            admitted = self.claim_is_admitted(claim, source_by_id)
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
                        "system_control" if "system" in roles else "assistant_unadopted"
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

    def build_evidence(
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
            source_only_segment_ids = {
                disposition.segment_id
                for provenance in claim.provenance
                for disposition in (
                    episodes_by_source.get(provenance.source_id).segment_dispositions
                    if episodes_by_source.get(provenance.source_id) is not None
                    else []
                )
                if disposition.disposition == "source_only"
            }
            claim_segment_ids = {
                segment_id
                for provenance in claim.provenance
                for segment_id in provenance.segment_ids
            }
            excluded_by_extraction = bool(
                claim_segment_ids and claim_segment_ids <= source_only_segment_ids
            )
            admitted = (
                self.claim_is_admitted(claim, source_by_id)
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
                    else "pending"
                    if admitted
                    else "excluded_source_policy"
                ),
                reason=(
                    previous_reason or "Awaiting scope revision."
                    if revising_existing
                    else "Excluded by the typed extraction-retention policy."
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
    def claim_is_admitted(
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
    def set_decision(
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

    def persist_audit(
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
        self.artifacts.persist_dream_audit(
            DreamRunAudit(
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status=status,
                source_ids=sorted(
                    {
                        *[entry.entry_id for entry in raw_entries],
                        *[
                            decision.raw_log_entry_id
                            for decision in decisions.values()
                            if decision.raw_log_entry_id
                        ],
                    }
                ),
                completed_source_ids=list(report.completed_source_ids),
                pending_source_ids=list(report.pending_source_ids),
                pages_created=report.pages_created,
                pages_updated=report.pages_updated,
                claim_decisions=sorted(
                    decisions.values(), key=lambda item: item.claim_id
                ),
                failures=list(report.failures),
                reconsolidation_proposal_ids=list(report.reconsolidation_proposal_ids),
            )
        )
