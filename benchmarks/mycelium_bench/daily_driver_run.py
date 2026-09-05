"""Execute the Daily Driver fixture through Mycelium's production pipeline."""

from __future__ import annotations

import copy
import json
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from benchmarks.mycelium_bench.daily_driver import load_fixture, validate_fixture
from benchmarks.mycelium_bench.daily_driver_eval import (
    evaluate_run,
    judge_probe_answer,
    load_snapshots,
    match_snapshot,
    retrieved_generated_ids,
)
from benchmarks.mycelium_bench.adapters import OllamaQaClient
from benchmarks.mycelium_bench.scoring import token_f1
from mycelium.artifacts import ArtifactStore, MemoryClaim, SourceSegment
from mycelium.core import Mycelium
from mycelium.operations import ConsolidationRequest, RetrievalRequest, SourceInput
from mycelium.reconsolidation import ReconsolidationReviewService
from mycelium.session import Session
from mycelium.store import LogStore


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(value), indent=2, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _normalized(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _source_label_map(memory: Mycelium) -> dict[str, str]:
    labels: dict[str, str] = {}
    for source in memory.artifacts.list_sources():
        for segment in source.segments:
            label = segment.metadata.get("fixture_segment_id")
            if label:
                labels[segment.segment_id] = str(label)
    return labels


def _claim_source_labels(
    claim: MemoryClaim, segment_labels: dict[str, str]
) -> set[str]:
    return {
        segment_labels[segment_id]
        for provenance in claim.provenance
        for segment_id in provenance.segment_ids
        if segment_id in segment_labels
    }


def _snapshot(memory: Mycelium, checkpoint_id: str) -> dict[str, Any]:
    claims = memory.artifacts.list_claims()
    entities = memory.artifacts.list_entities()
    placements = memory.artifacts.list_placements()
    facts = memory.artifacts.list_consolidated_facts()
    pages = memory.wiki.list_all()
    labels = _source_label_map(memory)
    return _jsonable({
        "checkpoint_id": checkpoint_id,
        "sources": memory.artifacts.list_sources(),
        "episodes": memory.artifacts.list_episodes(),
        "claims": [
            {
                **asdict(claim),
                "fixture_evidence": sorted(_claim_source_labels(claim, labels)),
            }
            for claim in claims
        ],
        "entities": entities,
        "placements": placements,
        "consolidated_facts": facts,
        "scope_decisions": memory.artifacts.list_scope_decisions(),
        "encounters": memory.artifacts.list_encounters(),
        "reconsolidation_proposals": memory.artifacts.list_reconsolidation_proposals(),
        "dream_runs": memory.artifacts.list_dream_runs(),
        "pages": pages,
        "counts": {
            "sources": len(memory.artifacts.list_sources()),
            "claims": len(claims),
            "active_claims": sum(claim.status == "active" for claim in claims),
            "pending": sum(claim.dream_disposition == "pending" for claim in claims),
            "deferred": sum(claim.dream_disposition == "deferred" for claim in claims),
            "routing_failed": sum(
                claim.dream_disposition == "routing_failed" for claim in claims
            ),
            "placed": sum(item.status == "placed" for item in placements),
            "consolidated_facts": len(facts),
            "entities": len(entities),
            "pages": len(pages),
        },
    })


def _configure_user(memory: Mycelium, name: str) -> None:
    entity = memory.artifacts.get_entity("you")
    if name not in entity.aliases:
        entity.aliases.append(name)
        memory.artifacts.save_entity(entity)
    page = memory.wiki.get(entity.slug)
    page.aliases = list(entity.aliases)
    memory.wiki.save(page)


async def _ingest_episode(
    memory: Mycelium, episode: dict[str, Any], *, user_speaker_label: str
) -> None:
    segments: list[SourceSegment | dict[str, Any]] = []
    transcript_lines = []
    for index, row in enumerate(episode.get("segments") or []):
        speaker = str(row.get("speaker") or "Unknown")
        text = str(row.get("text") or "")
        transcript_lines.append(f"{speaker}: {text}")
        segments.append(
            SourceSegment(
                segment_id="",
                index=index,
                content=text,
                speaker=speaker,
                role=("user" if speaker == user_speaker_label else row.get("role")),
                metadata={
                    "fixture_segment_id": str(row["id"]),
                    "fixture_retention": str(row.get("retention") or ""),
                },
            )
        )
    metadata = dict(episode.get("metadata") or {})
    metadata.update(
        {
            "fixture_episode_id": str(episode["id"]),
            "fixture_source_id": str(episode["source_id"]),
        }
    )
    await memory.ingest_source(SourceInput(
        transcript="\n".join(transcript_lines),
        session_id=str(episode["id"]),
        source_type=str(episode["source_type"]),
        occurred_at=str(episode["occurred_at"]),
        participants=tuple(str(value) for value in episode.get("participants") or []),
        metadata=metadata,
        segments=tuple(segments),
        idempotency_key=f"daily-driver:{episode['id']}",
    ))


def _replay_extracted_episode(
    memory: Mycelium,
    replay: ArtifactStore,
    replay_logs: LogStore,
    episode: dict[str, Any],
) -> None:
    """Replay only canonical extraction artifacts for one fixture episode."""
    fixture_episode_id = str(episode["id"])
    sources = [
        source
        for source in replay.list_sources()
        if str(source.metadata.get("fixture_episode_id")) == fixture_episode_id
    ]
    if len(sources) != 1:
        raise RuntimeError(
            f"Replay store must contain one source for {fixture_episode_id}; found {len(sources)}"
        )
    source = copy.deepcopy(sources[0])
    expected_labels = {str(row["id"]) for row in episode.get("segments") or []}
    actual_labels = {
        str(segment.metadata.get("fixture_segment_id"))
        for segment in source.segments
        if segment.metadata.get("fixture_segment_id")
    }
    if expected_labels != actual_labels:
        raise RuntimeError(
            f"Replay source for {fixture_episode_id} has different fixture segments"
        )
    manifests = [
        item for item in replay.list_episodes() if item.source_id == source.source_id
    ]
    if len(manifests) != 1:
        raise RuntimeError(
            f"Replay store must contain one manifest for {fixture_episode_id}; found {len(manifests)}"
        )
    manifest = copy.deepcopy(manifests[0])
    memory.artifacts.save_source(source)
    if not source.raw_log_entry_id:
        raise RuntimeError(
            f"Replay source for {fixture_episode_id} has no raw log entry"
        )
    log_entry = copy.deepcopy(replay_logs.get(source.raw_log_entry_id))
    log_entry.consolidated = False
    memory.log_store.append(log_entry)
    for claim_id in manifest.claim_ids:
        claim = copy.deepcopy(replay.get_claim(claim_id))
        claim.status = "active"
        claim.dream_disposition = "pending"
        claim.dream_disposition_reason = None
        claim.dream_run_id = None
        claim.dream_disposition_at = None
        memory.artifacts.save_claim(claim)
    memory.artifacts.save_episode(manifest)


def _gold_claim(fixture: dict[str, Any], claim_id: str) -> dict[str, Any]:
    return next(
        row for row in fixture["gold_claims"]["claims"] if row["id"] == claim_id
    )


def _approve_proposal(
    memory: Mycelium, fixture: dict[str, Any], fixture_proposal_id: str
) -> dict[str, Any]:
    reconciliation = next(
        item
        for checkpoint in fixture["gold_checkpoints"]["checkpoints"]
        for item in checkpoint.get("reconciliation") or []
        if item["id"] == fixture_proposal_id
    )
    incoming_evidence = set(
        _gold_claim(fixture, reconciliation["incoming_claim"])["evidence"]
    )
    target_evidence = set(
        _gold_claim(fixture, reconciliation["target_claim"])["evidence"]
    )
    labels = _source_label_map(memory)
    candidates = []
    for proposal in memory.artifacts.list_reconsolidation_proposals(status="pending"):
        incoming = memory.artifacts.get_claim(proposal.incoming_claim_id)
        target = memory.artifacts.get_claim(proposal.target_claim_id)
        if (
            _claim_source_labels(incoming, labels) & incoming_evidence
            and _claim_source_labels(target, labels) & target_evidence
        ):
            candidates.append(proposal)
    if len(candidates) != 1:
        raise RuntimeError(
            f"Expected one pending proposal for {fixture_proposal_id}, found {len(candidates)}"
        )
    service = ReconsolidationReviewService(
        memory.artifacts, memory.consolidator.materializer
    )
    result = service.approve(
        candidates[0].proposal_id,
        reviewer_note=f"Approved by fixture action {fixture_proposal_id}",
    )
    return _jsonable(result)


def _best_claim_candidates(
    fixture: dict[str, Any], memory: Mycelium
) -> list[dict[str, Any]]:
    labels = _source_label_map(memory)
    generated = memory.artifacts.list_claims()
    rows = []
    for gold in fixture["gold_claims"]["claims"]:
        expected_evidence = set(gold.get("evidence") or [])
        candidates = []
        for claim in generated:
            actual_evidence = _claim_source_labels(claim, labels)
            overlap = expected_evidence & actual_evidence
            if not overlap:
                continue
            text_score = token_f1(claim.text, gold["text"])
            type_match = claim.claim_type == gold.get("claim_type")
            predicate_match = _normalized(claim.predicate) == _normalized(
                gold.get("predicate")
            )
            score = text_score + 0.2 * type_match + 0.2 * predicate_match
            candidates.append(
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "claim_type": claim.claim_type,
                    "predicate": claim.predicate,
                    "status": claim.status,
                    "dream_disposition": claim.dream_disposition,
                    "fixture_evidence": sorted(actual_evidence),
                    "text_f1": round(text_score, 4),
                    "type_match": type_match,
                    "predicate_match": predicate_match,
                    "score": round(score, 4),
                }
            )
        candidates.sort(key=lambda item: (-item["score"], item["claim_id"]))
        best = candidates[0] if candidates else None
        likely = bool(
            best
            and (
                best["text_f1"] >= 0.45
                or (best["type_match"] and best["predicate_match"])
            )
        )
        rows.append(
            {
                "gold_claim_id": gold["id"],
                "gold_text": gold["text"],
                "gold_type": gold.get("claim_type"),
                "gold_predicate": gold.get("predicate"),
                "gold_state": gold.get("state"),
                "gold_evidence": sorted(expected_evidence),
                "candidate_found": bool(best),
                "likely_semantic_match": likely,
                "best_candidate": best,
                "candidate_count": len(candidates),
            }
        )
    return rows


