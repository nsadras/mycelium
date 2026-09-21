"""SQLite repository for durable memory artifacts."""

from __future__ import annotations
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from mycelium.database import database
from mycelium.ontology import section_keys

from mycelium.artifact_models import (
    SHORT_TERM_DISPOSITIONS,
    ClaimEntityReference,
    ClaimPlacement,
    ClaimProvenance,
    ClaimScopeDecision,
    ConsolidatedFact,
    DreamClaimDecision,
    DreamCommit,
    DreamRunAudit,
    EntityEncounter,
    EntityRecord,
    EntityResolutionDecision,
    EpisodeManifest,
    ExtractionBatchState,
    ExtractionSegmentDisposition,
    IdentityWorkUnit,
    IngestionOperation,
    MemoryClaim,
    NonWikiRetentionRecord,
    OrganizationProposal,
    ReconsolidationProposal,
    ScopeCohort,
    SourceDocument,
    SourceSegment,
    _slugify,
)


KINDS = [
    "sources",
    "episodes",
    "claims",
    "dream-runs",
    "dream-commits",
    "reconsolidation-proposals",
    "entities",
    "placements",
    "scope-decisions",
    "retention-records",
    "entity-references",
    "entity-resolution-decisions",
    "identity-work-units",
    "ingestion-operations",
    "scope-cohorts",
    "encounters",
    "consolidated-facts",
    "organization-proposals",
    "lifecycle-operations",
    "model-decisions",
    "participant-bindings",
    "identity-review-history",
]


