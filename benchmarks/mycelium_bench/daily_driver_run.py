"""Execute the Daily Driver fixture through Mycelium's production pipeline."""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from benchmarks.mycelium_bench.daily_driver import load_fixture, validate_fixture
from benchmarks.mycelium_bench.scoring import token_f1
from mycelium.artifacts import MemoryClaim, SourceSegment
from mycelium.core import Mycelium
from mycelium.reconsolidation import ReconsolidationReviewService


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
        json.dumps(_jsonable(value), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
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
    return {
        "checkpoint_id": checkpoint_id,
        "sources": memory.artifacts.list_sources(),
        "episodes": memory.artifacts.list_episodes(),
        "claims": [
            {**asdict(claim), "fixture_evidence": sorted(_claim_source_labels(claim, labels))}
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
    }


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
                role=(
                    "user"
                    if speaker == user_speaker_label
                    else row.get("role")
                ),
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
    await memory.encoder.encode_session(
        "\n".join(transcript_lines),
        str(episode["id"]),
        source_type=str(episode["source_type"]),
        occurred_at=str(episode["occurred_at"]),
        participants=[str(value) for value in episode.get("participants") or []],
        metadata=metadata,
        segments=segments,
    )


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
        memory.artifacts, memory.dream_process.materializer
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


def _entity_comparison(
    fixture: dict[str, Any], memory: Mycelium
) -> dict[str, Any]:
    generated = memory.artifacts.list_entities(status="active")
    matched_generated: set[str] = set()
    rows = []
    for gold in fixture["gold_wiki"]["entities"]:
        names = {_normalized(gold["title"]), *map(_normalized, gold.get("aliases") or [])}
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
                "type_match": bool(selected and selected[2].entity_type == gold["type"]),
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
    claim_rows_by_id = {
        row["gold_claim_id"]: row for row in claim_rows
    }
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
            "active_placed": sum(claim.claim_id in placed_ids for claim in active_claims),
            "active_rendered": sum(
                claim.claim_id in rendered_claim_ids for claim in active_claims
            ),
            "placed_without_page": [
                item.claim_id
                for item in placements
                if item.owner_entity_id not in page_entity_ids
            ],
            "dream_dispositions": dict(
                sorted(Counter(claim.dream_disposition for claim in active_claims).items())
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


def _report_markdown(
    run: dict[str, Any], comparison: dict[str, Any], actions: list[dict[str, Any]]
) -> str:
    source = comparison["source_accounting"]
    claims = comparison["claim_comparison"]
    entities = comparison["entity_comparison"]
    wiki_facts = comparison["wiki_fact_comparison"]
    projection = comparison["projection"]
    lines = [
        "# Daily Driver initial artifact comparison",
        "",
        f"- Model: `{run['model']}`",
        f"- Fixture: `{run['scenario_id']}`",
        "- Scope: production encoding, Dream, reviewed reconsolidation, and wiki projection; QA probes were not run.",
        "- Comparison policy: source provenance is exact; semantic claim matches and entity-name matches are diagnostic heuristics for human review, not a benchmark score.",
        "",
        "## Layer summary",
        "",
        f"- Claim-bearing source coverage: {source['claim_bearing_covered']}/{source['claim_bearing_total']}",
        f"- Source-only segments represented in extracted claims: {len(source['source_only_claimed'])}/{source['source_only_total']}",
        f"- Source-only segments rendered into the wiki: {len(source['source_only_rendered'])}/{source['source_only_total']}",
        f"- Gold claims with an evidence-linked candidate: {claims['candidate_found']}/{claims['gold_total']}",
        f"- Provisional semantic claim matches: {claims['likely_semantic_match']}/{claims['gold_total']}",
        f"- Gold entities found: {len(entities['matches']) - len(entities['missing'])}/{len(entities['matches'])}",
        f"- Extra generated entities: {len(entities['extra'])}",
        f"- Gold wiki facts provisionally represented anywhere: {wiki_facts['provisionally_represented']}/{wiki_facts['gold_total']}",
        f"- Active generated claims placed: {projection['active_placed']}/{projection['active_claims']}",
        f"- Active generated claims rendered: {projection['active_rendered']}/{projection['active_claims']}",
        "",
        "## Known capability boundary",
        "",
        "Source retraction is deliberately reported as unsupported. The runner did not mutate artifacts to imitate the gold checkpoint, so Northstar material may remain in the final generated wiki.",
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
        f"- Extras: {[item['title'] for item in entities['extra']] or 'none'}",
        "",
        "## Generated pages",
        "",
    ]
    for page in comparison["generated_pages"]:
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
        detail = action.get("error") or action.get("reason") or action.get("result", "ok")
        lines.append(f"- `{action['action']}`: {detail}")
    lines.extend(
        [
            "",
            "See `comparison.json` for every gold claim and its best generated candidate, and `checkpoints/` for full snapshots and generated Markdown at each lifecycle boundary.",
            "",
        ]
    )
    return "\n".join(lines)


def refresh_daily_driver_comparison(
    fixture_dir: Path, output_dir: Path, *, config_path: Path | None = None
) -> dict[str, Any]:
    """Recompute diagnostics for a completed run without invoking an LLM."""
    fixture = load_fixture(fixture_dir)
    run = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    memory = Mycelium(
        output_dir / "store", config_path=config_path, memory_profile="user"
    )
    comparison = compare_final(fixture, memory)
    _write_json(output_dir / "comparison.json", comparison)
    (output_dir / "REPORT.md").write_text(
        _report_markdown(run, comparison, run["actions"]), encoding="utf-8"
    )
    return comparison


async def run_daily_driver(
    fixture_dir: Path, output_dir: Path, *, config_path: Path | None = None
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
    _configure_user(memory, str(fixture["scenario"]["user"]["name"]))
    actions: list[dict[str, Any]] = []
    checkpoint_ids: list[str] = []
    for episode in fixture["scenario"]["episodes"]:
        await _ingest_episode(
            memory,
            episode,
            user_speaker_label=str(fixture["scenario"]["user"]["speaker_label"]),
        )
        for action in episode.get("actions_after") or []:
            kind, _, value = str(action).partition(":")
            event: dict[str, Any] = {"episode": episode["id"], "action": action}
            try:
                if kind == "dream":
                    event["result"] = _jsonable(await memory.dream())
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
    comparison = compare_final(fixture, memory)
    run = {
        "scenario_id": fixture["scenario"]["scenario_id"],
        "model": memory.config.llm.model,
        "ollama_url": memory.config.llm.url,
        "config_path": str(config_path) if config_path else None,
        "checkpoint_ids": checkpoint_ids,
        "actions": actions,
    }
    _write_json(output_dir / "run.json", run)
    _write_json(output_dir / "comparison.json", comparison)
    (output_dir / "REPORT.md").write_text(
        _report_markdown(run, comparison, actions), encoding="utf-8"
    )
    return {"run": run, "comparison": comparison, "output_dir": str(output_dir)}
