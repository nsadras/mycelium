"""Artifact-level evaluation for Daily Driver fixtures.

The evaluator deliberately operates on stable artifact IDs and exact fixture evidence
labels. Text similarity is retained only to disambiguate multiple propositions emitted
from the same source segment; every such match is exposed for review.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from benchmarks.mycelium_bench.scoring import token_f1
from mycelium.ollama import OllamaClient


class ProbeJudgment(BaseModel):
    """Post-answer semantic judgment; gold facts are never exposed to retrieval."""

    present_required_fact_ids: list[str] = Field(default_factory=list)
    present_forbidden_fact_ids: list[str] = Field(default_factory=list)
    answerable_decision_correct: bool
    rationale: str


def _normalized(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _claim_evidence(claim: dict[str, Any]) -> set[str]:
    return {str(value) for value in claim.get("fixture_evidence") or []}


def _eligible_candidate(gold: dict[str, Any], generated: dict[str, Any]) -> bool:
    text_score = token_f1(generated.get("text", ""), gold.get("text", ""))
    envelope = generated.get("claim_type") == gold.get("claim_type") and _normalized(
        generated.get("predicate")
    ) == _normalized(gold.get("predicate"))
    return text_score >= 0.45 or envelope


def _candidate_score(gold: dict[str, Any], generated: dict[str, Any]) -> float:
    return (
        token_f1(generated.get("text", ""), gold.get("text", ""))
        + 0.2 * (generated.get("claim_type") == gold.get("claim_type"))
        + 0.2
        * (
            _normalized(generated.get("predicate"))
            == _normalized(gold.get("predicate"))
        )
    )


def _entity_map(
    fixture: dict[str, Any], snapshot: dict[str, Any]
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    generated = [
        row for row in snapshot.get("entities") or [] if row.get("status") == "active"
    ]
    used: set[str] = set()
    mapping: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    active_gold_ids = {
        str(row["id"]) for row in fixture["gold_wiki"].get("entities") or []
    }
    gold_entities = [
        *(fixture["gold_wiki"].get("entities") or []),
        *(fixture["gold_wiki"].get("retracted_entities") or []),
    ]
    for gold in gold_entities:
        names = {
            _normalized(gold.get("title")),
            *map(_normalized, gold.get("aliases") or []),
        }
        candidates: list[tuple[bool, float, dict[str, Any]]] = []
        for entity in generated:
            if gold["id"] == "you":
                if entity.get("entity_id") == "you":
                    candidates.append((True, 1.0, entity))
                continue
            if entity.get("entity_type") != gold.get("type"):
                continue
            generated_names = {
                _normalized(entity.get("title")),
                *map(_normalized, entity.get("aliases") or []),
            }
            exact = bool(names & generated_names)
            similarity = max(
                (token_f1(left, right) for left in names for right in generated_names),
                default=0.0,
            )
            if exact or similarity >= 0.5:
                candidates.append((exact, similarity, entity))
        candidates.sort(
            key=lambda item: (-item[0], -item[1], str(item[2].get("entity_id")))
        )
        selected = next(
            (item for item in candidates if str(item[2].get("entity_id")) not in used),
            None,
        )
        if selected:
            generated_id = str(selected[2]["entity_id"])
            mapping[str(gold["id"])] = generated_id
            used.add(generated_id)
        rows.append(
            {
                "gold_entity_id": gold["id"],
                "gold_type": gold.get("type"),
                "expected_final_active": str(gold["id"]) in active_gold_ids,
                "generated_entity_id": selected[2].get("entity_id")
                if selected
                else None,
                "generated_type": selected[2].get("entity_type") if selected else None,
                "name_similarity": round(selected[1], 4) if selected else 0.0,
            }
        )
    extras = [row for row in generated if str(row.get("entity_id")) not in used]
    return mapping, rows, extras


def match_snapshot(fixture: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Map gold records to generated records using exact evidence before semantics."""
    generated_claims = snapshot.get("claims") or []
    placement_by_claim = {
        str(row.get("claim_id")): row for row in snapshot.get("placements") or []
    }
    entity_map, entity_rows, extra_entities = _entity_map(fixture, snapshot)
    claim_rows: list[dict[str, Any]] = []
    for gold in fixture["gold_claims"].get("claims") or []:
        gold_evidence = {str(value) for value in gold.get("evidence") or []}
        candidates = [
            claim
            for claim in generated_claims
            if gold_evidence & _claim_evidence(claim)
        ]
        candidates.sort(
            key=lambda row: (-_candidate_score(gold, row), str(row.get("claim_id")))
        )
        best = candidates[0] if candidates else None
        eligible = bool(best and _eligible_candidate(gold, best))
        placement = placement_by_claim.get(str(best.get("claim_id"))) if best else None
        claim_rows.append(
            {
                "gold_claim_id": gold["id"],
                "gold_fact_id": gold.get("fact_id"),
                "gold_owner": gold.get("owner"),
                "gold_section": gold.get("section"),
                "gold_evidence": sorted(gold_evidence),
                "candidate_found": best is not None,
                "semantic_candidate": eligible,
                "generated_claim_id": best.get("claim_id") if best else None,
                "generated_text": best.get("text") if best else None,
                "generated_status": best.get("status") if best else None,
                "generated_disposition": best.get("dream_disposition")
                if best
                else None,
                "generated_owner": placement.get("owner_entity_id")
                if placement
                else None,
                "generated_section": placement.get("section_key")
                if placement
                else None,
                "generated_links": placement.get("linked_entity_ids", [])
                if placement
                else [],
                "expected_generated_owner": entity_map.get(str(gold.get("owner"))),
                "text_f1": round(
                    token_f1(best.get("text", ""), gold.get("text", "")), 4
                )
                if best
                else 0.0,
                "type_match": bool(
                    best and best.get("claim_type") == gold.get("claim_type")
                ),
                "predicate_match": bool(
                    best
                    and _normalized(best.get("predicate"))
                    == _normalized(gold.get("predicate"))
                ),
                "modality_match": bool(
                    best
                    and best.get("evidence_modality") == gold.get("evidence_modality")
                ),
                "temporal_match": bool(
                    best and best.get("temporal_status") == gold.get("temporal_status")
                ),
                "actual_evidence": sorted(_claim_evidence(best)) if best else [],
            }
        )

    generated_facts = snapshot.get("consolidated_facts") or []
    pages = snapshot.get("pages") or []
    rendered: dict[str, list[dict[str, str]]] = defaultdict(list)
    for page in pages:
        for section in page.get("sections") or []:
            for item in section.get("items") or []:
                fact_id = item.get("fact_id")
                if fact_id:
                    rendered[str(fact_id)].append(
                        {
                            "entity_id": str(page.get("entity_id")),
                            "section_key": str(section.get("key")),
                        }
                    )
    claim_row_by_id = {row["gold_claim_id"]: row for row in claim_rows}
    fact_rows: list[dict[str, Any]] = []
    gold_locations: dict[str, list[dict[str, str]]] = defaultdict(list)
    for page in fixture["gold_wiki"].get("pages") or []:
        for section_key, payload in (page.get("sections") or {}).items():
            fact_ids = (
                payload if isinstance(payload, list) else payload.get("facts") or []
            )
            for fact_id in fact_ids:
                gold_locations[str(fact_id)].append(
                    {
                        "entity_id": str(page["entity_id"]),
                        "section_key": str(section_key),
                    }
                )
    gold_fact_definitions = {
        str(row["id"]): dict(row) for row in fixture["gold_wiki"].get("facts") or []
    }
    for gold_claim in fixture["gold_claims"].get("claims") or []:
        fact_id = str(gold_claim.get("fact_id") or "")
        if not fact_id or fact_id in gold_fact_definitions:
            continue
        gold_fact_definitions[fact_id] = {
            "id": fact_id,
            "text": gold_claim.get("text", ""),
            "claim_ids": [
                row["id"]
                for row in fixture["gold_claims"].get("claims") or []
                if str(row.get("fact_id") or "") == fact_id
            ],
            "state": gold_claim.get("state"),
            "render_on": [],
        }
    for gold_fact in gold_fact_definitions.values():
        expected_claims = [
            claim_row_by_id[value]
            for value in gold_fact.get("claim_ids") or []
            if value in claim_row_by_id
        ]
        generated_member_ids = {
            str(row["generated_claim_id"])
            for row in expected_claims
            if row["semantic_candidate"] and row["generated_claim_id"]
        }
        candidates = [
            fact
            for fact in generated_facts
            if generated_member_ids & set(map(str, fact.get("member_claim_ids") or []))
        ]
        candidates.sort(
            key=lambda row: (
                -len(
                    generated_member_ids
                    & set(map(str, row.get("member_claim_ids") or []))
                ),
                str(row.get("fact_id")),
            )
        )
        selected = candidates[0] if candidates else None
        expected_locations = gold_locations.get(str(gold_fact["id"]), [])
        expected_generated_locations = [
            {
                "entity_id": entity_map.get(row["entity_id"]),
                "section_key": row["section_key"],
            }
            for row in expected_locations
            if entity_map.get(row["entity_id"])
        ]
        actual_locations = (
            rendered.get(str(selected.get("fact_id")), []) if selected else []
        )
        fact_rows.append(
            {
                "gold_fact_id": gold_fact["id"],
                "gold_state": gold_fact.get("state"),
                "gold_render_on": gold_fact.get("render_on") or [],
                "expected_locations": expected_locations,
                "expected_generated_locations": expected_generated_locations,
                "gold_claim_ids": gold_fact.get("claim_ids") or [],
                "generated_fact_id": selected.get("fact_id") if selected else None,
                "generated_owner": selected.get("owner_entity_id")
                if selected
                else None,
                "generated_section": selected.get("section_key") if selected else None,
                "generated_state": selected.get("state") if selected else None,
                "member_claim_coverage": (
                    len(
                        generated_member_ids
                        & set(map(str, selected.get("member_claim_ids") or []))
                    )
                    / len(generated_member_ids)
                    if selected and generated_member_ids
                    else 0.0
                ),
                "rendered_at": actual_locations,
                "rendered_correctly": {
                    (row["entity_id"], row["section_key"])
                    for row in expected_generated_locations
                }
                <= {(row["entity_id"], row["section_key"]) for row in actual_locations}
                if expected_generated_locations
                else False,
            }
        )
    return {
        "entity_map": entity_map,
        "entity_rows": entity_rows,
        "extra_entities": extra_entities,
        "claim_rows": claim_rows,
        "fact_rows": fact_rows,
    }