class ArtifactStore:
    def __init__(self, root: Path, *, db=None):
        self.root = root
        self.db = db if db is not None else database(root.parent)

    def save_source(self, source: SourceDocument) -> None:
        self.db.put("sources", source.source_id, asdict(source))

    def save_ingestion_operation(self, operation: IngestionOperation) -> None:
        self.db.put("ingestion-operations", operation.operation_id, asdict(operation))

    def get_ingestion_operation(self, operation_id: str) -> IngestionOperation:
        return IngestionOperation(**self.db.get("ingestion-operations", operation_id))

    def list_ingestion_operations(
        self, *, status: str | None = None
    ) -> list[IngestionOperation]:
        operations = [
            self.get_ingestion_operation(path)
            for path in sorted(self.db.ids("ingestion-operations"))
        ]
        return [
            operation
            for operation in operations
            if status is None or operation.status == status
        ]

    def get_source(self, source_id: str) -> SourceDocument:
        data = self.db.get("sources", source_id)
        data["segments"] = [SourceSegment(**item) for item in data.get("segments", [])]
        return SourceDocument(**data)

    def list_sources(self) -> list[SourceDocument]:
        return [self.get_source(path) for path in sorted(self.db.ids("sources"))]

    def save_episode(self, episode: EpisodeManifest) -> None:
        self.db.put("episodes", episode.episode_id, asdict(episode))

    def get_episode(self, episode_id: str) -> EpisodeManifest:
        data = self.db.get("episodes", episode_id)
        data["segment_dispositions"] = [
            ExtractionSegmentDisposition(**item)
            for item in data.get("segment_dispositions", [])
        ]
        data["extraction_batches"] = [
            ExtractionBatchState(**item) for item in data.get("extraction_batches", [])
        ]
        return EpisodeManifest(**data)

    def list_episodes(self) -> list[EpisodeManifest]:
        return [self.get_episode(path) for path in sorted(self.db.ids("episodes"))]

    def save_identity_work_unit(self, unit: IdentityWorkUnit) -> None:
        self.db.put("identity-work-units", unit.unit_id, asdict(unit))

    def get_identity_work_unit(self, unit_id: str) -> IdentityWorkUnit:
        return IdentityWorkUnit(**self.db.get("identity-work-units", unit_id))

    def list_identity_work_units(self) -> list[IdentityWorkUnit]:
        return [
            self.get_identity_work_unit(path)
            for path in sorted(self.db.ids("identity-work-units"))
        ]

    def save_claim(self, claim: MemoryClaim) -> None:
        self.db.put("claims", claim.claim_id, asdict(claim))

    def save_entity(self, entity: EntityRecord) -> None:
        self.db.put("entities", entity.entity_id, asdict(entity))

    def get_entity(self, entity_id: str) -> EntityRecord:
        return EntityRecord(**self.db.get("entities", entity_id))

    def list_entities(self, *, status: str | None = None) -> list[EntityRecord]:
        entities = [
            self.get_entity(path)
            for path in sorted(self.db.ids("entities", "status", status))
        ]
        return [
            entity for entity in entities if status is None or entity.status == status
        ]

    def entity_for_slug(self, slug: str) -> EntityRecord | None:
        wanted = _slugify(slug)
        ids = self.db.ids("entities", "slug", wanted)
        return self.get_entity(ids[0]) if ids else None

    def create_entity(
        self,
        entity_type: str,
        title: str,
        *,
        aliases: list[str] | None = None,
        materialization_state: str = "materialized",
    ) -> EntityRecord:
        now = datetime.now().astimezone().isoformat()
        slug = _slugify(title)
        if entity_type == "you":
            entity_id = "you"
            slug = "you"
        else:
            base = f"{entity_type}-{slug}"
            entity_id = base
            suffix = 2
            while True:
                try:
                    self.get_entity(entity_id)
                except FileNotFoundError:
                    break
                entity_id = f"{base}-{suffix}"
                suffix += 1

            base_slug = slug
            suffix = 2
            while self.db.ids("entities", "slug", slug):
                slug = f"{base_slug}-{suffix}"
                suffix += 1
        entity = EntityRecord(
            entity_id=entity_id,
            entity_type=entity_type,
            title=title,
            slug=slug,
            aliases=list(aliases or []),
            status="active",
            created_at=now,
            updated_at=now,
            materialization_state=materialization_state,
        )
        self.save_entity(entity)
        return entity

    def save_placement(self, placement: ClaimPlacement) -> None:
        self.get_claim(placement.claim_id)
        if placement.owner_entity_id:
            entity = self.get_entity(placement.owner_entity_id)
            if entity.status != "active":
                raise ValueError("Placed claims require an active owner entity")
            allowed = set(section_keys(entity.entity_type))
            if placement.section_key not in allowed:
                raise ValueError(
                    f"Section {placement.section_key!r} is invalid for {entity.entity_type}"
                )
            if placement.relationship_kind == "project_role":
                project_links = [
                    linked_id
                    for linked_id in placement.linked_entity_ids
                    if self.get_entity(linked_id).entity_type == "project"
                ]
                if (
                    entity.entity_type not in {"you", "person"}
                    or len(project_links) != 1
                ):
                    raise ValueError(
                        "Project-role placements require a Person or You owner and exactly one linked Project"
                    )
        for linked_id in placement.linked_entity_ids:
            if self.get_entity(linked_id).status != "active":
                raise ValueError("Placed claims require active linked entities")
        for entity_id, section in placement.page_sections.items():
            destination = self.get_entity(entity_id)
            if destination.status != "active" or section not in section_keys(
                destination.entity_type
            ):
                raise ValueError(
                    "Page destinations require active identities and type-valid sections"
                )
        self.db.put("placements", placement.claim_id, asdict(placement))

    def get_placement(self, claim_id: str) -> ClaimPlacement:
        return ClaimPlacement(**self.db.get("placements", claim_id))

    def list_placements(self, *, status: str | None = None) -> list[ClaimPlacement]:
        placements = [
            self.get_placement(path)
            for path in sorted(self.db.ids("placements", "status", status))
        ]
        return [item for item in placements if status is None or item.status == status]

    def placement_for_claim(self, claim_id: str) -> ClaimPlacement | None:
        try:
            return self.get_placement(claim_id)
        except FileNotFoundError:
            return None

    def save_scope_decision(self, decision: ClaimScopeDecision) -> None:
        if decision.status == "active":
            for current in self.list_scope_decisions(
                claim_id=decision.claim_id, status="active"
            ):
                if current.decision_id == decision.decision_id:
                    continue
                current.status = "superseded"
                current.superseded_by_decision_id = decision.decision_id
                self.db.put("scope-decisions", current.decision_id, asdict(current))
        self.db.put("scope-decisions", decision.decision_id, asdict(decision))

    def get_scope_decision(self, decision_id: str) -> ClaimScopeDecision:
        return ClaimScopeDecision(**self.db.get("scope-decisions", decision_id))

    def list_scope_decisions(
        self, *, claim_id: str | None = None, status: str | None = None
    ) -> list[ClaimScopeDecision]:
        values = [
            self.get_scope_decision(path)
            for path in sorted(self.db.ids("scope-decisions"))
        ]
        return [
            item
            for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (status is None or item.status == status)
        ]

    def active_scope_decision(self, claim_id: str) -> ClaimScopeDecision | None:
        values = self.list_scope_decisions(claim_id=claim_id, status="active")
        return values[-1] if values else None

    def save_retention_record(self, record: NonWikiRetentionRecord) -> None:
        if record.claim_id:
            self.get_claim(record.claim_id)
        self.get_source(record.source_id)
        self.db.put("retention-records", record.retention_id, asdict(record))

    def get_retention_record(self, retention_id: str) -> NonWikiRetentionRecord:
        return NonWikiRetentionRecord(**self.db.get("retention-records", retention_id))

    def list_retention_records(
        self, *, claim_id: str | None = None, source_id: str | None = None
    ) -> list[NonWikiRetentionRecord]:
        values = [
            self.get_retention_record(path)
            for path in sorted(self.db.ids("retention-records"))
        ]
        return [
            item
            for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (source_id is None or item.source_id == source_id)
        ]

    def save_entity_reference(self, reference: ClaimEntityReference) -> None:
        """Save an exact reference ID; names are not identity keys."""
        self.get_claim(reference.claim_id)
        if reference.entity_id:
            entity = self.get_entity(reference.entity_id)
            if reference.status == "active" and entity.status != "active":
                raise ValueError("Active references require an active entity")
        self.db.put("entity-references", reference.reference_id, asdict(reference))

    def replace_automatic_entity_references(
        self,
        claim_ids: Iterable[str],
        references: Iterable[ClaimEntityReference],
        *,
        dream_run_id: str,
    ) -> None:
        """Atomically replace successful attribution, retaining manual decisions.

        An empty replacement is meaningful: the completed decision found no
        references. Failed or unprocessed claims must not appear in claim_ids.
        """
        claim_ids, references = set(claim_ids), list(references)
        if not dream_run_id:
            raise ValueError("Reference replacement requires a build ID")
        incoming_ids = {r.reference_id for r in references}
        if len(incoming_ids) != len(references):
            raise ValueError("Replacement reference IDs must be unique")
        if any(
            r.claim_id not in claim_ids
            or r.origin not in {"scope", "extraction"}
            or r.status != "active"
            or r.dream_run_id != dream_run_id
            for r in references
        ):
            raise ValueError("Replacement references must be active automatic decisions in this build and claim scope")
        with self.db.transaction():
            for claim_id in sorted(claim_ids):
                self.get_claim(claim_id)
                for current in self.list_entity_references(claim_id=claim_id, status="active"):
                    if current.origin == "manual" or current.reference_id in incoming_ids:
                        continue
                    current.status = "retired"
                    current.retired_by_dream_run_id = dream_run_id
                    self.save_entity_reference(current)
            for reference in references:
                try:
                    prior = self.get_entity_reference(reference.reference_id)
                except FileNotFoundError:
                    prior = None
                if prior is not None and (
                    prior.claim_id != reference.claim_id or prior.origin == "manual"
                ):
                    raise ValueError("A replacement cannot overwrite another claim or a manual reference")
                self.save_entity_reference(reference)

    def get_entity_reference(self, reference_id: str) -> ClaimEntityReference:
        return ClaimEntityReference(**self.db.get("entity-references", reference_id))

    def list_entity_references(
        self,
        *,
        claim_id: str | None = None,
        entity_id: str | None = None,
        status: str | None = None,
    ) -> list[ClaimEntityReference]:
        values = [
            self.get_entity_reference(path)
            for path in self.db.ids(
                "entity-references",
                "claim_id" if claim_id is not None else "entity_id",
                claim_id if claim_id is not None else entity_id,
            )
        ]
        return [
            item
            for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (entity_id is None or item.entity_id == entity_id)
            and (status is None or item.status == status)
        ]

    def save_entity_resolution_decision(
        self, decision: EntityResolutionDecision
    ) -> None:
        if decision.entity_id:
            self.get_entity(decision.entity_id)
        for entity_id in decision.candidate_entity_ids:
            self.get_entity(entity_id)
        for claim_id in decision.supporting_claim_ids:
            self.get_claim(claim_id)
        self.db.put(
            "entity-resolution-decisions", decision.decision_id, asdict(decision)
        )

    def get_entity_resolution_decision(
        self, decision_id: str
    ) -> EntityResolutionDecision:
        return EntityResolutionDecision(
            **self.db.get("entity-resolution-decisions", decision_id)
        )

    def list_entity_resolution_decisions(
        self, *, entity_id: str | None = None, review_state: str | None = None
    ) -> list[EntityResolutionDecision]:
        field, value = ("entity_id", entity_id) if entity_id is not None else ("review_state", review_state)
        values = [
            self.get_entity_resolution_decision(path)
            for path in sorted(self.db.ids("entity-resolution-decisions", field, value))
        ]
        return [
            item
            for item in values
            if (entity_id is None or item.entity_id == entity_id)
            and (review_state is None or item.review_state == review_state)
        ]

    def save_scope_cohort(self, cohort: ScopeCohort) -> None:
        for claim_id in cohort.claim_ids:
            self.get_claim(claim_id)
        self.db.put("scope-cohorts", cohort.cohort_id, asdict(cohort))

    def get_scope_cohort(self, cohort_id: str) -> ScopeCohort:
        return ScopeCohort(**self.db.get("scope-cohorts", cohort_id))

    def list_scope_cohorts(self) -> list[ScopeCohort]:
        values = [
            self.get_scope_cohort(path) for path in sorted(self.db.ids("scope-cohorts"))
        ]
        return sorted(values, key=lambda item: (item.created_at, item.cohort_id))

    def save_encounter(self, encounter: EntityEncounter) -> None:
        if self.get_entity(encounter.entity_id).status != "active":
            raise ValueError("Encounters require an active entity")
        self.db.put("encounters", encounter.encounter_id, asdict(encounter))

    def get_encounter(self, encounter_id: str) -> EntityEncounter:
        return EntityEncounter(**self.db.get("encounters", encounter_id))

    def list_encounters(self, *, entity_id: str | None = None) -> list[EntityEncounter]:
        values = [
            self.get_encounter(path) for path in sorted(self.db.ids("encounters"))
        ]
        return [
            item for item in values if entity_id is None or item.entity_id == entity_id
        ]

    def save_consolidated_fact(self, fact: ConsolidatedFact) -> None:
        owner = self.get_entity(fact.owner_entity_id)
        if owner.status != "active":
            raise ValueError("Consolidated facts require an active owner entity")
        if not fact.section_key.strip():
            raise ValueError("View items require a nonempty heading")
        for claim_id in fact.member_claim_ids:
            self.get_claim(claim_id)
        for linked_id in fact.linked_entity_ids:
            if self.get_entity(linked_id).status != "active":
                raise ValueError("Consolidated facts require active linked entities")
        self.db.put("consolidated-facts", fact.fact_id, asdict(fact))

    def get_consolidated_fact(self, fact_id: str) -> ConsolidatedFact:
        return ConsolidatedFact(**self.db.get("consolidated-facts", fact_id))

    def list_consolidated_facts(
        self, *, owner_entity_id: str | None = None
    ) -> list[ConsolidatedFact]:
        values = [
            self.get_consolidated_fact(path)
            for path in self.db.ids(
                "consolidated-facts", "owner_entity_id", owner_entity_id
            )
        ]
        return [
            item
            for item in values
            if owner_entity_id is None or item.owner_entity_id == owner_entity_id
        ]

    def facts_for_claim(self, claim_id: str) -> list[ConsolidatedFact]:
        return [
            self.get_consolidated_fact(path)
            for path in self.db.ids("consolidated-facts", "member_claim_ids", claim_id)
        ]

    def entities_for_claims(self, claim_ids: set[str]) -> set[str]:
        """Exact subjects and every cited view destination; evidence has no sole owner."""
        return {eid for cid in claim_ids
                for fact in self.facts_for_claim(cid)
                for eid in [fact.owner_entity_id, *fact.linked_entity_ids]} | {
                    ref.entity_id for cid in claim_ids
                    for ref in self.list_entity_references(claim_id=cid, status="active")
                    if ref.entity_id}

    def placements_for_entity(self, entity_id: str) -> list[ClaimPlacement]:
        return [
            placement
            for placement in self.list_placements(status="placed")
            if placement.owner_entity_id == entity_id
        ]

    def save_organization_proposal(self, proposal: OrganizationProposal) -> None:
        self.db.put("organization-proposals", proposal.proposal_id, asdict(proposal))

    def get_organization_proposal(self, proposal_id: str) -> OrganizationProposal:
        return OrganizationProposal(
            **self.db.get("organization-proposals", proposal_id)
        )

    def list_organization_proposals(
        self, *, status: str | None = None
    ) -> list[OrganizationProposal]:
        proposals = [
            self.get_organization_proposal(path)
            for path in sorted(
                self.db.ids("organization-proposals", "status", status), reverse=True
            )
        ]
        return [item for item in proposals if status is None or item.status == status]

    def get_claim(self, claim_id: str) -> MemoryClaim:
        data = self.db.get("claims", claim_id)
        data["provenance"] = [
            ClaimProvenance(**item) for item in data.get("provenance", [])
        ]
        return MemoryClaim(**data)

    def save_dream_run(self, run: DreamRunAudit) -> None:
        self.db.put("dream-runs", run.run_id, asdict(run))

    def save_dream_commit(self, commit: DreamCommit) -> None:
        self.db.put("dream-commits", commit.commit_id, asdict(commit))

    def get_dream_commit(self, commit_id: str) -> DreamCommit:
        return DreamCommit(**self.db.get("dream-commits", commit_id))

    def list_dream_commits(self, *, status: str | None = None) -> list[DreamCommit]:
        commits = [
            self.get_dream_commit(path)
            for path in self.db.ids("dream-commits", "status", status)
        ]
        return [
            commit for commit in commits if status is None or commit.status == status
        ]

    def get_dream_run(self, run_id: str) -> DreamRunAudit:
        data = self.db.get("dream-runs", run_id)
        data["claim_decisions"] = [
            DreamClaimDecision(**item) for item in data.get("claim_decisions", [])
        ]
        return DreamRunAudit(**data)

    def list_dream_runs(self) -> list[DreamRunAudit]:
        return [
            self.get_dream_run(path)
            for path in sorted(self.db.ids("dream-runs"), reverse=True)
        ]

    def save_reconsolidation_proposal(self, proposal: ReconsolidationProposal) -> None:
        self.db.put("reconsolidation-proposals", proposal.proposal_id, asdict(proposal))

    def get_reconsolidation_proposal(self, proposal_id: str) -> ReconsolidationProposal:
        return ReconsolidationProposal(
            **self.db.get("reconsolidation-proposals", proposal_id)
        )

    def list_reconsolidation_proposals(
        self, *, status: str | None = None
    ) -> list[ReconsolidationProposal]:
        proposals = [
            self.get_reconsolidation_proposal(path)
            for path in sorted(
                self.db.ids("reconsolidation-proposals", "status", status), reverse=True
            )
        ]
        return [
            proposal
            for proposal in proposals
            if status is None or proposal.status == status
        ]

    def find_reconsolidation_proposal(
        self,
        incoming_claim_ids: Iterable[str],
        target_claim_ids: Iterable[str],
        relation: str,
    ) -> ReconsolidationProposal | None:
        incoming = sorted(set(incoming_claim_ids))
        targets = sorted(set(target_claim_ids))
        return next(
            (
                proposal
                for proposal in self.list_reconsolidation_proposals()
                if proposal.incoming_claim_ids == incoming
                and proposal.target_claim_ids == targets
                and (proposal.proposed_relation == relation)
            ),
            None,
        )

    def pending_reconsolidation_claim_ids(self) -> set[str]:
        return {
            claim_id
            for proposal in self.list_reconsolidation_proposals(status="pending")
            for claim_id in (*proposal.incoming_claim_ids, *proposal.target_claim_ids)
        }

    def persist_dream_audit(self, run: DreamRunAudit) -> None:
        """Commit current claim dispositions, then write the immutable run record."""
        decided_at = run.completed_at
        for decision in run.claim_decisions:
            try:
                claim = self.get_claim(decision.claim_id)
            except FileNotFoundError:
                continue
            claim.dream_disposition = decision.disposition
            claim.dream_disposition_reason = decision.reason
            claim.dream_run_id = run.run_id
            claim.dream_disposition_at = decided_at
            self.save_claim(claim)
        self.save_dream_run(run)

    def list_claims(self, *, status: str | None = None) -> list[MemoryClaim]:
        claims = [
            self.get_claim(path)
            for path in sorted(self.db.ids("claims", "status", status))
        ]
        return [claim for claim in claims if status is None or claim.status == status]

    def list_short_term_claims(
        self, *, include_deferred: bool = True
    ) -> list[MemoryClaim]:
        """Return active claims needing initial organization or a maintenance retry.

        Claim disposition is the durable queue state. Existing views must not
        hide explicitly requested maintenance, including identity review.
        """
        allowed = {"pending", "routing_failed"}
        if include_deferred:
            allowed.add("deferred")
        queued = []
        for claim in self.list_claims(status="active"):
            if claim.dream_disposition not in allowed:
                continue
            queued.append(claim)
        return queued

    def build_incomplete(self) -> bool:
        active = {s.source_id for s in self.list_sources() if s.status == "active"}
        complete = {e.source_id for e in self.list_episodes() if e.extraction_status == "complete"}
        return bool(active - complete) or any(
            c.status == "active" and c.dream_disposition in {"pending", "routing_failed"}
            and any(p.source_id in active for p in c.provenance)
            for c in self.list_claims())

    def memory_tier(self, claim_id: str) -> str:
        claim = self.get_claim(claim_id)
        if claim.dream_disposition == "excluded_source_policy":
            return "source"
        if claim.dream_disposition in SHORT_TERM_DISPOSITIONS and not self.facts_for_claim(claim_id):
            return "short_term"
        return "canonical"

    def claims_for_sources(
        self, source_ids: Iterable[str], *, active_only: bool = True
    ) -> list[MemoryClaim]:
        wanted = set(source_ids)
        return [
            claim
            for claim in self.list_claims(status="active" if active_only else None)
            if any((prov.source_id in wanted for prov in claim.provenance))
        ]

    def claims_for_entity(self, entity_id: str) -> list[MemoryClaim]:
        claim_ids = {ref.claim_id for ref in self.list_entity_references(entity_id=entity_id, status="active")}
        claim_ids.update(cid for fact in self.list_consolidated_facts()
                         if entity_id in {fact.owner_entity_id, *fact.linked_entity_ids}
                         for cid in fact.member_claim_ids)
        return [
            claim
            for claim in self.list_claims(status="active")
            if claim.claim_id in claim_ids
        ]

    def coverage_report(self) -> dict[str, Any]:
        from mycelium.artifact_integrity import coverage_report

        return coverage_report(self)

    def delete_consolidated_fact(self, fact_id: str) -> None:
        self.db.delete("consolidated-facts", fact_id)

    def clear(self) -> dict[str, int]:
        counts = {}
        with self.db.transaction():
            for kind in KINDS:
                ids = self.db.ids(kind)
                counts[kind.replace("-", "_")] = len(ids)
                for identifier in ids:
                    self.db.delete(kind, identifier)
        return counts
