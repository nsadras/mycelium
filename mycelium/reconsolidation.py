"""Evidence-triggered reconsolidation of canonical memory claims."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from mycelium import prompts
from mycelium.artifacts import (
    ArtifactStore,
    ConsolidatedFact,
    MemoryClaim,
    ReconsolidationProposal,
    temporal_record,
)
from mycelium.consolidation import ClaimRoute
from mycelium.materialization import PageMaterializer
from mycelium.ollama import OllamaClient
from mycelium.projection import display_claim_text
from mycelium.structured_outputs import ReconsolidationDecisionsOutput


@dataclass(frozen=True)
class ReconciliationFailure:
    claim_id: str
    raw_log_entry_id: str
    reason: str


@dataclass(frozen=True)
class SupportingRelation:
    incoming_claim_id: str
    target_claim_id: str


@dataclass
class ReconciliationResult:
    supporting_relations: list[SupportingRelation] = field(default_factory=list)
    proposals: list[ReconsolidationProposal] = field(default_factory=list)
    failures: list[ReconciliationFailure] = field(default_factory=list)


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


class ClaimReconsolidator:
    """Classify new claims against bounded, deterministic existing candidates."""

    def __init__(self, llm: OllamaClient, artifacts: ArtifactStore):
        self.llm = llm
        self.artifacts = artifacts

    async def analyze(
        self,
        routes: list[ClaimRoute],
        *,
        current_claim_ids: set[str],
        dream_run_id: str,
    ) -> ReconciliationResult:
        result = ReconciliationResult()
        active = self.artifacts.list_claims(status="active")
        current_ids = set(current_claim_ids)
        existing = [claim for claim in active if claim.claim_id not in current_ids]

        for route in routes:
            if route.claim_id not in current_ids:
                continue
            try:
                incoming = self.artifacts.get_claim(route.claim_id)
            except FileNotFoundError:
                result.failures.append(ReconciliationFailure(
                    route.claim_id,
                    route.raw_log_entry_id,
                    "Incoming claim artifact is missing",
                ))
                continue
            candidates = self._candidates(incoming, route.owner_entity_id, existing)
            if not candidates:
                continue
            relation = await self._classify(incoming, candidates)
            if isinstance(relation, str):
                result.failures.append(ReconciliationFailure(
                    route.claim_id, route.raw_log_entry_id, relation
                ))
                continue
            relation_name, target, explanation, confidence = relation
            if relation_name == "additive":
                continue
            if relation_name == "supports":
                result.supporting_relations.append(SupportingRelation(
                    incoming.claim_id, target.claim_id
                ))
                continue
            existing_proposal = self.artifacts.find_reconsolidation_proposal(
                incoming.claim_id, target.claim_id, relation_name
            )
            if existing_proposal is not None:
                continue
            result.proposals.append(ReconsolidationProposal(
                proposal_id=f"recon-{uuid.uuid4().hex[:12]}",
                incoming_claim_id=incoming.claim_id,
                target_claim_id=target.claim_id,
                proposed_relation=relation_name,
                explanation=explanation,
                confidence=confidence,
                dream_run_id=dream_run_id,
                created_at=datetime.now().astimezone().isoformat(),
                affected_entity_ids=sorted({
                    entity_id
                    for entity_id in (
                        route.owner_entity_id,
                        self._owner_id(incoming.claim_id),
                        self._owner_id(target.claim_id),
                    )
                    if entity_id
                }),
            ))
        return result

    def _candidates(
        self,
        incoming: MemoryClaim,
        owner_entity_id: str | None,
        existing: list[MemoryClaim],
    ) -> list[MemoryClaim]:
        incoming_entities = self._entities(incoming)
        if not incoming_entities:
            return []
        candidates = [
            claim for claim in existing
            if incoming_entities & self._entities(claim)
            and self._temporal_roles_compatible(incoming, claim)
            and (
                self._owner_id(claim.claim_id) == owner_entity_id
                or bool(incoming.slot and claim.slot == incoming.slot)
            )
        ]
        return sorted(
            candidates,
            key=lambda claim: self._candidate_rank(incoming, claim),
            reverse=True,
        )[:12]

    def _owner_id(self, claim_id: str) -> str | None:
        placement = self.artifacts.placement_for_claim(claim_id)
        return placement.owner_entity_id if placement else None

    @staticmethod
    def _candidate_rank(
        incoming: MemoryClaim, candidate: MemoryClaim
    ) -> tuple[int, int, int, int, str]:
        incoming_temporal = temporal_record(incoming.facets)
        candidate_temporal = temporal_record(candidate.facets)
        return (
            int(bool(incoming.slot and candidate.slot == incoming.slot)),
            int(bool(incoming.predicate and candidate.predicate == incoming.predicate)),
            int(incoming.claim_type == candidate.claim_type),
            int(bool(
                incoming_temporal
                and candidate_temporal
                and incoming_temporal.get("role") == candidate_temporal.get("role")
            )),
            candidate.recorded_at,
        )

    @staticmethod
    def _temporal_roles_compatible(
        incoming: MemoryClaim, candidate: MemoryClaim
    ) -> bool:
        incoming_temporal = temporal_record(incoming.facets)
        candidate_temporal = temporal_record(candidate.facets)
        if incoming_temporal is None or candidate_temporal is None:
            return True
        return incoming_temporal.get("role", "event_time") == candidate_temporal.get(
            "role", "event_time"
        )

    async def _classify(
        self, incoming: MemoryClaim, candidates: list[MemoryClaim]
    ) -> tuple[str, MemoryClaim, str, float] | str:
        aliases = {f"E{index:03d}": claim for index, claim in enumerate(candidates, start=1)}
        candidate_text = "\n".join(
            f"[{alias}] type={claim.claim_type}; predicate={claim.predicate or 'unknown'}; "
            f"slot={claim.slot or 'none'}; recorded_at={claim.recorded_at}; "
            f"temporal={self._temporal_summary(claim)}\n{claim.text}"
            for alias, claim in aliases.items()
        )
        system, user = prompts.claim_reconsolidation_prompt(
            "N001",
            (
                f"type={incoming.claim_type}; predicate={incoming.predicate or 'unknown'}; "
                f"slot={incoming.slot or 'none'}; recorded_at={incoming.recorded_at}; "
                f"temporal={self._temporal_summary(incoming)}\n"
                f"{incoming.text}"
            ),
            candidate_text,
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                ReconsolidationDecisionsOutput,
                num_predict=1024,
                debug_label="dream-claim-reconsolidation",
            )
        except Exception as exc:
            return f"Reconsolidation request failed: {type(exc).__name__}"
        decisions = response.get("decisions", []) if isinstance(response, dict) else []
        if len(decisions) != 1 or decisions[0].get("incoming_alias") != "N001":
            return "Reconsolidation response did not account for the incoming claim exactly once"
        decision = decisions[0]
        relation = str(decision.get("relation", ""))
        target_alias = str(decision.get("target_alias", ""))
        if relation == "additive":
            if target_alias:
                return "Additive reconsolidation decision included a target"
            return relation, incoming, str(decision.get("explanation", "")), float(
                decision.get("confidence", 0.8)
            )
        target = aliases.get(target_alias)
        if relation not in {"supports", "contradicts", "supersedes"} or target is None:
            return "Reconsolidation decision used an invalid relation or target"
        return (
            relation,
            target,
            str(decision.get("explanation", "")).strip(),
            max(0.0, min(1.0, float(decision.get("confidence", 0.8)))),
        )

    @staticmethod
    def _temporal_summary(claim: MemoryClaim) -> str:
        temporal = temporal_record(claim.facets)
        if temporal is None:
            return "none"
        return ",".join(
            f"{key}={temporal[key]}"
            for key in ("role", "status", "start", "end", "certainty", "expression")
            if temporal.get(key) is not None
        )

    @staticmethod
    def _entities(claim: MemoryClaim) -> set[str]:
        return {
            re.sub(r"[^a-z0-9]+", " ", str(item.get("entity", "")).lower()).strip()
            for item in claim.about
            if item.get("entity")
        }


class ReconsolidationReviewService:
    """Apply a reviewed proposal through canonical claims and deterministic projection."""

    def __init__(self, artifacts: ArtifactStore, materializer: PageMaterializer):
        self.artifacts = artifacts
        self.materializer = materializer

    def approve(self, proposal_id: str, *, reviewer_note: str | None = None) -> ReviewResult:
        proposal = self.artifacts.get_reconsolidation_proposal(proposal_id)
        if proposal.status == "applied":
            return ReviewResult(proposal, [], [])
        if proposal.status == "rejected":
            raise ReviewConflictError("A rejected proposal cannot be approved")
        try:
            incoming = self.artifacts.get_claim(proposal.incoming_claim_id)
            target = self.artifacts.get_claim(proposal.target_claim_id)
        except FileNotFoundError as exc:
            self._mark_stale(proposal, "A referenced claim no longer exists")
            raise ReviewConflictError("A referenced claim no longer exists") from exc
        already_mutated = self._approved_relation_is_present(proposal, incoming, target)
        if incoming.status != "active" or (
            target.status != "active" and not already_mutated
        ):
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
                if proposal.proposed_relation == "contradicts":
                    add_claim_link(incoming, "contradicts", target.claim_id)
                    add_claim_link(target, "contradicts", incoming.claim_id)
                else:
                    target.status = "superseded"
                    add_claim_link(incoming, "supersedes", target.claim_id)
                    add_claim_link(target, "superseded_by", incoming.claim_id)
                self.artifacts.save_claim(incoming)
                self.artifacts.save_claim(target)
            if proposal.proposed_relation == "supersedes":
                self._remove_superseded_fact_views(target.claim_id)
            pages = self.materializer.regenerate(set(proposal.affected_entity_ids))
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

    def reject(self, proposal_id: str, *, reviewer_note: str | None = None) -> ReviewResult:
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
            pages = self.materializer.regenerate(set(proposal.affected_entity_ids))
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

    @staticmethod
    def _approved_relation_is_present(
        proposal: ReconsolidationProposal,
        incoming: MemoryClaim,
        target: MemoryClaim,
    ) -> bool:
        if proposal.status != "approved":
            return False
        if proposal.proposed_relation == "contradicts":
            return (
                {"relation": "contradicts", "target": target.claim_id} in incoming.links
                and {"relation": "contradicts", "target": incoming.claim_id} in target.links
            )
        return (
            target.status == "superseded"
            and {"relation": "supersedes", "target": target.claim_id} in incoming.links
            and {"relation": "superseded_by", "target": incoming.claim_id} in target.links
        )

    def _mark_stale(self, proposal: ReconsolidationProposal, reason: str) -> None:
        proposal.status = "stale"
        proposal.application_error = reason
        proposal.reviewed_at = datetime.now().astimezone().isoformat()
        self.artifacts.save_reconsolidation_proposal(proposal)

    def _remove_superseded_fact_views(self, claim_id: str) -> None:
        """Delete obsolete display facts without deleting their canonical claims."""
        now = datetime.now().astimezone().isoformat()
        for fact in self.artifacts.facts_for_claim(claim_id):
            self.artifacts.delete_consolidated_fact(fact.fact_id)
            for member_id in fact.member_claim_ids:
                if member_id == claim_id:
                    continue
                try:
                    member = self.artifacts.get_claim(member_id)
                except FileNotFoundError:
                    continue
                placement = self.artifacts.placement_for_claim(member_id)
                if (
                    member.status != "active"
                    or placement is None
                    or placement.status != "placed"
                    or not placement.owner_entity_id
                    or not placement.section_key
                ):
                    continue
                self.artifacts.save_consolidated_fact(ConsolidatedFact(
                    fact_id=f"fact-{uuid.uuid4().hex[:12]}",
                    text=display_claim_text(member),
                    member_claim_ids=[member.claim_id],
                    owner_entity_id=placement.owner_entity_id,
                    section_key=placement.section_key,
                    linked_entity_ids=list(placement.linked_entity_ids),
                    synthesis_origin="claim",
                    confidence=member.confidence,
                    reason="Separated after a supporting memory was superseded.",
                    created_at=now,
                    updated_at=now,
                ))