def _entity_comparison(fixture: dict[str, Any], memory: Mycelium) -> dict[str, Any]:
    generated = memory.artifacts.list_entities(status="active")
    matched_generated: set[str] = set()
    rows = []
    for gold in fixture["gold_wiki"]["entities"]:
        names = {
            _normalized(gold["title"]),
            *map(_normalized, gold.get("aliases") or []),
        }
        candidates = []
        for entity in generated:
            if gold["id"] == "you":
                if entity.entity_id == "you":
                    candidates.append((True, 1.0, entity))
                continue
            if entity.entity_type != gold["type"]:
                continue
            generated_names = {
                _normalized(entity.title),
                *map(_normalized, entity.aliases),
            }
            exact = bool(names & generated_names) or (
                gold["id"] == "you" and entity.entity_id == "you"
            )
            similarity = max(
                token_f1(left, right) for left in names for right in generated_names
            )
            if exact or similarity >= 0.5:
                candidates.append((exact, similarity, entity))
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2].entity_id))
        selected = next(
            (item for item in candidates if item[2].entity_id not in matched_generated),
            None,
        )
        if selected:
            matched_generated.add(selected[2].entity_id)
        rows.append(
            {
                "gold_entity_id": gold["id"],
                "gold_title": gold["title"],
                "gold_type": gold["type"],
                "generated": _jsonable(selected[2]) if selected else None,
                "type_match": bool(
                    selected and selected[2].entity_type == gold["type"]
                ),
                "name_similarity": round(selected[1], 4) if selected else 0.0,
            }
        )
    return {
        "matches": rows,
        "missing": [row["gold_entity_id"] for row in rows if not row["generated"]],
        "extra": [
            _jsonable(entity)
            for entity in generated
            if entity.entity_id not in matched_generated
        ],
    }


