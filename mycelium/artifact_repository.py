"""Filesystem repository for durable memory artifacts."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

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
    IdentityMaturityAssessment,
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
from mycelium.ontology import section_keys

def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or str(uuid.uuid4())


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.sources_dir = root / "sources"
        self.episodes_dir = root / "episodes"
        self.claims_dir = root / "claims"
        self.dream_runs_dir = root / "dream-runs"
        self.dream_commits_dir = root / "dream-commits"
        self.reconsolidation_proposals_dir = root / "reconsolidation-proposals"
        self.entities_dir = root / "entities"
        self.placements_dir = root / "placements"
        self.scope_decisions_dir = root / "scope-decisions"
        self.retention_records_dir = root / "retention-records"
        self.entity_references_dir = root / "entity-references"
        self.entity_resolution_decisions_dir = root / "entity-resolution-decisions"
        self.identity_maturity_assessments_dir = root / "identity-maturity-assessments"
        self.identity_work_units_dir = root / "identity-work-units"
        self.ingestion_operations_dir = root / "ingestion-operations"
        self.scope_cohorts_dir = root / "scope-cohorts"
        self.encounters_dir = root / "encounters"
        self.consolidated_facts_dir = root / "consolidated-facts"
        self.organization_proposals_dir = root / "organization-proposals"
        for directory in (
            self.sources_dir,
            self.episodes_dir,
            self.claims_dir,
            self.dream_runs_dir,
            self.dream_commits_dir,
            self.reconsolidation_proposals_dir,
            self.entities_dir,
            self.placements_dir,
            self.scope_decisions_dir,
            self.retention_records_dir,
            self.entity_references_dir,
            self.entity_resolution_decisions_dir,
            self.identity_maturity_assessments_dir,
            self.identity_work_units_dir,
            self.ingestion_operations_dir,
            self.scope_cohorts_dir,
            self.encounters_dir,
            self.consolidated_facts_dir,
            self.organization_proposals_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def save_source(self, source: SourceDocument) -> None:
        _atomic_json(self.sources_dir / f"{_safe_id(source.source_id)}.json", asdict(source))

    def save_ingestion_operation(self, operation: IngestionOperation) -> None:
        _atomic_json(
            self.ingestion_operations_dir / f"{_safe_id(operation.operation_id)}.json",
            asdict(operation),
        )

    def get_ingestion_operation(self, operation_id: str) -> IngestionOperation:
        return IngestionOperation(**self._read(
            self.ingestion_operations_dir / f"{_safe_id(operation_id)}.json"
        ))

    def list_ingestion_operations(
        self, *, status: str | None = None
    ) -> list[IngestionOperation]:
        operations = [
            self.get_ingestion_operation(path.stem)
            for path in sorted(self.ingestion_operations_dir.glob("*.json"))
        ]
        return [
            operation for operation in operations
            if status is None or operation.status == status
        ]

    def get_source(self, source_id: str) -> SourceDocument:
        data = self._read(self.sources_dir / f"{_safe_id(source_id)}.json")
        data["segments"] = [SourceSegment(**item) for item in data.get("segments", [])]
        return SourceDocument(**data)

    def list_sources(self) -> list[SourceDocument]:
        return [self.get_source(path.stem) for path in sorted(self.sources_dir.glob("*.json"))]

    def save_episode(self, episode: EpisodeManifest) -> None:
        _atomic_json(self.episodes_dir / f"{_safe_id(episode.episode_id)}.json", asdict(episode))

    def get_episode(self, episode_id: str) -> EpisodeManifest:
        data = self._read(self.episodes_dir / f"{_safe_id(episode_id)}.json")
        data["segment_dispositions"] = [
            ExtractionSegmentDisposition(**item)
            for item in data.get("segment_dispositions", [])
        ]
        data["extraction_batches"] = [
            ExtractionBatchState(**item)
            for item in data.get("extraction_batches", [])
        ]
        return EpisodeManifest(**data)

    def list_episodes(self) -> list[EpisodeManifest]:
        return [self.get_episode(path.stem) for path in sorted(self.episodes_dir.glob("*.json"))]

    def save_identity_work_unit(self, unit: IdentityWorkUnit) -> None:
        _atomic_json(
            self.identity_work_units_dir / f"{_safe_id(unit.unit_id)}.json",
            asdict(unit),
        )

    def get_identity_work_unit(self, unit_id: str) -> IdentityWorkUnit:
        return IdentityWorkUnit(**self._read(
            self.identity_work_units_dir / f"{_safe_id(unit_id)}.json"
        ))

    def list_identity_work_units(self) -> list[IdentityWorkUnit]:
        return [
            self.get_identity_work_unit(path.stem)
            for path in sorted(self.identity_work_units_dir.glob("*.json"))
        ]

    def save_claim(self, claim: MemoryClaim) -> None:
        _atomic_json(self.claims_dir / f"{_safe_id(claim.claim_id)}.json", asdict(claim))

    def save_entity(self, entity: EntityRecord) -> None:
        for existing in self.list_entities():
            if existing.entity_id != entity.entity_id and existing.slug == entity.slug:
                raise ValueError(f"Entity slug already exists: {entity.slug}")
        _atomic_json(self.entities_dir / f"{_safe_id(entity.entity_id)}.json", asdict(entity))

    def get_entity(self, entity_id: str) -> EntityRecord:
        return EntityRecord(**self._read(self.entities_dir / f"{_safe_id(entity_id)}.json"))

    def list_entities(self, *, status: str | None = None) -> list[EntityRecord]:
        entities = [self.get_entity(path.stem) for path in sorted(self.entities_dir.glob("*.json"))]
        return [entity for entity in entities if status is None or entity.status == status]

    def entity_for_slug(self, slug: str) -> EntityRecord | None:
        wanted = _slugify(slug)
        return next((entity for entity in self.list_entities() if entity.slug == wanted), None)

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
            existing_ids = {entity.entity_id for entity in self.list_entities()}
            while entity_id in existing_ids:
                entity_id = f"{base}-{suffix}"
                suffix += 1
            used_slugs = {entity.slug for entity in self.list_entities()}
            base_slug = slug
            suffix = 2
            while slug in used_slugs:
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
                if entity.entity_type not in {"you", "person"} or len(project_links) != 1:
                    raise ValueError(
                        "Project-role placements require a Person or You owner and "
                        "exactly one linked Project"
                    )
        for linked_id in placement.linked_entity_ids:
            if self.get_entity(linked_id).status != "active":
                raise ValueError("Placed claims require active linked entities")
        _atomic_json(
            self.placements_dir / f"{_safe_id(placement.claim_id)}.json", asdict(placement)
        )

    def get_placement(self, claim_id: str) -> ClaimPlacement:
        return ClaimPlacement(**self._read(
            self.placements_dir / f"{_safe_id(claim_id)}.json"
        ))

    def list_placements(self, *, status: str | None = None) -> list[ClaimPlacement]:
        placements = [
            self.get_placement(path.stem) for path in sorted(self.placements_dir.glob("*.json"))
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
                _atomic_json(
                    self.scope_decisions_dir / f"{_safe_id(current.decision_id)}.json",
                    asdict(current),
                )
        _atomic_json(
            self.scope_decisions_dir / f"{_safe_id(decision.decision_id)}.json",
            asdict(decision),
        )

    def get_scope_decision(self, decision_id: str) -> ClaimScopeDecision:
        return ClaimScopeDecision(**self._read(
            self.scope_decisions_dir / f"{_safe_id(decision_id)}.json"
        ))

    def list_scope_decisions(
        self, *, claim_id: str | None = None, status: str | None = None
    ) -> list[ClaimScopeDecision]:
        values = [
            self.get_scope_decision(path.stem)
            for path in sorted(self.scope_decisions_dir.glob("*.json"))
        ]
        return [
            item for item in values
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
        _atomic_json(
            self.retention_records_dir / f"{_safe_id(record.retention_id)}.json",
            asdict(record),
        )

    def get_retention_record(self, retention_id: str) -> NonWikiRetentionRecord:
        return NonWikiRetentionRecord(**self._read(
            self.retention_records_dir / f"{_safe_id(retention_id)}.json"
        ))

    def list_retention_records(
        self, *, claim_id: str | None = None, source_id: str | None = None
    ) -> list[NonWikiRetentionRecord]:
        values = [
            self.get_retention_record(path.stem)
            for path in sorted(self.retention_records_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (source_id is None or item.source_id == source_id)
        ]

    def save_entity_reference(self, reference: ClaimEntityReference) -> None:
        self.get_claim(reference.claim_id)
        if reference.entity_id:
            entity = self.get_entity(reference.entity_id)
            if reference.status == "active" and entity.status != "active":
                raise ValueError("Active references require an active entity")
        if reference.status == "active":
            for current in self.list_entity_references(
                claim_id=reference.claim_id, status="active"
            ):
                if current.role != reference.role or current.surface != reference.surface:
                    continue
                current.status = "superseded"
                current.superseded_by_reference_id = reference.reference_id
                _atomic_json(
                    self.entity_references_dir
                    / f"{_safe_id(current.reference_id)}.json",
                    asdict(current),
                )
        _atomic_json(
            self.entity_references_dir / f"{_safe_id(reference.reference_id)}.json",
            asdict(reference),
        )

    def get_entity_reference(self, reference_id: str) -> ClaimEntityReference:
        return ClaimEntityReference(**self._read(
            self.entity_references_dir / f"{_safe_id(reference_id)}.json"
        ))

    def list_entity_references(
        self,
        *,
        claim_id: str | None = None,
        entity_id: str | None = None,
        status: str | None = None,
    ) -> list[ClaimEntityReference]:
        values = [
            self.get_entity_reference(path.stem)
            for path in sorted(self.entity_references_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (entity_id is None or item.entity_id == entity_id)
            and (status is None or item.status == status)
        ]

    def save_entity_resolution_decision(
        self, decision: EntityResolutionDecision
    ) -> None:
        if decision.entity_id:
            self.get_entity(decision.entity_id)
        for claim_id in decision.supporting_claim_ids:
            self.get_claim(claim_id)
        _atomic_json(
            self.entity_resolution_decisions_dir
            / f"{_safe_id(decision.decision_id)}.json",
            asdict(decision),
        )

    def get_entity_resolution_decision(
        self, decision_id: str
    ) -> EntityResolutionDecision:
        return EntityResolutionDecision(**self._read(
            self.entity_resolution_decisions_dir / f"{_safe_id(decision_id)}.json"
        ))

    def list_entity_resolution_decisions(
        self, *, entity_id: str | None = None, review_state: str | None = None
    ) -> list[EntityResolutionDecision]:
        values = [
            self.get_entity_resolution_decision(path.stem)
            for path in sorted(self.entity_resolution_decisions_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (entity_id is None or item.entity_id == entity_id)
            and (review_state is None or item.review_state == review_state)
        ]

    def save_scope_cohort(self, cohort: ScopeCohort) -> None:
        for claim_id in cohort.claim_ids:
            self.get_claim(claim_id)
        _atomic_json(
            self.scope_cohorts_dir / f"{_safe_id(cohort.cohort_id)}.json",
            asdict(cohort),
        )

    def get_scope_cohort(self, cohort_id: str) -> ScopeCohort:
        return ScopeCohort(**self._read(
            self.scope_cohorts_dir / f"{_safe_id(cohort_id)}.json"
        ))

    def list_scope_cohorts(self) -> list[ScopeCohort]:
        values = [
            self.get_scope_cohort(path.stem)
            for path in sorted(self.scope_cohorts_dir.glob("*.json"))
        ]
        return sorted(values, key=lambda item: (item.created_at, item.cohort_id))

    def save_encounter(self, encounter: EntityEncounter) -> None:
        if self.get_entity(encounter.entity_id).status != "active":
            raise ValueError("Encounters require an active entity")
        _atomic_json(
            self.encounters_dir / f"{_safe_id(encounter.encounter_id)}.json",
            asdict(encounter),
        )

    def get_encounter(self, encounter_id: str) -> EntityEncounter:
        return EntityEncounter(**self._read(
            self.encounters_dir / f"{_safe_id(encounter_id)}.json"
        ))

    def list_encounters(self, *, entity_id: str | None = None) -> list[EntityEncounter]:
        values = [
            self.get_encounter(path.stem)
            for path in sorted(self.encounters_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if entity_id is None or item.entity_id == entity_id
        ]

    def save_consolidated_fact(self, fact: ConsolidatedFact) -> None:
        owner = self.get_entity(fact.owner_entity_id)
        if owner.status != "active":
            raise ValueError("Consolidated facts require an active owner entity")
        allowed = set(section_keys(
            owner.entity_type
        ))
        if fact.section_key not in allowed:
            raise ValueError(
                f"Section {fact.section_key!r} is invalid for consolidated fact owner"
            )
        for claim_id in fact.member_claim_ids:
            self.get_claim(claim_id)
        for linked_id in fact.linked_entity_ids:
            if self.get_entity(linked_id).status != "active":
                raise ValueError("Consolidated facts require active linked entities")
        _atomic_json(
            self.consolidated_facts_dir / f"{_safe_id(fact.fact_id)}.json",
            asdict(fact),
        )

    def get_consolidated_fact(self, fact_id: str) -> ConsolidatedFact:
        return ConsolidatedFact(**self._read(
            self.consolidated_facts_dir / f"{_safe_id(fact_id)}.json"
        ))

    def list_consolidated_facts(
        self, *, owner_entity_id: str | None = None
    ) -> list[ConsolidatedFact]:
        values = [
            self.get_consolidated_fact(path.stem)
            for path in sorted(self.consolidated_facts_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (owner_entity_id is None or item.owner_entity_id == owner_entity_id)
        ]

    def facts_for_claim(self, claim_id: str) -> list[ConsolidatedFact]:
        return [
            fact for fact in self.list_consolidated_facts()
            if claim_id in fact.member_claim_ids
        ]

    def delete_consolidated_fact(self, fact_id: str) -> None:
        path = self.consolidated_facts_dir / f"{_safe_id(fact_id)}.json"
        if path.exists():
            path.unlink()

    def placements_for_entity(self, entity_id: str) -> list[ClaimPlacement]:
        return [
            placement for placement in self.list_placements(status="placed")
            if placement.owner_entity_id == entity_id
        ]

    def save_organization_proposal(self, proposal: OrganizationProposal) -> None:
        _atomic_json(
            self.organization_proposals_dir / f"{_safe_id(proposal.proposal_id)}.json",
            asdict(proposal),
        )

    def get_organization_proposal(self, proposal_id: str) -> OrganizationProposal:
        return OrganizationProposal(**self._read(
            self.organization_proposals_dir / f"{_safe_id(proposal_id)}.json"
        ))

    def list_organization_proposals(self, *, status: str | None = None) -> list[OrganizationProposal]:
        proposals = [
            self.get_organization_proposal(path.stem)
            for path in sorted(self.organization_proposals_dir.glob("*.json"), reverse=True)
        ]
        return [item for item in proposals if status is None or item.status == status]

    def get_claim(self, claim_id: str) -> MemoryClaim:
        data = self._read(self.claims_dir / f"{_safe_id(claim_id)}.json")
        data["provenance"] = [ClaimProvenance(**item) for item in data.get("provenance", [])]
        return MemoryClaim(**data)

    def save_dream_run(self, run: DreamRunAudit) -> None:
        _atomic_json(self.dream_runs_dir / f"{_safe_id(run.run_id)}.json", asdict(run))

    def save_dream_commit(self, commit: DreamCommit) -> None:
        _atomic_json(
            self.dream_commits_dir / f"{_safe_id(commit.commit_id)}.json",
            asdict(commit),
        )

    def get_dream_commit(self, commit_id: str) -> DreamCommit:
        return DreamCommit(**self._read(
            self.dream_commits_dir / f"{_safe_id(commit_id)}.json"
        ))

    def list_dream_commits(self, *, status: str | None = None) -> list[DreamCommit]:
        commits = [
            self.get_dream_commit(path.stem)
            for path in sorted(self.dream_commits_dir.glob("*.json"))
        ]
        return [
            commit for commit in commits
            if status is None or commit.status == status
        ]

    def get_dream_run(self, run_id: str) -> DreamRunAudit:
        data = self._read(self.dream_runs_dir / f"{_safe_id(run_id)}.json")
        data["claim_decisions"] = [
            DreamClaimDecision(**item) for item in data.get("claim_decisions", [])
        ]
        return DreamRunAudit(**data)

    def list_dream_runs(self) -> list[DreamRunAudit]:
        return [
            self.get_dream_run(path.stem)
            for path in sorted(self.dream_runs_dir.glob("*.json"), reverse=True)
        ]

    def save_identity_maturity_assessment(
        self, assessment: IdentityMaturityAssessment
    ) -> None:
        _atomic_json(
            self.identity_maturity_assessments_dir
            / f"{_safe_id(assessment.assessment_id)}.json",
            asdict(assessment),
        )

    def get_identity_maturity_assessment(
        self, assessment_id: str
    ) -> IdentityMaturityAssessment:
        return IdentityMaturityAssessment(**self._read(
            self.identity_maturity_assessments_dir
            / f"{_safe_id(assessment_id)}.json"
        ))

    def list_identity_maturity_assessments(
        self, *, dream_run_id: str | None = None
    ) -> list[IdentityMaturityAssessment]:
        values = [
            self.get_identity_maturity_assessment(path.stem)
            for path in sorted(
                self.identity_maturity_assessments_dir.glob("*.json"), reverse=True
            )
        ]
        return [
            item for item in values
            if dream_run_id is None or item.dream_run_id == dream_run_id
        ]

    def save_reconsolidation_proposal(self, proposal: ReconsolidationProposal) -> None:
        _atomic_json(
            self.reconsolidation_proposals_dir / f"{_safe_id(proposal.proposal_id)}.json",
            asdict(proposal),
        )

    def get_reconsolidation_proposal(self, proposal_id: str) -> ReconsolidationProposal:
        return ReconsolidationProposal(**self._read(
            self.reconsolidation_proposals_dir / f"{_safe_id(proposal_id)}.json"
        ))

    def list_reconsolidation_proposals(
        self, *, status: str | None = None
    ) -> list[ReconsolidationProposal]:
        proposals = [
            self.get_reconsolidation_proposal(path.stem)
            for path in sorted(
                self.reconsolidation_proposals_dir.glob("*.json"), reverse=True
            )
        ]
        return [
            proposal for proposal in proposals
            if status is None or proposal.status == status
        ]

    def find_reconsolidation_proposal(
        self, incoming_claim_ids: Iterable[str], target_claim_ids: Iterable[str], relation: str
    ) -> ReconsolidationProposal | None:
        incoming = sorted(set(incoming_claim_ids))
        targets = sorted(set(target_claim_ids))
        return next((
            proposal for proposal in self.list_reconsolidation_proposals()
            if proposal.incoming_claim_ids == incoming
            and proposal.target_claim_ids == targets
            and proposal.proposed_relation == relation
        ), None)

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

    def clear(self) -> dict[str, int]:
        """Delete all derived artifacts while leaving canonical UI conversations untouched."""
        counts = {
            "sources": 0,
            "episodes": 0,
            "claims": 0,
            "dream_runs": 0,
            "dream_commits": 0,
            "reconsolidation_proposals": 0,
            "entities": 0,
            "placements": 0,
            "organization_proposals": 0,
            "scope_decisions": 0,
            "retention_records": 0,
            "entity_references": 0,
            "entity_resolution_decisions": 0,
            "identity_maturity_assessments": 0,
            "identity_work_units": 0,
            "ingestion_operations": 0,
            "scope_cohorts": 0,
            "encounters": 0,
            "consolidated_facts": 0,
        }
        for label, directory in (
            ("sources", self.sources_dir),
            ("episodes", self.episodes_dir),
            ("claims", self.claims_dir),
            ("dream_runs", self.dream_runs_dir),
            ("dream_commits", self.dream_commits_dir),
            ("reconsolidation_proposals", self.reconsolidation_proposals_dir),
            ("entities", self.entities_dir),
            ("placements", self.placements_dir),
            ("organization_proposals", self.organization_proposals_dir),
            ("scope_decisions", self.scope_decisions_dir),
            ("retention_records", self.retention_records_dir),
            ("entity_references", self.entity_references_dir),
            ("entity_resolution_decisions", self.entity_resolution_decisions_dir),
            ("identity_maturity_assessments", self.identity_maturity_assessments_dir),
            ("identity_work_units", self.identity_work_units_dir),
            ("ingestion_operations", self.ingestion_operations_dir),
            ("scope_cohorts", self.scope_cohorts_dir),
            ("encounters", self.encounters_dir),
            ("consolidated_facts", self.consolidated_facts_dir),
        ):
            for path in directory.glob("*.json"):
                path.unlink()
                counts[label] += 1
        return counts

    def clear_projection(self) -> dict[str, int]:
        """Delete entity-owned derived artifacts while preserving sources and claims."""
        counts = {
            "entities": 0,
            "placements": 0,
            "organization_proposals": 0,
            "scope_decisions": 0,
            "retention_records": 0,
            "entity_references": 0,
            "entity_resolution_decisions": 0,
            "identity_maturity_assessments": 0,
            "identity_work_units": 0,
            "scope_cohorts": 0,
            "encounters": 0,
            "consolidated_facts": 0,
            "claims_requeued": 0,
            "dream_commits": 0,
        }
        for label, directory in (
            ("dream_commits", self.dream_commits_dir),
            ("entities", self.entities_dir),
            ("placements", self.placements_dir),
            ("organization_proposals", self.organization_proposals_dir),
            ("scope_decisions", self.scope_decisions_dir),
            ("retention_records", self.retention_records_dir),
            ("entity_references", self.entity_references_dir),
            ("entity_resolution_decisions", self.entity_resolution_decisions_dir),
            ("identity_maturity_assessments", self.identity_maturity_assessments_dir),
            ("identity_work_units", self.identity_work_units_dir),
            ("scope_cohorts", self.scope_cohorts_dir),
            ("encounters", self.encounters_dir),
            ("consolidated_facts", self.consolidated_facts_dir),
        ):
            for path in directory.glob("*.json"):
                path.unlink()
                counts[label] += 1
        for path in self.claims_dir.glob("*.json"):
            data = self._read(path)
            changed = False
            if data.get("status", "active") == "active" and data.get(
                "dream_disposition"
            ) != "excluded_source_policy":
                data["dream_disposition"] = "pending"
                data["dream_disposition_reason"] = "Canonical projection was cleared."
                data["dream_run_id"] = None
                data["dream_disposition_at"] = None
                counts["claims_requeued"] += 1
                changed = True
            if not changed:
                continue
            _atomic_json(path, data)
        return counts

    def list_claims(self, *, status: str | None = None) -> list[MemoryClaim]:
        claims = [self.get_claim(path.stem) for path in sorted(self.claims_dir.glob("*.json"))]
        return [claim for claim in claims if status is None or claim.status == status]

    def list_short_term_claims(
        self, *, include_deferred: bool = True
    ) -> list[MemoryClaim]:
        """Return active claims that have not entered canonical wiki memory.

        Claim disposition is the durable queue state. A placement is consulted as
        an integrity guard so a stale disposition cannot make an already placed
        claim appear in short-term memory.
        """
        allowed = {"pending", "routing_failed"}
        if include_deferred:
            allowed.add("deferred")
        queued = []
        for claim in self.list_claims(status="active"):
            if claim.dream_disposition not in allowed:
                continue
            placement = self.placement_for_claim(claim.claim_id)
            if placement and placement.status == "placed":
                continue
            queued.append(claim)
        return queued

    def memory_tier(self, claim_id: str) -> str:
        claim = self.get_claim(claim_id)
        placement = self.placement_for_claim(claim_id)
        if claim.dream_disposition == "excluded_source_policy":
            return "source"
        if (
            claim.dream_disposition in SHORT_TERM_DISPOSITIONS
            and not (placement and placement.status == "placed")
        ):
            return "short_term"
        return "canonical"

    def claims_for_sources(self, source_ids: Iterable[str], *, active_only: bool = True) -> list[MemoryClaim]:
        wanted = set(source_ids)
        return [
            claim for claim in self.list_claims(status="active" if active_only else None)
            if any(prov.source_id in wanted for prov in claim.provenance)
        ]

    def claims_for_entity(self, entity_id: str) -> list[MemoryClaim]:
        claim_ids = {
            placement.claim_id for placement in self.placements_for_entity(entity_id)
        }
        return [
            claim for claim in self.list_claims(status="active")
            if claim.claim_id in claim_ids
        ]

    def coverage_report(self) -> dict[str, Any]:
        from mycelium.artifact_integrity import coverage_report

        return coverage_report(self)

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