def proposition_completeness(
    fixture: dict[str, Any], snapshot_match: dict[str, Any]
) -> dict[str, Any]:
    """Require distinct generated claims for distinct gold propositions per segment."""
    by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for gold in fixture["gold_claims"].get("claims") or []:
        for evidence_id in gold.get("evidence") or []:
            by_segment[str(evidence_id)].append(gold)
    generated_by_segment: dict[str, set[str]] = defaultdict(set)
    row_by_gold = {row["gold_claim_id"]: row for row in snapshot_match["claim_rows"]}
    rows: list[dict[str, Any]] = []
    for segment_id, propositions in sorted(by_segment.items()):
        matches = []
        for proposition in propositions:
            row = row_by_gold[proposition["id"]]
            claim_id = row.get("generated_claim_id")
            if row.get("semantic_candidate") and claim_id:
                generated_by_segment[segment_id].add(str(claim_id))
                matches.append((str(proposition["id"]), str(claim_id)))
        # One broad generated sentence cannot satisfy several atomic gold propositions.
        unique_claims: set[str] = set()
        represented: list[str] = []
        for gold_id, claim_id in matches:
            if claim_id in unique_claims:
                continue
            unique_claims.add(claim_id)
            represented.append(gold_id)
        rows.append(
            {
                "segment_id": segment_id,
                "proposition_count": len(propositions),
                "represented_count": len(represented),
                "complete": len(represented) == len(propositions),
                "gold_claim_ids": [row["id"] for row in propositions],
                "represented_gold_claim_ids": represented,
                "generated_claim_ids": sorted(unique_claims),
            }
        )
    multi = [row for row in rows if row["proposition_count"] > 1]
    total = sum(row["proposition_count"] for row in rows)
    represented = sum(row["represented_count"] for row in rows)
    return {
        "propositions_total": total,
        "propositions_represented": represented,
        "recall": represented / total if total else 1.0,
        "multi_assertion_segments": len(multi),
        "complete_multi_assertion_segments": sum(row["complete"] for row in multi),
        "rows": rows,
    }


