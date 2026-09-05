"""Offline consolidation from durable short-term claims into the canonical wiki."""

from __future__ import annotations

import uuid
import hashlib
from dataclasses import dataclass, replace
from datetime import datetime

from mycelium.artifacts import (
    ArtifactStore,
    ClaimScopeDecision,
    DreamClaimDecision,
    EntityRecord,
    EpisodeManifest,
    MemoryClaim,
    NonWikiRetentionRecord,
    ReconsolidationProposal,
    SourceDocument,
    ScopeCohort,
)
from mycelium.config import Config
from mycelium.dream_policy import DreamPolicy
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation import placement_from_route
from mycelium.consolidation_models import ClaimEvidence, ClaimRoute, RoutingResult
from mycelium.facts import FactResolver
from mycelium.dream_commit import DreamCommitService
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.short_term import ShortTermMemoryQueue
from mycelium.models import DreamReport, LogEntry
from mycelium.ollama import OllamaClient
from mycelium.store import LogStore, WikiStore


@dataclass
class DreamPreparation:
    run_id: str
    started_at: str
    queued_claims: list[MemoryClaim]
    incoming_claim_ids: set[str]
    incoming_source_ids: set[str]
    raw_entries: list[LogEntry]
    sources: list[SourceDocument]
    episodes_by_source: dict[str, EpisodeManifest]
    retention_records: list[NonWikiRetentionRecord]
    evidence: list[ClaimEvidence]
    decisions: dict[str, DreamClaimDecision]
    failures: list[dict[str, str]]
    failed_source_ids: set[str]


@dataclass
class DreamCommitInput:
    run_id: str
    started_at: str
    raw_entries: list[LogEntry]
    report: DreamReport
    decisions: dict[str, DreamClaimDecision]
    retention_records: list[NonWikiRetentionRecord]
    routing: RoutingResult | None
    successful_routes: list[ClaimRoute]
    retained_new_entities: list[EntityRecord]
    materialization: MaterializationResult
    proposals: list[ReconsolidationProposal]
    incoming_claim_ids: set[str]
    completed_source_ids: list[str]