def compare_final(fixture: dict[str, Any], memory: Mycelium) -> dict[str, Any]:
    labels = _source_label_map(memory)
    generated_claims = memory.artifacts.list_claims()
    expected_claim_labels = {
        str(segment["id"])
        for episode in fixture["scenario"]["episodes"]
        for segment in episode.get("segments") or []
        if segment.get("retention") in {"claim", "claim_then_retract"}
    }
    source_only_labels = {
        str(segment["id"])
        for episode in fixture["scenario"]["episodes"]
        for segment in episode.get("segments") or []
        if segment.get("retention") in {"source_only", "retraction_instruction"}
    }
    claimed_labels = {
        label
        for claim in generated_claims
        for label in _claim_source_labels(claim, labels)
    }
    claim_rows = _best_claim_candidates(fixture, memory)
    placements = memory.artifacts.list_placements(status="placed")
    placed_ids = {item.claim_id for item in placements}
    pages = memory.wiki.list_all()
    page_entity_ids = {page.entity_id for page in pages}
    rendered_claim_ids = {
        str(claim_id)
        for page in pages
        for section in page.sections
        for item in section.get("items") or []
        for claim_id in item.get("claim_ids") or []
    }
    active_claims = [claim for claim in generated_claims if claim.status == "active"]
    source_only_details: list[dict[str, Any]] = []
    for label in sorted(source_only_labels & claimed_labels):
        matching_claims = [
            claim
            for claim in generated_claims
            if label in _claim_source_labels(claim, labels)
        ]
        source_only_details.append(
            {
                "fixture_segment_id": label,
                "claims": [
                    {
                        "claim_id": claim.claim_id,
                        "text": claim.text,
                        "dream_disposition": claim.dream_disposition,
                        "rendered": claim.claim_id in rendered_claim_ids,
                    }
                    for claim in matching_claims
                ],
            }
        )
    claim_rows_by_id = {row["gold_claim_id"]: row for row in claim_rows}
    wiki_fact_rows = []
    for fact in fixture["gold_wiki"]["facts"]:
        matching_rows = [
            claim_rows_by_id[claim_id]
            for claim_id in fact.get("claim_ids") or []
            if claim_id in claim_rows_by_id
        ]
        rendered_candidates = sorted(
            {
                row["best_candidate"]["claim_id"]
                for row in matching_rows
                if row["likely_semantic_match"]
                and row["best_candidate"]
                and row["best_candidate"]["claim_id"] in rendered_claim_ids
            }
        )
        wiki_fact_rows.append(
            {
                "gold_fact_id": fact["id"],
                "gold_text": fact["text"],
                "gold_state": fact["state"],
                "gold_render_on": fact.get("render_on") or [],
                "provisionally_represented": bool(rendered_candidates),
                "rendered_candidate_claim_ids": rendered_candidates,
            }
        )
    return {
        "source_accounting": {
            "claim_bearing_total": len(expected_claim_labels),
            "claim_bearing_covered": len(expected_claim_labels & claimed_labels),
            "missing_claim_bearing": sorted(expected_claim_labels - claimed_labels),
            "source_only_total": len(source_only_labels),
            "source_only_claimed": sorted(source_only_labels & claimed_labels),
            "source_only_details": source_only_details,
            "source_only_rendered": sorted(
                {
                    row["fixture_segment_id"]
                    for row in source_only_details
                    if any(claim["rendered"] for claim in row["claims"])
                }
            ),
        },
        "claim_comparison": {
            "gold_total": len(claim_rows),
            "candidate_found": sum(row["candidate_found"] for row in claim_rows),
            "likely_semantic_match": sum(
                row["likely_semantic_match"] for row in claim_rows
            ),
            "rows": claim_rows,
        },
        "entity_comparison": _entity_comparison(fixture, memory),
        "wiki_fact_comparison": {
            "gold_total": len(wiki_fact_rows),
            "provisionally_represented": sum(
                row["provisionally_represented"] for row in wiki_fact_rows
            ),
            "rows": wiki_fact_rows,
        },
        "projection": {
            "active_claims": len(active_claims),
            "active_placed": sum(
                claim.claim_id in placed_ids for claim in active_claims
            ),
            "active_rendered": sum(
                claim.claim_id in rendered_claim_ids for claim in active_claims
            ),
            "placed_without_page": [
                item.claim_id
                for item in placements
                if item.owner_entity_id not in page_entity_ids
            ],
            "dream_dispositions": dict(
                sorted(
                    Counter(claim.dream_disposition for claim in active_claims).items()
                )
            ),
        },
        "generated_pages": [
            {
                "entity_id": page.entity_id,
                "slug": page.slug,
                "title": page.title,
                "page_type": page.page_type,
                "sections": [
                    {
                        "key": section.get("key"),
                        "heading": section.get("title"),
                        "item_count": len(section.get("items") or []),
                        "items": section.get("items") or [],
                    }
                    for section in page.sections
                    if section.get("items")
                ],
                "content": page.content,
            }
            for page in sorted(pages, key=lambda item: item.slug)
        ],
    }


