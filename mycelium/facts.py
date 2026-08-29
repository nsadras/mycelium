"""Grounded presentation facts above canonical claims and below wiki pages."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from mycelium import prompts
from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ConsolidatedFact,
    MemoryClaim,
)
from mycelium.ollama import OllamaClient
from mycelium.projection import display_claim_text
from mycelium.structured_outputs import ConsolidatedFactPlanOutput


@dataclass
class FactConsolidationResult:
    facts: list[ConsolidatedFact] = field(default_factory=list)
    deleted_fact_ids: set[str] = field(default_factory=set)
    failures: list[str] = field(default_factory=list)


class FactConsolidator:
    """Produce stable, editable display facts while preserving source claims."""

    def __init__(self, llm: OllamaClient, artifacts: ArtifactStore):
        self.llm = llm
        self.artifacts = artifacts

    async def consolidate(
        self,
        placements: list[ClaimPlacement],
        *,
        affected_entity_ids: set[str],
        pending_claim_ids: set[str],
    ) -> FactConsolidationResult:
        result = FactConsolidationResult()
        if not affected_entity_ids:
            return result
        placement_by_claim = {
            item.claim_id: item
            for item in [*self.artifacts.list_placements(), *placements]
        }
        claims = {
            claim.claim_id: claim
            for claim in self.artifacts.list_claims(status="active")
            if not claim.derivation_operation
        }
        existing = [
            fact for fact in self.artifacts.list_consolidated_facts()
            if fact.owner_entity_id in affected_entity_ids
        ]
        manual = [
            fact for fact in existing
            if fact.synthesis_origin == "manual"
            and all(
                self._placement_matches_fact(placement_by_claim.get(claim_id), fact)
                for claim_id in fact.member_claim_ids
            )
        ]
        reserved_claim_ids = {
            claim_id
            for fact in manual
            for claim_id in fact.member_claim_ids
            if self._placement_matches_fact(placement_by_claim.get(claim_id), fact)
        }
        result.facts.extend(manual)
        buckets: dict[tuple[str, str], list[tuple[MemoryClaim, ClaimPlacement]]] = {}
        for claim_id, placement in placement_by_claim.items():
            claim = claims.get(claim_id)
            if (
                claim is None
                or claim_id in reserved_claim_ids
                or placement.status != "placed"
                or not placement.owner_entity_id
                or not placement.section_key
                or placement.owner_entity_id not in affected_entity_ids
            ):
                continue
            buckets.setdefault(
                (placement.owner_entity_id, placement.section_key), []
            ).append((claim, placement))

        available_existing = [
            fact for fact in existing if fact.synthesis_origin != "manual"
        ]
        used_existing: set[str] = set()
        for (owner, section), values in sorted(buckets.items()):
            groups: list[tuple[list[tuple[MemoryClaim, ClaimPlacement]], str, float, str]]
            if len(values) == 1 or any(
                claim.claim_id in pending_claim_ids for claim, _ in values
            ):
                groups = [
                    ([value], display_claim_text(value[0]), value[0].confidence,
                     "One independently useful source claim.")
                    for value in values
                ]
            else:
                groups = await self._plan_bucket(owner, section, values, result)
            for members, text, confidence, reason in groups:
                member_ids = {claim.claim_id for claim, _ in members}
                prior = self._best_prior_fact(
                    member_ids, owner, section, available_existing, used_existing
                )
                now = datetime.now().astimezone().isoformat()
                fact = ConsolidatedFact(
                    fact_id=prior.fact_id if prior else f"fact-{uuid.uuid4().hex[:12]}",
                    text=text,
                    member_claim_ids=sorted(member_ids),
                    owner_entity_id=owner,
                    section_key=section,
                    linked_entity_ids=sorted({
                        linked_id for _, placement in members
                        for linked_id in placement.linked_entity_ids
                    }),
                    synthesis_origin="model" if len(members) > 1 else "claim",
                    confidence=confidence,
                    reason=reason,
                    created_at=prior.created_at if prior else now,
                    updated_at=now,
                    manual_text=False,
                )
                result.facts.append(fact)
                if prior:
                    used_existing.add(prior.fact_id)
        result.deleted_fact_ids = {
            fact.fact_id for fact in existing
            if fact.fact_id not in {value.fact_id for value in result.facts}
        }
        return result

    async def _plan_bucket(
        self,
        owner: str,
        section: str,
        values: list[tuple[MemoryClaim, ClaimPlacement]],
        result: FactConsolidationResult,
    ) -> list[tuple[list[tuple[MemoryClaim, ClaimPlacement]], str, float, str]]:
        aliases = {
            f"F{index:03d}": value for index, value in enumerate(values, start=1)
        }
        evidence = "\n\n".join(
            f"[{alias}] owner={owner}; section={section}; type={claim.claim_type}; "
            f"temporal={claim.temporal_status}\nclaim={claim.text}"
            f"\nnormalized_display={display_claim_text(claim)}"
            for alias, (claim, _) in aliases.items()
        )
        system, user = prompts.consolidated_fact_prompt(evidence)
        try:
            response = await self.llm.call_structured(
                system,
                user,
                ConsolidatedFactPlanOutput,
                num_predict=4096,
                debug_label="dream-fact-consolidation",
            )
            plan = ConsolidatedFactPlanOutput.model_validate(response)
            flattened = [alias for fact in plan.facts for alias in fact.claim_aliases]
            if len(flattened) != len(set(flattened)) or set(flattened) != set(aliases):
                raise ValueError("Fact plan must cover each claim alias exactly once")
            grouped = []
            for fact in plan.facts:
                members = [aliases[alias] for alias in fact.claim_aliases]
                if not self._grounded(fact.text, [claim for claim, _ in members]):
                    raise ValueError("Synthesized fact omitted or introduced a hard anchor")
                grouped.append((members, fact.text, fact.confidence, fact.reason))
            return grouped
        except Exception as exc:
            result.failures.append(
                f"Fact synthesis for {owner}/{section} was rejected: {type(exc).__name__}"
            )
            return [
                ([value], display_claim_text(value[0]), value[0].confidence,
                 "Kept as an independent fact after synthesis validation.")
                for value in values
            ]

    @staticmethod
    def _placement_matches_fact(
        placement: ClaimPlacement | None, fact: ConsolidatedFact
    ) -> bool:
        return bool(
            placement
            and placement.status == "placed"
            and placement.owner_entity_id == fact.owner_entity_id
            and placement.section_key == fact.section_key
        )

    @staticmethod
    def _best_prior_fact(
        member_ids: set[str],
        owner: str,
        section: str,
        existing: list[ConsolidatedFact],
        used: set[str],
    ) -> ConsolidatedFact | None:
        candidates = [
            fact for fact in existing
            if fact.fact_id not in used
            and fact.owner_entity_id == owner
            and fact.section_key == section
            and member_ids & set(fact.member_claim_ids)
        ]
        return max(
            candidates,
            key=lambda fact: (
                len(member_ids & set(fact.member_claim_ids))
                / len(member_ids | set(fact.member_claim_ids)),
                fact.updated_at,
            ),
            default=None,
        )

    @classmethod
    def _grounded(cls, text: str, claims: list[MemoryClaim]) -> bool:
        source = " ".join(display_claim_text(claim) for claim in claims)
        return cls._hard_anchors(source) == cls._hard_anchors(text)

    @staticmethod
    def _hard_anchors(text: str) -> set[str]:
        return {
            value.lower()
            for value in re.findall(
                r"\b(?:\d+(?:\.\d+)?%?|20\d{2}(?:-\d{2}-\d{2})?|"
                r"(?:mon|tues|wednes|thurs|fri|satur|sun)day|"
                r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b",
                text,
                flags=re.IGNORECASE,
            )
        }