def retrieved_generated_ids(
    loaded_pages: list[Any], snapshot_match: dict[str, Any]
) -> tuple[set[str], set[str]]:
    claim_ids: set[str] = set()
    fact_ids: set[str] = set()
    for page in loaded_pages:
        claim_ids.update(re.findall(r"\(claim: ([^)]+)\)", page.content or ""))
        for section in page.sections or []:
            for item in section.get("items") or []:
                claim_ids.update(map(str, item.get("claim_ids") or []))
                if item.get("fact_id"):
                    fact_ids.add(str(item["fact_id"]))
    gold_fact_ids: set[str] = set()
    for row in snapshot_match["fact_rows"]:
        if row.get("generated_fact_id") in fact_ids:
            gold_fact_ids.add(str(row["gold_fact_id"]))
            continue
        gold_claim_rows = [
            item
            for item in snapshot_match["claim_rows"]
            if item.get("gold_fact_id") == row["gold_fact_id"]
        ]
        if any(item.get("generated_claim_id") in claim_ids for item in gold_claim_rows):
            gold_fact_ids.add(str(row["gold_fact_id"]))
    return gold_fact_ids, claim_ids


async def judge_probe_answer(
    *,
    llm: OllamaClient,
    probe: dict[str, Any],
    answer: str,
    gold_facts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    required = {
        fact_id: gold_facts[fact_id]["text"]
        for fact_id in probe.get("required_facts") or []
    }
    forbidden = {
        fact_id: gold_facts[fact_id]["text"]
        for fact_id in probe.get("forbidden_facts") or []
    }
    system = (
        "Judge a memory answer by propositions, not wording. Mark a required fact present only if the "
        "answer entails its relevant content. Mark a forbidden fact present only if the answer asserts it. "
        "For an unanswerable probe, answerable_decision_correct is true only when the response clearly "
        "declines to supply the requested fact. Return only the structured result."
    )
    user = json.dumps(
        {
            "question": probe["question"],
            "answer": answer,
            "expected_answer_is_non_normative": probe.get("expected_answer"),
            "answerable": probe.get("answerable", True),
            "required_facts": required,
            "forbidden_facts": forbidden,
        },
        ensure_ascii=False,
    )
    response = await llm.call_structured(system, user, ProbeJudgment, num_predict=512)
    judgment = ProbeJudgment.model_validate(response).model_dump()
    allowed_required = set(required)
    allowed_forbidden = set(forbidden)
    judgment["present_required_fact_ids"] = sorted(
        allowed_required & set(judgment["present_required_fact_ids"])
    )
    judgment["present_forbidden_fact_ids"] = sorted(
        allowed_forbidden & set(judgment["present_forbidden_fact_ids"])
    )
    judgment["passed"] = (
        set(judgment["present_required_fact_ids"]) == allowed_required
        and not judgment["present_forbidden_fact_ids"]
        and judgment["answerable_decision_correct"]
    )
    return judgment


def _ratio_metric(
    *,
    numerator: int,
    denominator: int,
    target: float,
    direction: str = "at_least",
    evaluated: bool = True,
) -> dict[str, Any]:
    value = numerator / denominator if denominator else 1.0
    passed = evaluated and (
        value >= target if direction == "at_least" else value <= target
    )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": round(value, 6),
        "target": target,
        "direction": direction,
        "evaluated": evaluated,
        "passed": passed,
    }