async def _run_checkpoint_probes(
    fixture: dict[str, Any],
    memory: Mycelium,
    checkpoint_id: str,
    snapshot: dict[str, Any],
    *,
    run_answers: bool,
) -> list[dict[str, Any]]:
    probes = [
        row
        for row in fixture["probes"].get("probes") or []
        if row.get("checkpoint") == checkpoint_id
    ]
    if not probes:
        return []
    snapshot_match = match_snapshot(fixture, snapshot)
    gold_facts = {
        str(row["id"]): row for row in fixture["gold_wiki"].get("facts") or []
    }
    qa = OllamaQaClient(
        model=memory.config.llm.model,
        url=memory.config.llm.url,
        temperature=0.0,
        timeout=memory.config.llm.timeout_seconds,
    )
    rows: list[dict[str, Any]] = []
    for probe in probes:
        retrieval = await memory.retrieve_context(RetrievalRequest(
            query=str(probe["question"]),
        ))
        loaded_pages = list(retrieval.page_references)
        retrieved_gold_facts, retrieved_claim_ids = retrieved_generated_ids(
            retrieval.evidence, snapshot_match
        )
        retrieved_evidence = {
            str(value)
            for claim in snapshot.get("claims") or []
            if str(claim.get("claim_id")) in retrieved_claim_ids
            for value in claim.get("fixture_evidence") or []
        }
        required = set(map(str, probe.get("required_facts") or []))
        forbidden = set(map(str, probe.get("forbidden_facts") or []))
        forbidden_evidence = set(map(str, probe.get("forbidden_evidence") or []))
        present_required = sorted(required & retrieved_gold_facts)
        present_forbidden = sorted(forbidden & retrieved_gold_facts)
        session = Session(
            mycelium=memory,
            session_id=f"daily-driver-{checkpoint_id}-{probe['id']}",
            query=str(probe["question"]),
        )
        session.page_references = retrieval.page_references
        session.memory_evidence = retrieval.evidence
        context = session.memory_context
        result: dict[str, Any] = {
            "probe_id": probe["id"],
            "checkpoint": checkpoint_id,
            "question": probe["question"],
            "answerable": probe.get("answerable", True),
            "required_facts": sorted(required),
            "present_required_facts": present_required,
            "missing_required_facts": sorted(required - retrieved_gold_facts),
            "forbidden_facts": sorted(forbidden),
            "present_forbidden_facts": present_forbidden,
            "forbidden_evidence": sorted(forbidden_evidence),
            "present_forbidden_evidence": sorted(
                forbidden_evidence & retrieved_evidence
            ),
            "retrieved_evidence": sorted(retrieved_evidence),
            "retrieval_passed": required <= retrieved_gold_facts
            and not present_forbidden
            and not (forbidden_evidence & retrieved_evidence),
            "retrieved_generated_claim_ids": sorted(retrieved_claim_ids),
            "loaded_pages": [
                {"entity_id": page.entity_id, "slug": page.slug, "title": page.title}
                for page in loaded_pages
            ],
            "context": context,
            "answer": None,
            "judgment": None,
        }
        if run_answers:
            if probe.get("evaluation_mode") == "artifact":
                answer = str(probe.get("expected_answer") or "")
                result["answer_origin"] = "artifact observation"
            else:
                answer_result = await qa.answer(str(probe["question"]), context)
                answer = answer_result.output
                result["answer_origin"] = "production retrieval context"
                result["answer_metadata"] = answer_result.metadata
            result["answer"] = answer
            result["judgment"] = await judge_probe_answer(
                llm=memory.llm,
                probe=probe,
                answer=answer,
                gold_facts=gold_facts,
            )
        rows.append(result)
    return rows


