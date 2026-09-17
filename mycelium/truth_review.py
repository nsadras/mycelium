"""Discover and review truth changes independently of wiki ownership."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from mycelium.artifacts import ArtifactStore, ReconsolidationProposal, temporal_records
from mycelium.artifact_integrity import cited_source_segments
from mycelium.budget import ContextBudgetError, require_request_budget
from mycelium.config import Config
from mycelium.claim_index import OllamaEmbedder
from mycelium.prompting import render_prompt_pair
from mycelium.semantic_candidates import SemanticCandidates
from mycelium.truth_contract import (
    TruthComparison,
    truth_candidates_model,
    truth_comparison_model,
    truth_comparison_prompt,
)


@dataclass
class TruthReviewResult:
    proposals: list[ReconsolidationProposal] = field(default_factory=list)
    failure_claim_ids: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


class TruthReviewer:
    """Only structured model decisions or exact prior reviews establish meaning."""

    _GLOBAL_CANDIDATES = 32
    _ENTITY_CANDIDATES = 16

    def __init__(self, llm, artifacts: ArtifactStore, config: Config):
        self.llm, self.artifacts = llm, artifacts
        self.config = config
        self.candidates = None
        self.candidate_trace = {}

    def _record(self, claim, sources, reference_replacements):
        citations, withdrawn = [], []
        for _, source, segments in cited_source_segments(
            self.artifacts, claim, source_cache=sources
        ):
            if source.status != "active":
                withdrawn.extend(
                    {
                        "source_id": source.source_id,
                        "segment_id": segment.segment_id,
                        "status": source.status,
                    }
                    for segment in segments
                )
                continue
            for segment in segments:
                citations.append(
                    {
                        "source_id": source.source_id,
                        "segment_id": segment.segment_id,
                        "source_time": source.occurred_at,
                        "message_time": segment.timestamp,
                        "speaker": segment.speaker,
                        "text": segment.content,
                    }
                )
        if not citations:
            raise ValueError(f"Claim {claim.claim_id} cites no active source support")
        bindings = self.artifacts.list_entity_references(
            claim_id=claim.claim_id, status="active"
        )
        if claim.claim_id in reference_replacements:
            # Match the commit's exact replacement scope. An empty replacement
            # clears stale automatic bindings; explicit human reviews survive.
            bindings = [ref for ref in bindings if ref.origin == "manual"] + list(
                reference_replacements[claim.claim_id]
            )
        if len({ref.reference_id for ref in bindings}) != len(bindings):
            raise ValueError("Truth identity context contains duplicate reference IDs")
        # Presentation ownership and recreated build bookkeeping cannot establish
        # identity or change a truth decision. Preserve all semantic fields and
        # explicit review IDs; the complete references remain in the audit store.
        semantic_bindings = {
            json.dumps(
                {
                    key: getattr(ref, key)
                    for key in (
                        "role",
                        "surface",
                        "entity_id",
                        "confidence",
                        "reason",
                        "origin",
                        "identity_decision_id",
                    )
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            for ref in bindings
            if ref.role != "canonical_owner"
            and (not withdrawn or ref.origin == "manual")
        }
        return {
            # A partially withdrawn synthesis may contain unsupported details.
            # Compare the remaining source assertions directly. Canonical text,
            # bindings and all historical citations remain intact in the store.
            "claim_id": claim.claim_id,
            "text": None if withdrawn else claim.text,
            "about": [] if withdrawn else claim.about,
            "temporal_status": "uncertain" if withdrawn else claim.temporal_status,
            "temporal": [] if withdrawn else temporal_records(claim.facets),
            "identity_bindings": [
                json.loads(value) for value in sorted(semantic_bindings)
            ],
            "citations": citations,
            "withdrawn_citations": withdrawn,
        }

    def _records(self, claims, reference_replacements=None):
        # Exact source reads and segment indexes are shared only within this
        # synchronous preparation. The next review observes all source changes.
        sources = {}
        reference_replacements = reference_replacements or {}
        staged_ids = set()
        for cid, references in reference_replacements.items():
            for ref in references:
                if (
                    ref.claim_id != cid
                    or ref.status != "active"
                    or ref.origin not in {"scope", "extraction"}
                    or ref.reference_id in staged_ids
                ):
                    raise ValueError(
                        "Staged truth bindings must be unique active automatic references in their exact claim scope"
                    )
                staged_ids.add(ref.reference_id)
        return {
            cid: self._record(claim, sources, reference_replacements)
            for cid, claim in claims.items()
        }

    async def review(
        self,
        incoming_claim_ids,
        placements,
        entities,
        *,
        dream_run_id,
        excluded_claim_ids=frozenset(),
        reference_replacements=None,
    ):
        result = TruthReviewResult()
        # A retained source statement is not canonical evidence. Current-build
        # exclusions arrive before their disposition is committed to the store.
        claims = {
            c.claim_id: c
            for c in self.artifacts.list_claims(status="active")
            if c.dream_disposition != "excluded_source_policy"
            and c.claim_id not in excluded_claim_ids
        }
        incoming = sorted(incoming_claim_ids & claims.keys())
        if not incoming:
            return result
        try:
            if any(
                ref.dream_run_id != dream_run_id
                for refs in (reference_replacements or {}).values()
                for ref in refs
            ):
                raise ValueError(
                    "Staged truth bindings must belong to the current build"
                )
            records = self._records(claims, reference_replacements)
            if len(claims) < 2:
                # There is no truth comparison to make, but direct projection
                # still requires complete citations. A retained claim can cite
                # both active and retracted sources; its view marks uncertainty.
                return result
            reviewed_pairs = {
                tuple(sorted((left, right)))
                for proposal in self.artifacts.list_reconsolidation_proposals()
                if proposal.status in {"pending", "approved", "applied", "rejected"}
                for left in proposal.incoming_claim_ids
                for right in proposal.target_claim_ids
            }
            candidates = await self._candidate_pairs(
                incoming, records, excluded_pairs=reviewed_pairs
            )
            pairs = sorted(candidates)
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
                    retained, target = (
                        (right, left) if right in incoming_claim_ids else (left, right)
                    )
                changes.setdefault((retained, relation), []).append((target, decision))
            now = datetime.now().astimezone().isoformat()
            for (retained, relation), targets in changes.items():
                target_ids = sorted(target for target, _ in targets)
                sides = {retained, *target_ids}
                affected = {
                    eid
                    for cid in sides
                    if cid in placements
                    for eid in [
                        placements[cid].owner_entity_id,
                        *placements[cid].linked_entity_ids,
                        *placements[cid].page_sections,
                    ]
                    if eid
                }
                result.proposals.append(
                    ReconsolidationProposal(
                        proposal_id=f"recon-{uuid.uuid4().hex[:12]}",
                        incoming_claim_ids=[retained],
                        target_claim_ids=target_ids,
                        proposed_relation=relation,
                        explanation=json.dumps(
                            {target: decision for target, decision in targets},
                            ensure_ascii=False,
                        ),
                        confidence=min(claims[cid].confidence for cid in sides),
                        dream_run_id=dream_run_id,
                        created_at=now,
                        affected_entity_ids=sorted(affected),
                        prior_state="\n".join(claims[cid].text for cid in target_ids),
                        incoming_state=claims[retained].text,
                    )
                )
        except Exception as exc:
            result.failure_claim_ids.update(incoming)
            result.errors.append(
                f"Truth comparison failed: {type(exc).__name__}: {exc}"
            )
        return result

    async def _candidate_pools(self, incoming, records, excluded_pairs):
        """Search proposes bounded pairs; neither rank nor entity IDs decide truth."""
        documents = {
            cid: json.dumps(record, ensure_ascii=False, sort_keys=True)
            for cid, record in records.items()
        }
        by_entity = {}
        for cid, record in records.items():
            for ref in record.get("identity_bindings", []):
                if ref.get("entity_id"):
                    by_entity.setdefault(ref["entity_id"], set()).add(cid)
        pools, seen = {}, set(excluded_pairs)
        self.candidate_trace = {}
        for cid in sorted(incoming):
            eligible = {
                other
                for other in records
                if other != cid and tuple(sorted((cid, other))) not in excluded_pairs
            }
            global_ids, entity_ids = [], []
            if len(eligible) <= self._GLOBAL_CANDIDATES + self._ENTITY_CANDIDATES:
                selected = sorted(eligible)
            else:
                if self.candidates is None:
                    self.candidates = SemanticCandidates(
                        self.artifacts.root.parent / "indexes" / "truth",
                        OllamaEmbedder(
                            self.config.llm.url,
                            self.config.retrieval.embedding_model,
                            timeout=self.config.llm.timeout_seconds,
                            trace_path=self.llm.trace_path,
                        ),
                        self.artifacts.db,
                    )
                # The global route remains available across ownership boundaries
                # and when identity is unresolved or no page was admitted.
                global_ids = await self.candidates.select(
                    documents,
                    [documents[cid]],
                    limit=self._GLOBAL_CANDIDATES,
                    eligible_ids=eligible,
                )
                related = {
                    other
                    for ref in records[cid].get("identity_bindings", [])
                    for other in by_entity.get(ref.get("entity_id"), ())
                } & eligible
                entity_ids = await self.candidates.select(
                    documents,
                    [documents[cid]],
                    limit=self._ENTITY_CANDIDATES,
                    eligible_ids=related - set(global_ids),
                )
                selected = [*global_ids, *entity_ids]
            pools[cid] = set()
            for target in selected:
                pair = tuple(sorted((cid, target)))
                if pair not in seen:
                    pools[cid].add(target)
                    seen.add(pair)
            self.candidate_trace[cid] = {
                "global": global_ids,
                "entity": entity_ids,
                "selected": selected,
                "assigned": sorted(pools[cid]),
            }
        return pools

    async def _candidate_pairs(self, incoming, records, *, excluded_pairs=frozenset()):
        """Bound total model work as well as each individual request."""
        pairs = set()
        pools = await self._candidate_pools(incoming, records, excluded_pairs)

        async def select(new_ids, other_ids):
            # A statement cannot be its own comparison target. Other statements
            # from the same ingestion cohort remain candidates.
            if len(new_ids) == len(other_ids) == 1 and new_ids == other_ids:
                return
            incoming_aliases = {f"C{i:03d}": cid for i, cid in enumerate(new_ids, 1)}
            group_aliases = {f"X{i:03d}": cid for i, cid in enumerate(other_ids, 1)}
            # Pools assign each unordered pair once, including same-batch pairs
            # that were retrieved from only the later side's search.
            allowed = {
                alias: [
                    target
                    for target, target_id in group_aliases.items()
                    if cid != target_id
                    and target_id in pools[cid]
                    and tuple(sorted((cid, target_id))) not in excluded_pairs
                ]
                for alias, cid in incoming_aliases.items()
            }
            incoming_aliases = {
                a: cid for a, cid in incoming_aliases.items() if allowed[a]
            }
            allowed = {a: allowed[a] for a in incoming_aliases}
            if not allowed:
                return
            used_targets = {
                target for targets in allowed.values() for target in targets
            }
            group_aliases = {
                alias: cid
                for alias, cid in group_aliases.items()
                if alias in used_targets
            }
            schema = truth_candidates_model(allowed)
            system, user = render_prompt_pair(
                "memory/truth_candidates",
                payload=json.dumps(
                    {
                        "incoming": {
                            a: records[c] for a, c in incoming_aliases.items()
                        },
                        "candidates": {a: records[c] for a, c in group_aliases.items()},
                        "eligible_candidates": allowed,
                    },
                    ensure_ascii=False,
                ),
            )
            try:
                require_request_budget(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    context_window=self.llm.context_window_tokens,
                    output_tokens=4096,
                    schema=schema.model_json_schema(),
                )
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
            response = schema.model_validate(
                await self.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=4096,
                    debug_label="dream-truth-candidates",
                    cache_store=self.artifacts.db,
                )
            ).model_dump()["decisions"]
            for alias, decision in response.items():
                for target, relevance in decision["candidates"].items():
                    if relevance == "unrelated":
                        continue
                    left, right = incoming_aliases[alias], group_aliases[target]
                    pairs.add(tuple(sorted((left, right))))

        for start in range(0, len(incoming), 12):
            new_ids = incoming[start : start + 12]
            group_ids = sorted({target for cid in new_ids for target in pools[cid]})
            for other in range(0, len(group_ids), 12):
                await select(new_ids, group_ids[other : other + 12])
        return pairs

    async def _compare_pairs(self, pairs, records):
        decisions = {}

        async def compare(batch):
            aliases = {f"P{i:03d}": pair for i, pair in enumerate(batch, 1)}
            schema = truth_comparison_model(aliases)
            system, user = truth_comparison_prompt(
                json.dumps(
                    {
                        alias: {
                            "left": records[left],
                            "right": records[right],
                        }
                        for alias, (left, right) in aliases.items()
                    },
                    ensure_ascii=False,
                )
            )
            output_budget = self.llm.output_budget(4096, think=True)
            try:
                require_request_budget(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    context_window=self.llm.context_window_tokens,
                    output_tokens=output_budget,
                    schema=schema.model_json_schema(),
                )
            except ContextBudgetError:
                if len(batch) == 1:
                    raise
                middle = len(batch) // 2
                await compare(batch[:middle])
                await compare(batch[middle:])
                return
            response = schema.model_validate(
                await self.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=4096,
                    debug_label="dream-truth-comparison",
                    think=True,
                    cache_store=self.artifacts.db,
                )
            ).model_dump()["comparisons"]
            decisions.update(
                {
                    aliases[alias]: TruthComparison.model_validate(value).model_dump()
                    for alias, value in response.items()
                }
            )

        for start in range(0, len(pairs), 12):
            await compare(pairs[start : start + 12])
        return decisions
