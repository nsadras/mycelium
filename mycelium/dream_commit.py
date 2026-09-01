"""Replayable filesystem commit for a completed Dream decision plan."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimPlacement,
    ClaimScopeDecision,
    ConsolidatedFact,
    DreamClaimDecision,
    DreamCommit,
    DreamRunAudit,
    EntityEncounter,
    EntityRecord,
    EntityResolutionDecision,
    IdentityMaturityAssessment,
    NonWikiRetentionRecord,
    ReconsolidationProposal,
    ScopeCohort,
)
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.store import LogStore


class DreamCommitService:
    """Persist a Dream write set before applying any part of it."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        logs: LogStore,
        materializer: PageMaterializer,
    ) -> None:
        self.artifacts = artifacts
        self.logs = logs
        self.materializer = materializer

    def prepare(
        self,
        *,
        run_id: str,
        materialization: MaterializationResult,
        retention_records: list[NonWikiRetentionRecord],
        entity_decisions: list[EntityResolutionDecision],
        maturity_assessments: list[IdentityMaturityAssessment],
        entity_references: list[ClaimEntityReference],
        encounters: list[EntityEncounter],
        scope_decisions: list[ClaimScopeDecision],
        proposals: list[ReconsolidationProposal],
        cohort: ScopeCohort,
        affected_entity_ids: set[str],
        completed_log_entry_ids: list[str],
        audit: DreamRunAudit,
    ) -> DreamCommit:
        now = datetime.now().astimezone().isoformat()
        commit = DreamCommit(
            commit_id=f"dream-commit-{run_id}",
            run_id=run_id,
            status="prepared",
            payload={
                "entities": [asdict(item) for item in materialization.entities.values()],
                "placements": [asdict(item) for item in materialization.placements.values()],
                "facts": [asdict(item) for item in materialization.facts.values()],
                "deleted_fact_ids": sorted(materialization.deleted_fact_ids),
                "retention_records": [asdict(item) for item in retention_records],
                "entity_decisions": [asdict(item) for item in entity_decisions],
                "maturity_assessments": [asdict(item) for item in maturity_assessments],
                "entity_references": [asdict(item) for item in entity_references],
                "encounters": [asdict(item) for item in encounters],
                "scope_decisions": [asdict(item) for item in scope_decisions],
                "proposals": [asdict(item) for item in proposals],
                "cohort": asdict(cohort),
                "affected_entity_ids": sorted(affected_entity_ids),
                "completed_log_entry_ids": sorted(set(completed_log_entry_ids)),
                "audit": asdict(audit),
            },
            created_at=now,
            updated_at=now,
        )
        self.artifacts.save_dream_commit(commit)
        return commit

    def apply(self, commit: DreamCommit) -> MaterializationResult:
        if commit.status == "complete":
            return MaterializationResult()
        commit.status = "applying"
        commit.error = None
        commit.updated_at = datetime.now().astimezone().isoformat()
        self.artifacts.save_dream_commit(commit)
        payload = commit.payload
        try:
            for raw in payload["entities"]:
                self.artifacts.save_entity(EntityRecord(**raw))
            for raw in payload["placements"]:
                self.artifacts.save_placement(ClaimPlacement(**raw))
            for fact_id in payload["deleted_fact_ids"]:
                self.artifacts.delete_consolidated_fact(fact_id)
            for raw in payload["facts"]:
                self.artifacts.save_consolidated_fact(ConsolidatedFact(**raw))
            for raw in payload["proposals"]:
                self.artifacts.save_reconsolidation_proposal(
                    ReconsolidationProposal(**raw)
                )
            for raw in payload["retention_records"]:
                self.artifacts.save_retention_record(NonWikiRetentionRecord(**raw))
            for raw in payload["entity_decisions"]:
                self.artifacts.save_entity_resolution_decision(
                    EntityResolutionDecision(**raw)
                )
            for raw in payload["maturity_assessments"]:
                self.artifacts.save_identity_maturity_assessment(
                    IdentityMaturityAssessment(**raw)
                )
            for raw in payload["entity_references"]:
                self.artifacts.save_entity_reference(ClaimEntityReference(**raw))
            for raw in payload["encounters"]:
                self.artifacts.save_encounter(EntityEncounter(**raw))
            for raw in payload["scope_decisions"]:
                self.artifacts.save_scope_decision(ClaimScopeDecision(**raw))
            self.artifacts.save_scope_cohort(ScopeCohort(**payload["cohort"]))
            pages = self.materializer.regenerate(set(payload["affected_entity_ids"]))
            self.logs.mark_consolidated(payload["completed_log_entry_ids"])
            audit_data = dict(payload["audit"])
            audit_data["claim_decisions"] = [
                DreamClaimDecision(**raw)
                for raw in audit_data.get("claim_decisions", [])
            ]
            self.artifacts.persist_dream_audit(DreamRunAudit(**audit_data))
            commit.status = "complete"
            commit.error = None
            commit.updated_at = datetime.now().astimezone().isoformat()
            self.artifacts.save_dream_commit(commit)
            return pages
        except Exception as exc:
            commit.error = f"{type(exc).__name__}: {exc}"
            commit.updated_at = datetime.now().astimezone().isoformat()
            self.artifacts.save_dream_commit(commit)
            raise

    def recover_pending(self) -> list[str]:
        recovered = []
        for commit in self.artifacts.list_dream_commits():
            if commit.status == "complete":
                continue
            self.apply(commit)
            recovered.append(commit.commit_id)
        return recovered