def _report_markdown(
    run: dict[str, Any],
    evaluation: dict[str, Any],
    actions: list[dict[str, Any]],
) -> str:
    artifact_summary = evaluation["artifact_summary"]
    source = artifact_summary["source_accounting"]
    claims = artifact_summary["claims"]
    entities = artifact_summary["entities"]
    wiki_facts = artifact_summary["wiki_facts"]
    projection = artifact_summary["projection"]
    lines = [
        "# Daily Driver artifact evaluation",
        "",
        f"- Model: `{run['model']}`",
        f"- Fixture: `{run['scenario_id']}`",
        f"- Extraction mode: `{run.get('extraction_mode', 'fresh')}`",
        "- Scope: production encoding, Dream, reviewed reconsolidation, wiki projection, retrieval probes, and semantic answer checks.",
        "- Comparison policy: provenance, state, ownership, sections, and rendered IDs are authoritative. Text matching is an exposed diagnostic used only to associate source-grounded propositions.",
        "- Dimensions remain separate; there is no aggregate quality score.",
        "",
        "## Release gates",
        "",
        *[
            f"- {'PASS' if gate['passed'] else 'FAIL'} `{gate['id']}` — {gate['rule']}"
            for gate in evaluation["gates"]
        ],
        "",
        "## Rubric dimensions",
        "",
        *[
            (
                f"- {('PASS' if metric['passed'] else 'FAIL') if metric.get('evaluated', True) else 'NOT RUN'} "
                f"`{metric['id']}`: "
                f"{metric['value']:.3f} ({metric['numerator']}/{metric['denominator']})"
            )
            for metric in evaluation["dimensions"]
        ],
        "",
        "## Layer summary",
        "",
        f"- Claim-bearing source coverage: {source['claim_bearing_covered']}/{source['claim_bearing_total']}",
        f"- Source-only segments represented in extracted claims: {len(source['source_only_claimed'])}/{source['source_only_total']}",
        f"- Source-only segments rendered into the wiki: {len(source['source_only_rendered'])}/{source['source_only_total']}",
        f"- Gold claims with an evidence-linked candidate: {claims['evidence_candidate_found']}/{claims['gold_total']}",
        f"- Evidence-grounded semantic candidates: {claims['semantic_candidate_found']}/{claims['gold_total']}",
        f"- Gold entities found: {entities['found']}/{entities['gold_total']}",
        f"- Extra generated entities: {len(entities['extra'])}",
        f"- Gold wiki facts rendered at their required page/section endpoints: {wiki_facts['rendered_correctly']}/{wiki_facts['gold_total']}",
        f"- Active generated claims placed: {projection['active_placed']}/{projection['active_claims']}",
        f"- Active generated claims rendered: {projection['active_rendered']}/{projection['active_claims']}",
        f"- Atomic propositions represented: {evaluation['proposition_completeness']['propositions_represented']}/{evaluation['proposition_completeness']['propositions_total']}",
        f"- Complete multi-assertion segments: {evaluation['proposition_completeness']['complete_multi_assertion_segments']}/{evaluation['proposition_completeness']['multi_assertion_segments']}",
        "",
        "## Known capability boundary",
        "",
        "Unsupported fixture actions are recorded as capability gaps. The runner never mutates artifacts to imitate a gold checkpoint.",
        "",
        "## Source accounting",
        "",
        f"- Missing claim-bearing segments: {source['missing_claim_bearing'] or 'none'}",
        f"- Claimed source-only segments: {source['source_only_claimed'] or 'none'}",
        f"- Source-only segments rendered in wiki pages: {source['source_only_rendered'] or 'none'}",
        "",
        "## Entity accounting",
        "",
        f"- Missing: {entities['missing'] or 'none'}",
        f"- Extras: {[item.get('title') for item in entities['extra']] or 'none'}",
        "",
        "## Generated pages",
        "",
    ]
    for page in artifact_summary["generated_pages"]:
        section_summary = ", ".join(
            f"{section['heading'] or section['key']} ({section['item_count']})"
            for section in page["sections"]
        )
        lines.append(
            f"- **{page['title']}** (`{page['page_type']}`, `{page['slug']}`): "
            f"{section_summary or 'no structured facts'}"
        )
    lines.extend(["", "## Action log", ""])
    for action in actions:
        detail = (
            action.get("error") or action.get("reason") or action.get("result", "ok")
        )
        lines.append(f"- `{action['action']}`: {detail}")
    lines.extend(
        [
            "",
            "See `evaluation.json` for dimensions, gates, proposition completeness, checkpoint diffs, ownership confusion, duplicates, retrieval results, and page diffs. `comparison.json` is a transitional review artifact and is not used for gates or dimension results.",
            "",
        ]
    )
    return "\n".join(lines)