class ConsolidationProcess:
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
        self.policy = DreamPolicy(artifacts)
        self.router = ClaimRouter(llm, artifacts)
        self.materializer = PageMaterializer(wiki, artifacts, config)
        self.fact_resolver = FactResolver(llm, artifacts)
        self.short_term = ShortTermMemoryQueue(artifacts)
        self.committer = DreamCommitService(artifacts, logs, self.materializer)

    async def run(
        self, *, dry_run: bool = False, include_deferred: bool = False,
        source_ids: set[str] | None = None
    ) -> DreamReport:
        if not dry_run:
            self.committer.recover_pending()
        prepared = self.prepare(include_deferred=include_deferred, source_ids=source_ids)
        run_id = prepared.run_id
        started_at = prepared.started_at
        queued_claims = prepared.queued_claims
        incoming_claim_ids = prepared.incoming_claim_ids
        incoming_source_ids = prepared.incoming_source_ids
        raw_entries = prepared.raw_entries
        episodes_by_source = prepared.episodes_by_source
        retention_records = prepared.retention_records
        evidence = prepared.evidence
        decisions = prepared.decisions
        failures = prepared.failures
        failed_source_ids = prepared.failed_source_ids
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
            revision_claims = self.policy.scope_revision_claims(
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
            revision_evidence, revision_decisions = self.policy.build_evidence(
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
                routing = self.policy.merge_revision_routing(routing, revision_routing)
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
                self.policy.set_decision(
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
        } | {
            placement.owner_entity_id
            for route in successful_routes
            for placement in [self.artifacts.placement_for_claim(route.claim_id)]
            if placement is not None and placement.owner_entity_id
        }
        fact_result = await self.fact_resolver.resolve(
            [placement_from_route(route) for route in successful_routes],
            affected_entity_ids={
                value for value in affected_fact_entities if value is not None
            },
            incoming_claim_ids=incoming_claim_ids,
            dream_run_id=run_id,
            seed_entities=retained_new_entities,
        )
        for failure in fact_result.failures:
            failures.append({
                "stage": "fact_resolution",
                "source_id": failure.owner_entity_id,
                "reason": failure.reason,
            })
            failed_source_ids.update(failure.raw_log_entry_ids)
            for route in successful_routes:
                prior = self.artifacts.placement_for_claim(route.claim_id)
                if (
                    (
                        route.owner_entity_id == failure.owner_entity_id
                        or (
                            prior is not None
                            and prior.owner_entity_id == failure.owner_entity_id
                        )
                    )
                    and route.claim_id in incoming_claim_ids
                ):
                    failed_source_ids.add(route.raw_log_entry_id)
                    self.policy.set_decision(
                        decisions, route.claim_id, "routing_failed", failure.reason
                    )
        successful_routes = [
            route for route in successful_routes
            if route.owner_entity_id not in fact_result.failed_owner_ids
            and (
                (prior := self.artifacts.placement_for_claim(route.claim_id)) is None
                or prior.owner_entity_id not in fact_result.failed_owner_ids
            )
        ]
        placement_updates = {
            placement.claim_id: placement for placement in fact_result.placements
        }
        successful_routes = [
            replace(
                route,
                section_key=placement_updates[route.claim_id].section_key,
                linked_entity_ids=tuple(
                    placement_updates[route.claim_id].linked_entity_ids
                ),
                page_sections=dict(placement_updates[route.claim_id].page_sections),
            ) if route.claim_id in placement_updates else route
            for route in successful_routes
        ]
        proposals = fact_result.proposals
        materialized = self.materializer.stage(
            successful_routes,
            retained_new_entities,
            facts=fact_result.facts,
            deleted_fact_ids=fact_result.deleted_fact_ids,
            placement_overrides=fact_result.placements,
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
                self.policy.set_decision(
                    decisions,
                    route.claim_id,
                    "routed",
                    f"Owned by {entity.entity_id} in {route.section_key}.",
                    page_slugs=[entity.slug],
                )
            else:
                self.policy.set_decision(
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
            self.commit(DreamCommitInput(
                run_id=run_id,
                started_at=started_at,
                raw_entries=raw_entries,
                report=report,
                decisions=decisions,
                retention_records=retention_records,
                routing=routing,
                successful_routes=successful_routes,
                retained_new_entities=retained_new_entities,
                materialization=materialized,
                proposals=proposals,
                incoming_claim_ids=incoming_claim_ids,
                completed_source_ids=completed_source_ids,
            ))
        return report

    def commit(self, inputs: DreamCommitInput) -> None:
        now = datetime.now().astimezone().isoformat()
        retained_new_entity_ids = {
            entity.entity_id for entity in inputs.retained_new_entities
        }
        existing_entity_ids = {
            entity.entity_id for entity in self.artifacts.list_entities()
        }
        encounters = [
            encounter
            for encounter in (
                inputs.routing.encounters if inputs.routing is not None else []
            )
            if encounter.entity_id in retained_new_entity_ids
            or encounter.entity_id in existing_entity_ids
        ]
        scope_decisions = [
            ClaimScopeDecision(
                decision_id=(
                    "scope-"
                    + hashlib.sha256(
                        f"{inputs.run_id}:{route.claim_id}".encode("utf-8")
                    ).hexdigest()[:16]
                ),
                claim_id=route.claim_id,
                owner_entity_id=route.owner_entity_id,
                section_key=route.section_key,
                linked_entity_ids=list(route.linked_entity_ids),
                supporting_claim_ids=list(route.supporting_claim_ids),
                confidence=route.confidence,
                reason=route.reason,
                origin="automatic",
                dream_run_id=inputs.run_id,
                status="active",
                created_at=now,
                identity_blocker_ids=list(route.identity_blocker_ids),
            )
            for route in inputs.successful_routes
        ]
        cohort = ScopeCohort(
            cohort_id=f"cohort-{inputs.run_id}",
            dream_run_id=inputs.run_id,
            claim_ids=sorted(inputs.incoming_claim_ids),
            source_ids=sorted({
                provenance.source_id
                for claim_id in inputs.incoming_claim_ids
                for provenance in self.artifacts.get_claim(claim_id).provenance
            }),
            revision_entity_ids=sorted(retained_new_entity_ids),
            created_at=now,
        )
        affected_entity_ids = {
            *inputs.materialization.entities,
            *[encounter.entity_id for encounter in encounters],
            *[
                entity_id
                for proposal in inputs.proposals
                for entity_id in proposal.affected_entity_ids
            ],
            "you",
        }
        audit = self.policy.build_audit(
            inputs.run_id,
            inputs.started_at,
            inputs.raw_entries,
            inputs.report,
            inputs.decisions,
        )
        commit = self.committer.prepare(
            run_id=inputs.run_id,
            materialization=inputs.materialization,
            retention_records=inputs.retention_records,
            entity_decisions=(
                inputs.routing.entity_decisions if inputs.routing is not None else []
            ),
            maturity_assessments=(
                inputs.routing.maturity_assessments
                if inputs.routing is not None else []
            ),
            entity_references=(
                inputs.routing.entity_references if inputs.routing is not None else []
            ),
            encounters=encounters,
            scope_decisions=scope_decisions,
            proposals=inputs.proposals,
            cohort=cohort,
            affected_entity_ids=affected_entity_ids,
            completed_log_entry_ids=inputs.completed_source_ids,
            audit=audit,
        )
        self.committer.apply(commit)

    def prepare(self, *, include_deferred: bool, source_ids: set[str] | None = None) -> DreamPreparation:
        started_at = datetime.now().astimezone().isoformat()
        run_id = (
            f"dream-{datetime.now().strftime('%Y%m%dT%H%M%S')}-"
            f"{uuid.uuid4().hex[:8]}"
        )
        queued_claims = self.short_term.claims_for_dream(
            include_deferred=include_deferred
        )
        if source_ids is not None:
            queued_claims = [
                claim for claim in queued_claims
                if any(p.source_id in source_ids for p in claim.provenance)
            ]
        incoming_claim_ids = {claim.claim_id for claim in queued_claims}
        queued_claims = self.policy.initial_scope_claims(queued_claims)
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
        if source_ids is not None:
            snapshot_log_ids = {
                source.raw_log_entry_id for source in self.artifacts.list_sources()
                if source.source_id in source_ids
            }
            raw_entries = [entry for entry in raw_entries if entry.entry_id in snapshot_log_ids]
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

        retention_records = self.policy.retention_records(
            sources, queued_claim_ids, episodes_by_source
        )
        evidence, decisions = self.policy.build_evidence(
            sources, queued_claim_ids, episodes_by_source, incoming_claim_ids
        )
        incoming_source_ids = {
            provenance.source_id
            for claim_id in incoming_claim_ids
            for provenance in self.artifacts.get_claim(claim_id).provenance
        }
        return DreamPreparation(
            run_id=run_id,
            started_at=started_at,
            queued_claims=queued_claims,
            incoming_claim_ids=incoming_claim_ids,
            incoming_source_ids=incoming_source_ids,
            raw_entries=raw_entries,
            sources=sources,
            episodes_by_source=episodes_by_source,
            retention_records=retention_records,
            evidence=evidence,
            decisions=decisions,
            failures=failures,
            failed_source_ids=failed_source_ids,
        )