def _checkpoint_results(
    fixture: dict[str, Any], snapshots: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    gold_checkpoints = {
        row["id"]: row for row in fixture["gold_checkpoints"].get("checkpoints") or []
    }
    results: list[dict[str, Any]] = []
    for checkpoint_id, gold in gold_checkpoints.items():
        snapshot = snapshots.get(checkpoint_id)
        if not snapshot:
            results.append(
                {
                    "checkpoint_id": checkpoint_id,
                    "passed": False,
                    "checks": [],
                    "error": "missing snapshot",
                }
            )
            continue
        match = match_snapshot(fixture, snapshot)
        claim_by_gold = {row["gold_claim_id"]: row for row in match["claim_rows"]}
        fact_by_gold = {row["gold_fact_id"]: row for row in match["fact_rows"]}
        rendered_claim_ids = {
            str(claim_id)
            for page in snapshot.get("pages") or []
            for section in page.get("sections") or []
            for item in section.get("items") or []
            for claim_id in item.get("claim_ids") or []
        }
        pending_proposal_claim_ids = {
            str(claim_id)
            for proposal in snapshot.get("reconsolidation_proposals") or []
            if proposal.get("status") == "pending"
            for claim_id in (
                proposal.get("incoming_claim_id"),
                proposal.get("target_claim_id"),
            )
            if claim_id
        }
        generated_entities = {
            str(row.get("entity_id"))
            for row in snapshot.get("entities") or []
            if row.get("status") == "active"
        }
        page_entities = {
            str(row.get("entity_id")) for row in snapshot.get("pages") or []
        }
        checks: list[dict[str, Any]] = []
        for queue_name, expected_claim_ids in (gold.get("queue") or {}).items():
            for claim_id in expected_claim_ids or []:
                row = claim_by_gold[claim_id]
                expected = (
                    "routing_failed"
                    if queue_name == "retryable"
                    else queue_name.rstrip("s")
                )
                checks.append(
                    {
                        "kind": "queue",
                        "gold_id": claim_id,
                        "expected": expected,
                        "actual": row.get("generated_disposition"),
                        "passed": row.get("generated_disposition") == expected,
                    }
                )
        for gold_claim_id in gold.get("canonical_claims") or []:
            row = claim_by_gold[gold_claim_id]
            checks.append(
                {
                    "kind": "canonical_claim",
                    "gold_id": gold_claim_id,
                    "actual": {
                        "status": row.get("generated_status"),
                        "owner": row.get("generated_owner"),
                    },
                    "passed": row.get("generated_status") == "active"
                    and bool(row.get("generated_owner")),
                }
            )
        for gold_claim_id in gold.get("withheld_from_authoritative_sections") or []:
            generated_id = claim_by_gold[gold_claim_id].get("generated_claim_id")
            checks.append(
                {
                    "kind": "withheld_claim",
                    "gold_id": gold_claim_id,
                    "actual": generated_id in rendered_claim_ids,
                    "passed": bool(generated_id)
                    and generated_id not in rendered_claim_ids,
                }
            )
        for gold_claim_id in gold.get("needs_review") or []:
            generated_id = claim_by_gold[gold_claim_id].get("generated_claim_id")
            checks.append(
                {
                    "kind": "needs_review",
                    "gold_id": gold_claim_id,
                    "actual": generated_id in pending_proposal_claim_ids,
                    "passed": bool(generated_id)
                    and generated_id in pending_proposal_claim_ids,
                }
            )
        for reconciliation in gold.get("reconciliation") or []:
            incoming_id = claim_by_gold[reconciliation["incoming_claim"]].get(
                "generated_claim_id"
            )
            target_id = claim_by_gold[reconciliation["target_claim"]].get(
                "generated_claim_id"
            )
            candidates = [
                proposal
                for proposal in snapshot.get("reconsolidation_proposals") or []
                if proposal.get("incoming_claim_id") == incoming_id
                and proposal.get("target_claim_id") == target_id
                and proposal.get("proposed_relation") == reconciliation.get("relation")
                and proposal.get("status") == reconciliation.get("status")
            ]
            checks.append(
                {
                    "kind": "reconciliation",
                    "gold_id": reconciliation["id"],
                    "actual": candidates,
                    "passed": len(candidates) == 1,
                }
            )
        for gold_entity_id in gold.get("entities") or []:
            generated_id = match["entity_map"].get(gold_entity_id)
            checks.append(
                {
                    "kind": "required_entity",
                    "gold_id": gold_entity_id,
                    "actual": generated_id,
                    "passed": bool(generated_id and generated_id in generated_entities),
                }
            )
        for gold_entity_id in gold.get("pages") or []:
            generated_id = match["entity_map"].get(gold_entity_id)
            checks.append(
                {
                    "kind": "required_page",
                    "gold_id": gold_entity_id,
                    "actual": generated_id,
                    "passed": bool(generated_id and generated_id in page_entities),
                }
            )
        for gold_entity_id in gold.get("forbidden_pages") or []:
            generated_id = match["entity_map"].get(gold_entity_id)
            checks.append(
                {
                    "kind": "forbidden_page",
                    "gold_id": gold_entity_id,
                    "actual": generated_id,
                    "passed": not generated_id or generated_id not in page_entities,
                }
            )
        for gold_entity_id, gold_fact_ids in (
            gold.get("required_page_facts") or {}
        ).items():
            generated_entity_id = match["entity_map"].get(gold_entity_id)
            for gold_fact_id in gold_fact_ids:
                rendered_at = fact_by_gold[gold_fact_id].get("rendered_at") or []
                checks.append(
                    {
                        "kind": "required_page_fact",
                        "gold_id": gold_fact_id,
                        "gold_entity_id": gold_entity_id,
                        "actual": rendered_at,
                        "passed": any(
                            row["entity_id"] == generated_entity_id
                            for row in rendered_at
                        ),
                    }
                )
        for gold_claim_id, expected_status in (
            gold.get("claim_state_overrides") or {}
        ).items():
            actual = claim_by_gold[gold_claim_id].get("generated_status")
            checks.append(
                {
                    "kind": "claim_state",
                    "gold_id": gold_claim_id,
                    "expected": expected_status,
                    "actual": actual,
                    "passed": actual == expected_status,
                }
            )
        for gold_fact_id in gold.get("authoritative_facts") or []:
            row = fact_by_gold[gold_fact_id]
            checks.append(
                {
                    "kind": "authoritative_fact",
                    "gold_id": gold_fact_id,
                    "actual": row.get("rendered_at"),
                    "passed": bool(row.get("rendered_at")),
                }
            )
        for gold_fact_id in gold.get("historical_facts") or []:
            row = fact_by_gold[gold_fact_id]
            checks.append(
                {
                    "kind": "historical_fact",
                    "gold_id": gold_fact_id,
                    "actual": row.get("rendered_at"),
                    "passed": bool(row.get("rendered_at")),
                }
            )
        for gold_fact_id in gold.get("forbidden_current_facts") or []:
            row = fact_by_gold[gold_fact_id]
            checks.append(
                {
                    "kind": "forbidden_current_fact",
                    "gold_id": gold_fact_id,
                    "actual": row.get("rendered_at"),
                    "passed": not row.get("rendered_at"),
                }
            )
        for gold_entity_id in gold.get("removed_entities") or []:
            generated_id = match["entity_map"].get(gold_entity_id)
            checks.append(
                {
                    "kind": "removed_entity",
                    "gold_id": gold_entity_id,
                    "actual": generated_id,
                    "passed": not generated_id
                    or generated_id not in generated_entities,
                }
            )
        for gold_entity_id in gold.get("removed_pages") or []:
            generated_id = match["entity_map"].get(gold_entity_id)
            checks.append(
                {
                    "kind": "removed_page",
                    "gold_id": gold_entity_id,
                    "actual": generated_id,
                    "passed": not generated_id or generated_id not in page_entities,
                }
            )
        source_by_fixture_id = {
            str((source.get("metadata") or {}).get("fixture_source_id")): source
            for source in snapshot.get("sources") or []
        }
        for fixture_source_id, expected_state in (
            gold.get("source_states") or {}
        ).items():
            source = source_by_fixture_id.get(str(fixture_source_id))
            actual_state = source.get("status", "active") if source else None
            checks.append(
                {
                    "kind": "source_state",
                    "gold_id": fixture_source_id,
                    "expected": expected_state,
                    "actual": actual_state,
                    "passed": actual_state == expected_state,
                }
            )
        if gold.get("exact_fact_count") is not None:
            actual = sum(bool(row.get("rendered_at")) for row in match["fact_rows"])
            checks.append(
                {
                    "kind": "exact_fact_count",
                    "expected": gold["exact_fact_count"],
                    "actual": actual,
                    "passed": actual == gold["exact_fact_count"],
                }
            )
        results.append(
            {
                "checkpoint_id": checkpoint_id,
                "passed": all(row["passed"] for row in checks),
                "checks_passed": sum(row["passed"] for row in checks),
                "checks_total": len(checks),
                "checks": checks,
            }
        )
    return results


def evaluate_run(
    fixture: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    probe_results: list[dict[str, Any]],
) -> dict[str, Any]:
    final_id = str(
        fixture["gold_checkpoints"].get("final_checkpoint")
        or (fixture["gold_checkpoints"].get("checkpoints") or [])[-1]["id"]
    )
    final_snapshot = snapshots.get(final_id, {})
    final_match = match_snapshot(fixture, final_snapshot)
    propositions = proposition_completeness(fixture, final_match)
    checkpoint_results = _checkpoint_results(fixture, snapshots)
    claim_rows = final_match["claim_rows"]
    fact_rows = final_match["fact_rows"]
    final_gold_fact_ids = {
        str(row["id"]) for row in fixture["gold_wiki"].get("facts") or []
    }
    wiki_fact_rows = [
        row for row in fact_rows if row["gold_fact_id"] in final_gold_fact_ids
    ]
    probes_by_id = {row["probe_id"]: row for row in probe_results}
    rubric_dimensions = fixture["rubric"].get("dimensions") or []
    final_entity_rows = [
        row for row in final_match["entity_rows"] if row["expected_final_active"]
    ]

    admitted_evidence = {
        str(value)
        for gold in fixture["gold_claims"].get("claims") or []
        for value in gold.get("evidence") or []
    }
    supported_generated = {
        str(claim.get("claim_id"))
        for claim in final_snapshot.get("claims") or []
        if admitted_evidence & _claim_evidence(claim)
    }
    rendered_claim_ids = {
        str(claim_id)
        for page in final_snapshot.get("pages") or []
        for section in page.get("sections") or []
        for item in section.get("items") or []
        for claim_id in item.get("claim_ids") or []
    }
    unsupported_rendered = rendered_claim_ids - supported_generated
    provenance_exact = [
        row
        for row in claim_rows
        if row["semantic_candidate"] and row["actual_evidence"] == row["gold_evidence"]
    ]
    envelope_checks = [
        passed
        for row in claim_rows
        if row["semantic_candidate"]
        for passed in (
            row["type_match"],
            row["predicate_match"],
            row["modality_match"],
            row["temporal_match"],
        )
    ]
    ownership_rows = [
        row
        for row in claim_rows
        if row["semantic_candidate"] and row["expected_generated_owner"]
    ]
    section_rows = [row for row in ownership_rows if row.get("gold_section")]
    expected_render_count = {
        row["gold_fact_id"]: len(row["expected_locations"]) for row in wiki_fact_rows
    }
    duplicate_rows = [
        {
            "gold_fact_id": row["gold_fact_id"],
            "expected": expected_render_count[row["gold_fact_id"]],
            "actual": len(row["rendered_at"]),
        }
        for row in wiki_fact_rows
        if len(row["rendered_at"]) > expected_render_count[row["gold_fact_id"]]
    ]
    fixture_probes = fixture["probes"].get("probes") or []
    retracted_fact_ids = {
        str(row.get("fact_id"))
        for row in fixture["gold_claims"].get("claims") or []
        if row.get("state") == "retracted" and row.get("fact_id")
    }
    retraction_probe_ids = {
        str(row["id"])
        for row in fixture_probes
        if retracted_fact_ids & set(map(str, row.get("forbidden_facts") or []))
    }
    retracted_claim_ids = {
        str(row["id"])
        for row in fixture["gold_claims"].get("claims") or []
        if row.get("state") == "retracted"
    }
    claim_by_gold_id = {row["gold_claim_id"]: row for row in claim_rows}
    retracted_claim_checks = [
        claim_by_gold_id[claim_id].get("generated_status") == "retracted"
        for claim_id in retracted_claim_ids
        if claim_id in claim_by_gold_id
    ]
    retrieval_required_total = sum(
        len(row.get("required_facts") or []) for row in fixture_probes
    )
    retrieval_required_present = sum(
        len(row.get("present_required_facts") or []) for row in probe_results
    )
    retrieval_forbidden_total = sum(
        len(row.get("forbidden_facts") or []) + len(row.get("forbidden_evidence") or [])
        for row in fixture_probes
    )
    retrieval_forbidden_present = sum(
        len(row.get("present_forbidden_facts") or [])
        + len(row.get("present_forbidden_evidence") or [])
        for row in probe_results
    )
    answered = [row for row in probe_results if row.get("judgment")]

    raw_metrics: dict[str, dict[str, Any]] = {
        "claim_recall": _ratio_metric(
            numerator=propositions["propositions_represented"],
            denominator=propositions["propositions_total"],
            target=1.0,
        ),
        "unsupported_claim_rate": _ratio_metric(
            numerator=len(unsupported_rendered),
            denominator=max(1, len(rendered_claim_ids)),
            target=0.0,
            direction="at_most",
        ),
        "provenance_accuracy": _ratio_metric(
            numerator=len(provenance_exact),
            denominator=sum(row["semantic_candidate"] for row in claim_rows),
            target=1.0,
        ),
        "semantic_envelope_accuracy": _ratio_metric(
            numerator=sum(envelope_checks), denominator=len(envelope_checks), target=1.0
        ),
        "lifecycle_accuracy": _ratio_metric(
            numerator=sum(row.get("checks_passed", 0) for row in checkpoint_results),
            denominator=sum(row.get("checks_total", 0) for row in checkpoint_results),
            target=1.0,
        ),
        "entity_precision_recall": _ratio_metric(
            numerator=sum(
                bool(row["generated_entity_id"]) for row in final_entity_rows
            ),
            denominator=len(final_entity_rows) + len(final_match["extra_entities"]),
            target=1.0,
        ),
        "entity_type_accuracy": _ratio_metric(
            numerator=sum(
                row["gold_type"] == row["generated_type"]
                for row in final_entity_rows
                if row["generated_entity_id"]
            ),
            denominator=sum(
                bool(row["generated_entity_id"]) for row in final_entity_rows
            ),
            target=1.0,
        ),
        "ownership_accuracy": _ratio_metric(
            numerator=sum(
                row["generated_owner"] == row["expected_generated_owner"]
                for row in ownership_rows
            ),
            denominator=len(ownership_rows),
            target=1.0,
        ),
        "section_accuracy": _ratio_metric(
            numerator=sum(
                row["generated_section"] == row["gold_section"] for row in section_rows
            ),
            denominator=len(section_rows),
            target=1.0,
        ),
        "wiki_fact_recall": _ratio_metric(
            numerator=sum(bool(row["rendered_correctly"]) for row in wiki_fact_rows),
            denominator=len(wiki_fact_rows),
            target=1.0,
        ),
        "wiki_concision": _ratio_metric(
            numerator=len(duplicate_rows),
            denominator=max(1, len(wiki_fact_rows)),
            target=0.0,
            direction="at_most",
        ),
        "cross_project_contamination": _ratio_metric(
            numerator=sum(
                row["generated_owner"] not in {None, row["expected_generated_owner"]}
                for row in ownership_rows
            ),
            denominator=max(1, len(ownership_rows)),
            target=0.0,
            direction="at_most",
        ),
        "current_history_separation": _ratio_metric(
            numerator=sum(
                check["passed"]
                for row in checkpoint_results
                for check in row.get("checks", [])
                if check["kind"] in {"claim_state", "forbidden_current_fact"}
            ),
            denominator=sum(
                1
                for row in checkpoint_results
                for check in row.get("checks", [])
                if check["kind"] in {"claim_state", "forbidden_current_fact"}
            ),
            target=1.0,
        ),
        "retraction_completeness": _ratio_metric(
            numerator=sum(retracted_claim_checks)
            + sum(
                not row.get("present_forbidden_facts")
                and not row.get("present_forbidden_evidence")
                for row in probe_results
                if row["probe_id"] in retraction_probe_ids
            ),
            denominator=len(retracted_claim_checks) + len(retraction_probe_ids),
            target=1.0,
            evaluated=bool(retracted_claim_checks)
            and (
                not retraction_probe_ids
                or retraction_probe_ids
                <= {str(row["probe_id"]) for row in probe_results}
            ),
        ),
        "retrieval_fact_recall": _ratio_metric(
            numerator=retrieval_required_present,
            denominator=retrieval_required_total,
            target=1.0,
            evaluated=len(probe_results) == len(fixture_probes),
        ),
        "retrieval_tangent_rate": _ratio_metric(
            numerator=retrieval_forbidden_present,
            denominator=max(1, retrieval_forbidden_total),
            target=0.0,
            direction="at_most",
            evaluated=len(probe_results) == len(fixture_probes),
        ),
        "semantic_answer_quality": _ratio_metric(
            numerator=sum(bool(row["judgment"].get("passed")) for row in answered),
            denominator=len(fixture_probes),
            target=1.0,
            evaluated=len(answered) == len(fixture_probes),
        ),
    }
    dimensions = []
    for definition in rubric_dimensions:
        metric = dict(
            raw_metrics.get(
                definition["id"], _ratio_metric(numerator=0, denominator=0, target=1.0)
            )
        )
        metric.update(
            {
                "id": definition["id"],
                "stage": definition.get("stage"),
                "severity": definition.get("severity"),
                "measure": definition.get("measure"),
            }
        )
        dimensions.append(metric)

    gate_results = evaluate_gates(
        fixture=fixture,
        snapshots=snapshots,
        checkpoint_results=checkpoint_results,
        probe_results=probes_by_id,
    )
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for row in ownership_rows:
        confusion[str(row["gold_owner"])][
            str(row["generated_owner"] or "unassigned")
        ] += 1
    page_diff = [
        {
            "gold_fact_id": row["gold_fact_id"],
            "missing": not row["rendered_at"],
            "expected": row["expected_locations"],
            "actual": row["rendered_at"],
            "actual_section": row["generated_section"],
        }
        for row in wiki_fact_rows
    ]
    scenario_segments = [
        segment
        for episode in fixture["scenario"].get("episodes") or []
        for segment in episode.get("segments") or []
    ]
    claim_bearing_labels = {
        str(row["id"])
        for row in scenario_segments
        if row.get("retention") in {"claim", "claim_then_retract"}
    }
    source_only_labels = {
        str(row["id"])
        for row in scenario_segments
        if row.get("retention") in {"source_only", "retraction_instruction"}
    }
    claimed_labels = {
        label
        for claim in final_snapshot.get("claims") or []
        for label in _claim_evidence(claim)
    }
    active_claims = [
        claim
        for claim in final_snapshot.get("claims") or []
        if claim.get("status") == "active"
    ]
    placement_by_claim = {
        str(row.get("claim_id")): row for row in final_snapshot.get("placements") or []
    }
    generated_pages = [
        {
            "entity_id": page.get("entity_id"),
            "slug": page.get("slug"),
            "title": page.get("title"),
            "page_type": page.get("page_type"),
            "sections": [
                {
                    "key": section.get("key"),
                    "heading": section.get("title"),
                    "item_count": len(section.get("items") or []),
                }
                for section in page.get("sections") or []
                if section.get("items")
            ],
        }
        for page in sorted(
            final_snapshot.get("pages") or [], key=lambda row: str(row.get("slug"))
        )
    ]
    artifact_summary = {
        "source_accounting": {
            "claim_bearing_total": len(claim_bearing_labels),
            "claim_bearing_covered": len(claim_bearing_labels & claimed_labels),
            "missing_claim_bearing": sorted(claim_bearing_labels - claimed_labels),
            "source_only_total": len(source_only_labels),
            "source_only_claimed": sorted(source_only_labels & claimed_labels),
            "source_only_rendered": sorted(
                {
                    label
                    for claim in final_snapshot.get("claims") or []
                    if str(claim.get("claim_id")) in rendered_claim_ids
                    for label in _claim_evidence(claim)
                    if label in source_only_labels
                }
            ),
        },
        "claims": {
            "gold_total": len(claim_rows),
            "evidence_candidate_found": sum(
                row["candidate_found"] for row in claim_rows
            ),
            "semantic_candidate_found": sum(
                row["semantic_candidate"] for row in claim_rows
            ),
        },
        "entities": {
            "gold_total": len(final_entity_rows),
            "found": sum(bool(row["generated_entity_id"]) for row in final_entity_rows),
            "missing": [
                row["gold_entity_id"]
                for row in final_entity_rows
                if not row["generated_entity_id"]
            ],
            "extra": final_match["extra_entities"],
        },
        "wiki_facts": {
            "gold_total": len(wiki_fact_rows),
            "rendered_correctly": sum(
                row["rendered_correctly"] for row in wiki_fact_rows
            ),
        },
        "projection": {
            "active_claims": len(active_claims),
            "active_placed": sum(
                (placement_by_claim.get(str(claim.get("claim_id"))) or {}).get("status")
                == "placed"
                for claim in active_claims
            ),
            "active_rendered": sum(
                str(claim.get("claim_id")) in rendered_claim_ids
                for claim in active_claims
            ),
            "dream_dispositions": dict(
                sorted(
                    Counter(
                        str(claim.get("dream_disposition")) for claim in active_claims
                    ).items()
                )
            ),
        },
        "generated_pages": generated_pages,
    }
    return {
        "final_checkpoint": final_id,
        "dimensions": dimensions,
        "gates": gate_results,
        "summary": {
            "dimensions_passed": sum(row["passed"] for row in dimensions),
            "dimensions_total": len(dimensions),
            "gates_passed": sum(row["passed"] for row in gate_results),
            "gates_total": len(gate_results),
            "release_ready": all(row["passed"] for row in gate_results),
        },
        "proposition_completeness": propositions,
        "checkpoint_diffs": checkpoint_results,
        "ownership_confusion_matrix": {
            key: dict(value) for key, value in sorted(confusion.items())
        },
        "duplicate_rendered_facts": duplicate_rows,
        "retrieval_probes": probe_results,
        "qualitative_page_diff": page_diff,
        "unsupported_rendered_claim_ids": sorted(unsupported_rendered),
        "artifact_summary": artifact_summary,
        "final_match": final_match,
    }


def evaluate_gates(
    *,
    fixture: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    checkpoint_results: list[dict[str, Any]],
    probe_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    checkpoint_by_id = {row["checkpoint_id"]: row for row in checkpoint_results}
    results: list[dict[str, Any]] = []
    for gate in fixture["rubric"].get("gates") or []:
        check = gate.get("check") or {}
        kind = check.get("type")
        passed = False
        actual: Any = None
        if kind == "checkpoint_checks":
            checkpoint = checkpoint_by_id.get(str(check.get("checkpoint")))
            check_kinds = set(check.get("kinds") or [])
            selected = [
                row
                for row in (checkpoint or {}).get("checks", [])
                if row["kind"] in check_kinds
            ]
            passed = bool(selected) and all(row["passed"] for row in selected)
            actual = selected
        elif kind == "probe":
            probe = probe_results.get(str(check.get("probe_id")))
            requirements = set(check.get("requirements") or ["retrieval"])
            values = []
            if probe and "retrieval" in requirements:
                values.append(bool(probe.get("retrieval_passed")))
            if probe and "answer" in requirements:
                values.append(bool((probe.get("judgment") or {}).get("passed")))
            passed = bool(values) and all(values)
            actual = probe
        elif kind == "distinct_entities":
            snapshot = snapshots.get(str(check.get("checkpoint")), {})
            match = match_snapshot(fixture, snapshot)
            generated = [
                match["entity_map"].get(value)
                for value in check.get("entity_ids") or []
            ]
            passed = all(generated) and len(set(generated)) == len(generated)
            actual = generated
        elif kind == "forbidden_evidence_absent":
            snapshot = snapshots.get(str(check.get("checkpoint")), {})
            labels = set(map(str, check.get("evidence") or []))
            offending = []
            for claim in snapshot.get("claims") or []:
                if claim.get("status") == "active" and labels & _claim_evidence(claim):
                    offending.append(str(claim.get("claim_id")))
            passed = not offending
            actual = offending
        elif kind == "ownership_exact":
            snapshot = snapshots.get(str(check.get("checkpoint")), {})
            match = match_snapshot(fixture, snapshot)
            owners = set(map(str, check.get("entity_ids") or []))
            selected = [
                row
                for row in match["claim_rows"]
                if row.get("gold_owner") in owners and row.get("semantic_candidate")
            ]
            ownership_offending = [
                {
                    "gold_claim_id": row["gold_claim_id"],
                    "expected": row["expected_generated_owner"],
                    "actual": row["generated_owner"],
                }
                for row in selected
                if row.get("generated_owner") is not None
                and row.get("generated_owner") != row.get("expected_generated_owner")
            ]
            passed = bool(selected) and not ownership_offending
            actual = ownership_offending
        else:
            actual = f"unknown gate check type: {kind}"
        results.append(
            {
                "id": gate["id"],
                "rule": gate.get("rule"),
                "passed": passed,
                "check": check,
                "actual": actual,
            }
        )
    return results


def load_snapshots(output_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        path.parent.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((output_dir / "checkpoints").glob("*/snapshot.json"))
    }