def refresh_daily_driver_comparison(
    fixture_dir: Path, output_dir: Path, *, config_path: Path | None = None
) -> dict[str, Any]:
    """Recompute diagnostics for a completed run without invoking an LLM."""
    fixture = load_fixture(fixture_dir)
    memory = Mycelium(
        output_dir / "store", config_path=config_path, memory_profile="user"
    )
    run_path = output_dir / "run.json"
    if run_path.exists():
        run = json.loads(run_path.read_text(encoding="utf-8"))
    else:
        run = {
            "scenario_id": fixture["scenario"]["scenario_id"],
            "model": memory.config.llm.model,
            "ollama_url": memory.config.llm.url,
            "config_path": str(config_path) if config_path else None,
            "extraction_mode": "unknown_recovered_run",
            "replay_extraction_store": None,
            "probe_answers": True,
            "checkpoint_ids": sorted(
                path.parent.name
                for path in (output_dir / "checkpoints").glob("*/snapshot.json")
            ),
            "actions": [],
        }
        _write_json(run_path, run)
    comparison = compare_final(fixture, memory)
    snapshots = load_snapshots(output_dir)
    probe_results = [
        row
        for path in sorted((output_dir / "checkpoints").glob("*/probes.json"))
        for row in json.loads(path.read_text(encoding="utf-8"))
    ]
    evaluation = evaluate_run(fixture, snapshots, probe_results)
    _write_json(output_dir / "comparison.json", comparison)
    _write_json(output_dir / "evaluation.json", evaluation)
    (output_dir / "REPORT.md").write_text(
        _report_markdown(run, evaluation, run["actions"]),
        encoding="utf-8",
    )
    return {"comparison": comparison, "evaluation": evaluation}


