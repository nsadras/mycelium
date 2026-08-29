"""Human review for owner-scoped truth-change proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mycelium.artifacts import ArtifactStore, MemoryClaim, ReconsolidationProposal
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer


@dataclass(frozen=True)
class ReviewResult:
    proposal: ReconsolidationProposal
    pages_updated: list[str]
    pages_deleted: list[str]


class ReviewConflictError(RuntimeError):
    """The proposal can no longer be safely reviewed."""


def add_claim_link(claim: MemoryClaim, relation: str, target: str) -> None:
    link = {"relation": relation, "target": target}
    if link not in claim.links:
        claim.links.append(link)


class ReconsolidationReviewService:
    """Apply reviewed truth changes, then rerun the canonical fact resolver."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        materializer: PageMaterializer,
        resolver: FactResolver,
    ) -> None:
        self.artifacts = artifacts
        self.materializer = materializer
        self.resolver = resolver

    async def approve(
        self, proposal_id: str, *, reviewer_note: str | None = None
    ) -> ReviewResult:
        proposal = self.artifacts.get_reconsolidation_proposal(proposal_id)
        if proposal.status == "applied":
            return ReviewResult(proposal, [], [])
        if proposal.status == "rejected":
            raise ReviewConflictError("A rejected proposal cannot be approved")
        incoming, targets = self._load_claims(proposal)
        already_mutated = self._approved_relation_is_present(
            proposal, incoming, targets
        )
        if any(claim.status != "active" for claim in incoming) or any(
            claim.status != "active" for claim in targets
        ) and not already_mutated:
            self._mark_stale(proposal, "A referenced claim is no longer active")
            raise ReviewConflictError("A referenced claim is no longer active")
        if proposal.status == "pending":
            proposal.status = "approved"
            proposal.reviewer_note = reviewer_note
            proposal.reviewed_at = datetime.now().astimezone().isoformat()
        proposal.application_error = None
        self.artifacts.save_reconsolidation_proposal(proposal)
        try:
            if not already_mutated:
                self._apply_relation(proposal, incoming, targets)
            pages = await self._rebuild(proposal)
            proposal.status = "applied"
            proposal.applied_at = datetime.now().astimezone().isoformat()
            self.artifacts.save_reconsolidation_proposal(proposal)
            return ReviewResult(
                proposal,
                sorted(pages.updated_slugs | pages.created_slugs),
                sorted(pages.deleted_slugs),
            )
        except Exception as exc:
            proposal.application_error = f"{type(exc).__name__}: {exc}"
            self.artifacts.save_reconsolidation_proposal(proposal)
            raise

    async def reject(
        self, proposal_id: str, *, reviewer_note: str | None = None
    ) -> ReviewResult:
        proposal = self.artifacts.get_reconsolidation_proposal(proposal_id)
        if proposal.status == "rejected" and not proposal.application_error:
            return ReviewResult(proposal, [], [])
        if proposal.status in {"approved", "applied"}:
            raise ReviewConflictError("An approved proposal cannot be rejected")
        if proposal.status == "pending":
            proposal.status = "rejected"
            proposal.reviewer_note = reviewer_note
            proposal.reviewed_at = datetime.now().astimezone().isoformat()
        proposal.application_error = None
        self.artifacts.save_reconsolidation_proposal(proposal)
        try:
            pages = await self._rebuild(proposal)
            self.artifacts.save_reconsolidation_proposal(proposal)
            return ReviewResult(
                proposal,
                sorted(pages.updated_slugs | pages.created_slugs),
                sorted(pages.deleted_slugs),
            )
        except Exception as exc:
            proposal.application_error = f"{type(exc).__name__}: {exc}"
            self.artifacts.save_reconsolidation_proposal(proposal)
            raise

    def _load_claims(
        self, proposal: ReconsolidationProposal
    ) -> tuple[list[MemoryClaim], list[MemoryClaim]]:
        try:
            incoming = [
                self.artifacts.get_claim(claim_id)
                for claim_id in proposal.incoming_claim_ids
            ]
            targets = [
                self.artifacts.get_claim(claim_id)
                for claim_id in proposal.target_claim_ids
            ]
        except FileNotFoundError as exc:
            self._mark_stale(proposal, "A referenced claim no longer exists")
            raise ReviewConflictError("A referenced claim no longer exists") from exc
        return incoming, targets

    def _apply_relation(
        self,
        proposal: ReconsolidationProposal,
        incoming: list[MemoryClaim],
        targets: list[MemoryClaim],
    ) -> None:
        for new_claim in incoming:
            for target in targets:
                if proposal.proposed_relation == "contradicts":
                    add_claim_link(new_claim, "contradicts", target.claim_id)
                    add_claim_link(target, "contradicts", new_claim.claim_id)
                else:
                    target.status = "superseded"
                    add_claim_link(new_claim, "supersedes", target.claim_id)
                    add_claim_link(target, "superseded_by", new_claim.claim_id)
                self.artifacts.save_claim(target)
            self.artifacts.save_claim(new_claim)

    async def _rebuild(self, proposal: ReconsolidationProposal):
        resolution = await self.resolver.resolve(
            [],
            affected_entity_ids=set(proposal.affected_entity_ids),
            incoming_claim_ids=set(),
            dream_run_id=f"review-{proposal.proposal_id}",
        )
        if resolution.failures:
            raise ReviewConflictError(resolution.failures[0].reason)
        for placement in resolution.placements:
            self.artifacts.save_placement(placement)
        for fact_id in resolution.deleted_fact_ids:
            self.artifacts.delete_consolidated_fact(fact_id)
        for fact in resolution.facts:
            self.artifacts.save_consolidated_fact(fact)
        return self.materializer.regenerate(set(proposal.affected_entity_ids))

    @staticmethod
    def _approved_relation_is_present(
        proposal: ReconsolidationProposal,
        incoming: list[MemoryClaim],
        targets: list[MemoryClaim],
    ) -> bool:
        if proposal.status != "approved":
            return False
        for new_claim in incoming:
            for target in targets:
                if proposal.proposed_relation == "contradicts":
                    if (
                        {"relation": "contradicts", "target": target.claim_id}
                        not in new_claim.links
                        or {"relation": "contradicts", "target": new_claim.claim_id}
                        not in target.links
                    ):
                        return False
                elif (
                    target.status != "superseded"
                    or {"relation": "supersedes", "target": target.claim_id}
                    not in new_claim.links
                    or {"relation": "superseded_by", "target": new_claim.claim_id}
                    not in target.links
                ):
                    return False
        return True

    def _mark_stale(self, proposal: ReconsolidationProposal, reason: str) -> None:
        proposal.status = "stale"
        proposal.application_error = reason
        proposal.reviewed_at = datetime.now().astimezone().isoformat()
        self.artifacts.save_reconsolidation_proposal(proposal)
