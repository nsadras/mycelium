"""Discover and review truth changes independently of wiki ownership."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime

from mycelium.artifacts import ArtifactStore, ReconsolidationProposal, temporal_records
from mycelium.budget import ContextBudgetError, require_request_budget
from mycelium.prompting import render_prompt_pair
from mycelium.truth_contract import TruthComparison, truth_candidates_model, truth_comparison_model, truth_comparison_prompt


@dataclass
class TruthReviewResult:
    proposals: list[ReconsolidationProposal] = field(default_factory=list)
    failure_claim_ids: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


class TruthReviewer:
    """Only structured model decisions or exact prior reviews establish meaning."""

    def __init__(self, llm, artifacts: ArtifactStore):
        self.llm, self.artifacts = llm, artifacts

    def _record(self, claim, placements, entities):
        placement = placements.get(claim.claim_id)
        owner = entities.get(placement.owner_entity_id) if placement else None
        citations = []
        for provenance in claim.provenance:
            source = self.artifacts.get_source(provenance.source_id)
            if source.status != "active":
                raise ValueError(f"Claim {claim.claim_id} cites an inactive source")
            segments = {s.segment_id: s for s in source.segments}
            for segment_id in provenance.segment_ids:
                segment = segments[segment_id]
                citations.append({
                    "source_id": source.source_id, "segment_id": segment_id,
                    "source_time": source.occurred_at, "message_time": segment.timestamp,
                    "speaker": segment.speaker, "text": segment.content,
                })
        if not citations:
            raise ValueError(f"Claim {claim.claim_id} has no cited source segments")
        return {
            "claim_id": claim.claim_id, "text": claim.text, "about": claim.about,
            "temporal_status": claim.temporal_status, "temporal": temporal_records(claim.facets),
            "page_owner": {"entity_id": owner.entity_id, "title": owner.title} if owner else None,
            "identity_bindings": [asdict(ref) for ref in self.artifacts.list_entity_references(
                claim_id=claim.claim_id, status="active")],
            "citations": citations,
        }

    async def review(self, incoming_claim_ids, placements, entities, *, dream_run_id):
        result = TruthReviewResult()
        claims = {c.claim_id: c for c in self.artifacts.list_claims(status="active")}
        incoming = sorted(incoming_claim_ids & claims.keys())
        if not incoming or len(claims) < 2:
            return result
        try:
            records = {cid: self._record(c, placements, entities) for cid, c in claims.items()}
            candidates = await self._candidate_pairs(incoming, records)
            reviewed_pairs = {
                tuple(sorted((left, right)))
                for proposal in self.artifacts.list_reconsolidation_proposals()
                if proposal.status in {"pending", "approved", "applied", "rejected"}
                for left in proposal.incoming_claim_ids for right in proposal.target_claim_ids
            }
            pairs = sorted(candidates - reviewed_pairs)
            decisions = await self._compare_pairs(pairs, records)
            changes = {}
            for (left, right), decision in decisions.items():
                relation = decision["relation"]
                if relation == "no_change":
                    continue
                if relation == "left_supersedes_right":
                    retained, target, relation = left, right, "supersedes"
                elif relation == "right_supersedes_left":
                    retained, target, relation = right, left, "supersedes"
                else:
                    retained, target = (right, left) if right in incoming_claim_ids else (left, right)
                changes.setdefault((retained, relation), []).append((target, decision))
            now = datetime.now().astimezone().isoformat()
            for (retained, relation), targets in changes.items():
                target_ids = sorted(target for target, _ in targets)
                sides = {retained, *target_ids}
                affected = {
                    eid for cid in sides if cid in placements
                    for eid in [placements[cid].owner_entity_id, *placements[cid].linked_entity_ids,
                                *placements[cid].page_sections]
                    if eid
                }
                result.proposals.append(ReconsolidationProposal(
                    proposal_id=f"recon-{uuid.uuid4().hex[:12]}", incoming_claim_ids=[retained],
                    target_claim_ids=target_ids, proposed_relation=relation,
                    explanation=json.dumps({target: decision for target, decision in targets}, ensure_ascii=False),
                    confidence=min(claims[cid].confidence for cid in sides),
                    dream_run_id=dream_run_id, created_at=now, affected_entity_ids=sorted(affected),
                    prior_state="\n".join(claims[cid].text for cid in target_ids),
                    incoming_state=claims[retained].text,
                ))
        except Exception as exc:
            result.failure_claim_ids.update(incoming)
            result.errors.append(f"Truth comparison failed: {type(exc).__name__}: {exc}")
        return result

    async def _candidate_pairs(self, incoming, records):
        """Bound each model request without restricting candidates by page owner."""
        pairs = set()
        group_ids = sorted(records)

        async def select(new_ids, other_ids):
            # A statement cannot be its own comparison target. Other statements
            # from the same ingestion cohort remain candidates.
            if len(new_ids) == len(other_ids) == 1 and new_ids == other_ids:
                return
            incoming_aliases = {f"C{i:03d}": cid for i, cid in enumerate(new_ids, 1)}
            group_aliases = {f"X{i:03d}": cid for i, cid in enumerate(other_ids, 1)}
            allowed = {alias: [target for target, target_id in group_aliases.items() if cid != target_id]
                       for alias, cid in incoming_aliases.items()}
            incoming_aliases = {a: cid for a, cid in incoming_aliases.items() if allowed[a]}
            allowed = {a: allowed[a] for a in incoming_aliases}
            if not allowed:
                return
            schema = truth_candidates_model(allowed)
            system, user = render_prompt_pair("memory/truth_candidates", payload=json.dumps({
                "incoming": {a: records[c] for a, c in incoming_aliases.items()},
                "candidates": {a: records[c] for a, c in group_aliases.items()},
                "eligible_candidates": allowed,
            }, ensure_ascii=False))
            try:
                require_request_budget([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                       context_window=self.llm.context_window_tokens, output_tokens=4096,
                                       schema=schema.model_json_schema())
            except ContextBudgetError:
                if len(other_ids) > 1:
                    middle = len(other_ids) // 2
                    await select(new_ids, other_ids[:middle])
                    await select(new_ids, other_ids[middle:])
                elif len(new_ids) > 1:
                    middle = len(new_ids) // 2
                    await select(new_ids[:middle], other_ids)
                    await select(new_ids[middle:], other_ids)
                else:
                    raise
                return
            response = schema.model_validate(await self.llm.call_structured(
                system, user, schema, num_predict=4096, debug_label="dream-truth-candidates",
            )).model_dump()["decisions"]
            for alias, decision in response.items():
                for target, relevance in decision["candidates"].items():
                    if relevance == "unrelated":
                        continue
                    left, right = incoming_aliases[alias], group_aliases[target]
                    pairs.add(tuple(sorted((left, right))))

        for start in range(0, len(incoming), 12):
            for other in range(0, len(group_ids), 12):
                await select(incoming[start:start + 12], group_ids[other:other + 12])
        return pairs

    async def _compare_pairs(self, pairs, records):
        decisions = {}

        async def compare(batch):
            aliases = {f"P{i:03d}": pair for i, pair in enumerate(batch, 1)}
            schema = truth_comparison_model(aliases)
            system, user = truth_comparison_prompt(json.dumps({alias: {
                "left": records[left], "right": records[right],
            } for alias, (left, right) in aliases.items()}, ensure_ascii=False))
            output_budget = self.llm.output_budget(4096, think=True)
            try:
                require_request_budget([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                       context_window=self.llm.context_window_tokens, output_tokens=output_budget,
                                       schema=schema.model_json_schema())
            except ContextBudgetError:
                if len(batch) == 1:
                    raise
                middle = len(batch) // 2
                await compare(batch[:middle])
                await compare(batch[middle:])
                return
            response = schema.model_validate(await self.llm.call_structured(
                system, user, schema, num_predict=4096, debug_label="dream-truth-comparison", think=True,
            )).model_dump()["comparisons"]
            decisions.update({aliases[alias]: TruthComparison.model_validate(value).model_dump()
                              for alias, value in response.items()})

        for start in range(0, len(pairs), 12):
            await compare(pairs[start:start + 12])
        return decisions