async def run_daily_driver(
    fixture_dir: Path,
    output_dir: Path,
    *,
    config_path: Path | None = None,
    replay_extraction_store: Path | None = None,
    run_probe_answers: bool = True,
) -> dict[str, Any]:
    validate_fixture(fixture_dir)
    fixture = load_fixture(fixture_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    memory = Mycelium(
        output_dir / "store",
        config_path=config_path,
        memory_profile="user",
    )
    replay = None
    replay_logs = None
    if replay_extraction_store is not None:
        if not replay_extraction_store.is_dir():
            raise ValueError(
                f"Replay extraction store does not exist: {replay_extraction_store}"
            )
        replay = ArtifactStore(replay_extraction_store / "artifacts")
        replay_logs = LogStore(replay_extraction_store / "logs")
    _configure_user(memory, str(fixture["scenario"]["user"]["name"]))
    actions: list[dict[str, Any]] = []
    checkpoint_ids: list[str] = []
    snapshots: dict[str, dict[str, Any]] = {}
    probe_results: list[dict[str, Any]] = []
    for episode in fixture["scenario"]["episodes"]:
        if replay is None:
            await _ingest_episode(
                memory,
                episode,
                user_speaker_label=str(fixture["scenario"]["user"]["speaker_label"]),
            )
        else:
            if replay_logs is None:
                raise RuntimeError("Replay log store was not initialized")
            _replay_extracted_episode(memory, replay, replay_logs, episode)
        for action in episode.get("actions_after") or []:
            kind, _, value = str(action).partition(":")
            event: dict[str, Any] = {"episode": episode["id"], "action": action}
            try:
                if kind == "dream":
                    result = await memory.consolidate(ConsolidationRequest())
                    event["result"] = _jsonable(result.report)
                elif kind == "checkpoint":
                    snapshot = _snapshot(memory, value)
                    checkpoint_dir = output_dir / "checkpoints" / value
                    _write_json(checkpoint_dir / "snapshot.json", snapshot)
                    wiki_dir = checkpoint_dir / "wiki"
                    wiki_dir.mkdir(parents=True, exist_ok=True)
                    for page in memory.wiki.list_all():
                        shutil.copy2(
                            memory.store_path / "wiki" / f"{page.slug}.md",
                            wiki_dir / f"{page.slug}.md",
                        )
                    snapshots[value] = snapshot
                    checkpoint_probes = await _run_checkpoint_probes(
                        fixture,
                        memory,
                        value,
                        snapshot,
                        run_answers=run_probe_answers,
                    )
                    _write_json(checkpoint_dir / "probes.json", checkpoint_probes)
                    probe_results.extend(checkpoint_probes)
                    checkpoint_ids.append(value)
                    event["result"] = snapshot["counts"]
                elif kind == "approve":
                    event["result"] = _approve_proposal(memory, fixture, value)
                elif kind == "retract":
                    event.update(
                        {
                            "status": "unsupported",
                            "reason": (
                                "Production Mycelium has no source-retraction operation; "
                                "the fixture action was not simulated."
                            ),
                        }
                    )
                else:
                    raise ValueError(f"Unsupported fixture action: {action}")
            except Exception as exc:  # Preserve later checkpoints for diagnosis.
                event.update(
                    {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
                )
            actions.append(event)
    run = {
        "scenario_id": fixture["scenario"]["scenario_id"],
        "model": memory.config.llm.model,
        "ollama_url": memory.config.llm.url,
        "config_path": str(config_path) if config_path else None,
        "extraction_mode": "replay" if replay is not None else "fresh",
        "replay_extraction_store": (
            str(replay_extraction_store) if replay_extraction_store else None
        ),
        "probe_answers": run_probe_answers,
        "checkpoint_ids": checkpoint_ids,
        "actions": actions,
    }
    _write_json(output_dir / "run.json", run)
    comparison = compare_final(fixture, memory)
    evaluation = evaluate_run(fixture, snapshots, probe_results)
    _write_json(output_dir / "comparison.json", comparison)
    _write_json(output_dir / "evaluation.json", evaluation)
    (output_dir / "REPORT.md").write_text(
        _report_markdown(run, evaluation, actions), encoding="utf-8"
    )
    return {
        "run": run,
        "comparison": comparison,
        "evaluation": evaluation,
        "output_dir": str(output_dir),
    }


async def run_daily_driver_trials(
    fixture_dir: Path,
    output_dir: Path,
    *,
    trials: int,
    config_path: Path | None = None,
    replay_extraction_store: Path | None = None,
    run_probe_answers: bool = True,
) -> dict[str, Any]:
    """Run repeated independent trials and report variance per dimension."""
    if trials < 2:
        raise ValueError("Repeated trial runs require trials >= 2")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for trial in range(1, trials + 1):
        trial_dir = output_dir / f"trial-{trial:02d}"
        results.append(
            await run_daily_driver(
                fixture_dir,
                trial_dir,
                config_path=config_path,
                replay_extraction_store=replay_extraction_store,
                run_probe_answers=run_probe_answers,
            )
        )
    dimension_values: dict[str, list[float]] = defaultdict(list)
    gate_values: dict[str, list[bool]] = defaultdict(list)
    for result in results:
        for row in result["evaluation"]["dimensions"]:
            dimension_values[row["id"]].append(float(row["value"]))
        for row in result["evaluation"]["gates"]:
            gate_values[row["id"]].append(bool(row["passed"]))
    summary = {
        "scenario_id": results[0]["run"]["scenario_id"],
        "trials": trials,
        "extraction_mode": results[0]["run"]["extraction_mode"],
        "dimensions": {
            key: {
                "values": values,
                "mean": sum(values) / len(values),
                "minimum": min(values),
                "maximum": max(values),
            }
            for key, values in sorted(dimension_values.items())
        },
        "gates": {
            key: {
                "passed_trials": sum(values),
                "total_trials": len(values),
                "passed_all": all(values),
            }
            for key, values in sorted(gate_values.items())
        },
        "trial_dirs": [result["output_dir"] for result in results],
    }
    _write_json(output_dir / "trial_summary.json", summary)
    return summary
