"""Validation utilities for the Daily Driver executable memory specification."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from mycelium.models import PAGE_SECTION_KEYS, PAGE_TYPES


REQUIRED_FILES = {
    "scenario.yaml",
    "gold_claims.yaml",
    "gold_checkpoints.yaml",
    "gold_wiki.yaml",
    "probes.yaml",
    "rubric.yaml",
}


def load_fixture(fixture_dir: Path) -> dict[str, Any]:
    missing = sorted(
        name for name in REQUIRED_FILES if not (fixture_dir / name).exists()
    )
    if missing:
        raise ValueError(f"Missing fixture files: {', '.join(missing)}")
    return {
        name.removesuffix(".yaml"): _load_yaml(fixture_dir / name)
        for name in sorted(REQUIRED_FILES)
    }


def validate_fixture(fixture_dir: Path) -> dict[str, Any]:
    data = load_fixture(fixture_dir)
    scenario = data["scenario"]
    gold_claims = data["gold_claims"]
    checkpoints = data["gold_checkpoints"]
    wiki = data["gold_wiki"]
    probes = data["probes"]
    rubric = data["rubric"]
    errors: list[str] = []

    scenario_id = str(scenario.get("scenario_id") or "")
    for name, document in data.items():
        if document.get("schema_version") != 1:
            errors.append(f"{name}: schema_version must be 1")
        if document.get("scenario_id") != scenario_id:
            errors.append(f"{name}: scenario_id does not match {scenario_id!r}")

    episodes = scenario.get("episodes") or []
    episode_ids = _unique_ids(episodes, "episode", errors)
    source_ids = _unique_values(episodes, "source_id", "source", errors)
    segments = [
        segment for episode in episodes for segment in episode.get("segments") or []
    ]
    segment_ids = _unique_ids(segments, "segment", errors)
    segment_by_id = {str(segment.get("id")): segment for segment in segments}
    user = scenario.get("user") or {}
    user_name = str(user.get("name") or "").strip()
    user_label = str(user.get("speaker_label") or "").strip()
    if user.get("id") != "you":
        errors.append("scenario user id must be 'you'")
    if not user_name or not user_label:
        errors.append("scenario user requires name and speaker_label")
    if user.get("identity_authority") != "configured_profile":
        errors.append("scenario user identity must come from configured_profile")
    if user_name and any(segment.get("speaker") == user_name for segment in segments):
        errors.append("configured user name cannot be used as a source speaker label")
    for episode in episodes:
        episode_segments = episode.get("segments") or []
        has_user_turn = any(
            segment.get("speaker") == user_label for segment in episode_segments
        )
        participants = set(episode.get("participants") or [])
        if has_user_turn and user_label not in participants:
            errors.append(
                f"episode {episode.get('id')}: user speaker label is absent from participants"
            )
        for segment in episode_segments:
            if segment.get("role") == "user" and segment.get("speaker") != user_label:
                errors.append(
                    f"segment {segment.get('id')}: user role must use configured speaker label"
                )

    claims = gold_claims.get("claims") or []
    claim_ids = _unique_ids(claims, "claim", errors)
    claim_by_id = {str(claim.get("id")): claim for claim in claims}
    fact_ids = {str(claim.get("fact_id")) for claim in claims if claim.get("fact_id")}
    ignored = gold_claims.get("ignored_segments") or []
    ignored_ids = _unique_ids(ignored, "ignored segment", errors)

    evidenced_segments: set[str] = set()
    for claim in claims:
        claim_id = str(claim.get("id"))
        for evidence_id in claim.get("evidence") or []:
            evidence_id = str(evidence_id)
            evidenced_segments.add(evidence_id)
            if evidence_id not in segment_ids:
                errors.append(
                    f"claim {claim_id}: unknown evidence segment {evidence_id}"
                )
        owner = str(claim.get("owner") or "")
        if not owner:
            errors.append(f"claim {claim_id}: owner is required")
        for relation in ("superseded_by",):
            target = claim.get(relation)
            if target and target not in claim_ids:
                errors.append(f"claim {claim_id}: unknown {relation} claim {target}")
        if claim.get("retracted_by") and claim["retracted_by"] not in source_ids:
            errors.append(
                f"claim {claim_id}: unknown retracted source {claim['retracted_by']}"
            )

    overlap = evidenced_segments & ignored_ids
    if overlap:
        errors.append(
            f"segments cannot be both evidence and ignored: {sorted(overlap)}"
        )
    for ignored_id in ignored_ids:
        if ignored_id not in segment_ids:
            errors.append(f"ignored segment does not exist: {ignored_id}")

    expected_source_only = {
        segment_id
        for segment_id, segment in segment_by_id.items()
        if segment.get("retention") in {"source_only", "retraction_instruction"}
    }
    if expected_source_only != ignored_ids:
        errors.append(
            "ignored segment manifest does not equal source-only/retraction segments: "
            f"missing={sorted(expected_source_only - ignored_ids)}, "
            f"extra={sorted(ignored_ids - expected_source_only)}"
        )
    expected_claim_evidence = {
        segment_id
        for segment_id, segment in segment_by_id.items()
        if segment.get("retention") in {"claim", "claim_then_retract"}
    }
    if expected_claim_evidence - evidenced_segments:
        errors.append(
            "claim-bearing segments lack gold provenance: "
            f"{sorted(expected_claim_evidence - evidenced_segments)}"
        )

    checkpoint_rows = checkpoints.get("checkpoints") or []
    checkpoint_ids = _unique_ids(checkpoint_rows, "checkpoint", errors)
    for checkpoint in checkpoint_rows:
        checkpoint_id = str(checkpoint.get("id"))
        if checkpoint.get("after_episode") not in episode_ids:
            errors.append(
                f"checkpoint {checkpoint_id}: unknown episode {checkpoint.get('after_episode')}"
            )
        _validate_checkpoint_claims(
            checkpoint, checkpoint_id, claim_ids, fact_ids, errors
        )

    action_checkpoints = {
        action.split(":", 1)[1]
        for episode in episodes
        for action in episode.get("actions_after") or []
        if isinstance(action, str) and action.startswith("checkpoint:")
    }
    if action_checkpoints != checkpoint_ids:
        errors.append(
            "scenario/checkpoint actions differ: "
            f"missing={sorted(checkpoint_ids - action_checkpoints)}, "
            f"extra={sorted(action_checkpoints - checkpoint_ids)}"
        )

    entities = wiki.get("entities") or []
    entity_ids = _unique_ids(entities, "wiki entity", errors)
    entity_by_id = {str(entity.get("id")): entity for entity in entities}
    retracted_entities = wiki.get("retracted_entities") or []
    retracted_entity_ids = _unique_ids(retracted_entities, "retracted entity", errors)
    all_entity_ids = entity_ids | retracted_entity_ids
    gold_you = entity_by_id.get("you")
    if gold_you and user_name not in set(gold_you.get("aliases") or []):
        errors.append("configured user name must be an alias of the gold You entity")
    for entity in [*entities, *retracted_entities]:
        if entity.get("type") not in PAGE_TYPES:
            errors.append(
                f"entity {entity.get('id')}: unsupported type {entity.get('type')}"
            )
    for claim in claims:
        if claim.get("owner") not in all_entity_ids:
            errors.append(
                f"claim {claim.get('id')}: unknown owner {claim.get('owner')}"
            )
        for linked_entity_id in claim.get("linked_entities") or []:
            if linked_entity_id not in all_entity_ids:
                errors.append(
                    f"claim {claim.get('id')}: unknown linked entity {linked_entity_id}"
                )
    pages = wiki.get("pages") or []
    page_entity_ids = _unique_values(pages, "entity_id", "wiki page entity", errors)
    wiki_facts = wiki.get("facts") or []
    wiki_fact_ids = _unique_ids(wiki_facts, "wiki fact", errors)
    wiki_fact_by_id = {str(fact.get("id")): fact for fact in wiki_facts}

    if page_entity_ids != entity_ids:
        errors.append(
            "active entities and pages differ: "
            f"entities_without_pages={sorted(entity_ids - page_entity_ids)}, "
            f"pages_without_entities={sorted(page_entity_ids - entity_ids)}"
        )
    retracted_fact_ids = {
        str(claim.get("fact_id"))
        for claim in claims
        if claim.get("state") == "retracted"
    }
    expected_final_fact_ids = fact_ids - retracted_fact_ids
    if wiki_fact_ids != expected_final_fact_ids:
        errors.append(
            "final wiki fact registry differs from active/history claims: "
            f"missing={sorted(expected_final_fact_ids - wiki_fact_ids)}, "
            f"extra={sorted(wiki_fact_ids - expected_final_fact_ids)}"
        )
    for fact in wiki_facts:
        fact_id = str(fact.get("id"))
        expected_claim_ids = {
            claim_id
            for claim_id, claim in claim_by_id.items()
            if claim.get("fact_id") == fact_id
        }
        declared_claim_ids = {str(value) for value in fact.get("claim_ids") or []}
        if declared_claim_ids != expected_claim_ids:
            errors.append(
                f"wiki fact {fact_id}: claim_ids differ; "
                f"missing={sorted(expected_claim_ids - declared_claim_ids)}, "
                f"extra={sorted(declared_claim_ids - expected_claim_ids)}"
            )
        render_on = {str(value) for value in fact.get("render_on") or []}
        if render_on - entity_ids:
            errors.append(
                f"wiki fact {fact_id}: unknown render_on entities "
                f"{sorted(render_on - entity_ids)}"
            )
        if render_on:
            endpoint_ids = {
                str(value)
                for claim_id in declared_claim_ids
                for value in [
                    claim_by_id[claim_id].get("owner"),
                    *(claim_by_id[claim_id].get("linked_entities") or []),
                ]
                if value
            }
            if render_on - endpoint_ids:
                errors.append(
                    f"wiki fact {fact_id}: render_on is not grounded in claim endpoints "
                    f"{sorted(render_on - endpoint_ids)}"
                )

    rendered_fact_pages: dict[str, list[str]] = {}
    for page in pages:
        entity_id = str(page.get("entity_id"))
        entity = entity_by_id.get(entity_id)
        if entity:
            allowed_sections = {key for key, _ in PAGE_SECTION_KEYS[entity["type"]]}
            unknown_sections = set(page.get("sections") or {}) - allowed_sections
            if unknown_sections:
                errors.append(
                    f"page {entity_id}: invalid sections {sorted(unknown_sections)}"
                )
        for value in _section_fact_ids(page.get("sections") or {}):
            rendered_fact_pages.setdefault(value, []).append(entity_id)
            if value not in wiki_fact_by_id:
                errors.append(f"page {entity_id}: unknown fact {value}")
    for fact_id in sorted(wiki_fact_ids):
        fact = wiki_fact_by_id[fact_id]
        actual_pages = rendered_fact_pages.get(fact_id, [])
        declared_pages = {str(value) for value in fact.get("render_on") or []}
        if declared_pages:
            if set(actual_pages) != declared_pages or len(actual_pages) != len(
                declared_pages
            ):
                errors.append(
                    f"wiki fact {fact_id}: endpoint projections differ; "
                    f"expected={sorted(declared_pages)}, actual={sorted(actual_pages)}"
                )
        elif len(actual_pages) != 1:
            errors.append(
                f"wiki fact {fact_id}: ordinary facts must render once; "
                f"actual={sorted(actual_pages)}"
            )

    wiki_dir = fixture_dir / "wiki"
    markdown_files = {path.stem for path in wiki_dir.glob("*.md")}
    expected_slugs = {str(page.get("slug")) for page in pages}
    if markdown_files != expected_slugs:
        errors.append(
            "reference Markdown differs from structured pages: "
            f"missing={sorted(expected_slugs - markdown_files)}, "
            f"extra={sorted(markdown_files - expected_slugs)}"
        )
    for slug in sorted(markdown_files):
        text = (wiki_dir / f"{slug}.md").read_text(encoding="utf-8")
        markdown_fact_ids = set(re.findall(r"\b(?:f-[a-z0-9-]+)\b", text))
        structured_ids = {
            fact_id
            for page in pages
            if page.get("slug") == slug
            for fact_id in _section_fact_ids(page.get("sections") or {})
        }
        if markdown_fact_ids != structured_ids:
            errors.append(
                f"wiki/{slug}.md fact IDs differ: "
                f"missing={sorted(structured_ids - markdown_fact_ids)}, "
                f"extra={sorted(markdown_fact_ids - structured_ids)}"
            )

    probe_rows = probes.get("probes") or []
    probe_ids = _unique_ids(probe_rows, "probe", errors)
    for probe in probe_rows:
        probe_id = str(probe.get("id"))
        if probe.get("checkpoint") not in checkpoint_ids:
            errors.append(
                f"probe {probe_id}: unknown checkpoint {probe.get('checkpoint')}"
            )
        for fact_id in [
            *(probe.get("required_facts") or []),
            *(probe.get("forbidden_facts") or []),
        ]:
            if fact_id not in fact_ids:
                errors.append(f"probe {probe_id}: unknown fact {fact_id}")
        for evidence_id in [
            *(probe.get("required_evidence") or []),
            *(probe.get("forbidden_evidence") or []),
        ]:
            if evidence_id not in segment_ids:
                errors.append(f"probe {probe_id}: unknown evidence {evidence_id}")

    dimension_rows = rubric.get("dimensions") or []
    dimension_ids = _unique_ids(dimension_rows, "rubric dimension", errors)
    dimensions_by_id = {str(row.get("id")): row for row in dimension_rows}
    for row in dimension_rows:
        if "target" not in row:
            continue
        try:
            target = float(row["target"])
        except (TypeError, ValueError):
            errors.append(f"rubric dimension {row.get('id')}: target must be numeric")
            continue
        if not 0.0 <= target <= 1.0:
            errors.append(
                f"rubric dimension {row.get('id')}: target must be between 0 and 1"
            )
    acceptance_dimension_ids = rubric.get("acceptance", {}).get("dimensions") or []
    if len(acceptance_dimension_ids) != len(set(acceptance_dimension_ids)):
        errors.append("rubric acceptance dimensions contain duplicates")
    for dimension_id in acceptance_dimension_ids:
        if dimension_id not in dimension_ids:
            errors.append(
                f"rubric acceptance: unknown dimension {dimension_id}"
            )
        elif "target" not in dimensions_by_id[dimension_id]:
            errors.append(
                f"rubric acceptance: dimension {dimension_id} has no declared target"
            )
    active_gates = rubric.get("gates") or []
    deferred_gates = rubric.get("deferred_gates") or []
    gate_ids = _unique_ids(active_gates, "rubric gate", errors)
    all_gate_ids = _unique_ids(
        [*active_gates, *deferred_gates], "rubric active or deferred gate", errors
    )
    supported_gate_checks = {
        "checkpoint_checks",
        "probe",
        "distinct_entities",
        "forbidden_evidence_absent",
        "ownership_exact",
    }
    for gate in [*active_gates, *deferred_gates]:
        check = gate.get("check") or {}
        if check.get("type") not in supported_gate_checks:
            errors.append(
                f"rubric gate {gate.get('id')}: unsupported check type {check.get('type')}"
            )
        if check.get("checkpoint") and check["checkpoint"] not in checkpoint_ids:
            errors.append(
                f"rubric gate {gate.get('id')}: unknown checkpoint {check['checkpoint']}"
            )
        if check.get("probe_id") and check["probe_id"] not in probe_ids:
            errors.append(
                f"rubric gate {gate.get('id')}: unknown probe {check['probe_id']}"
            )
        for entity_id in check.get("entity_ids") or []:
            if entity_id not in all_entity_ids:
                errors.append(
                    f"rubric gate {gate.get('id')}: unknown entity {entity_id}"
                )

    final_checkpoint_id = str(
        checkpoints.get("final_checkpoint")
        or (checkpoint_rows[-1]["id"] if checkpoint_rows else "")
    )
    if final_checkpoint_id not in checkpoint_ids:
        errors.append(f"unknown final checkpoint {final_checkpoint_id}")

    final_checkpoint = next(
        (
            checkpoint
            for checkpoint in checkpoint_rows
            if checkpoint.get("id") == final_checkpoint_id
        ),
        None,
    )
    if final_checkpoint and final_checkpoint.get("exact_fact_count") != len(
        wiki_fact_ids
    ):
        errors.append(
            "cp8_final exact_fact_count does not match gold_wiki facts: "
            f"{final_checkpoint.get('exact_fact_count')} != {len(wiki_fact_ids)}"
        )

    summary = {
        "valid": not errors,
        "scenario_id": scenario_id,
        "episodes": len(episode_ids),
        "sources": len(source_ids),
        "segments": len(segment_ids),
        "claims": len(claim_ids),
        "consolidated_facts": len(wiki_fact_ids),
        "active_entities": len(entity_ids),
        "checkpoints": len(checkpoint_ids),
        "probes": len(probe_ids),
        "rubric_dimensions": len(dimension_ids),
        "acceptance_dimensions": len(acceptance_dimension_ids),
        "rubric_gates": len(gate_ids),
        "deferred_rubric_gates": len(all_gate_ids) - len(gate_ids),
        "errors": errors,
    }
    if errors:
        raise ValueError(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def _validate_checkpoint_claims(
    checkpoint: dict[str, Any],
    checkpoint_id: str,
    claim_ids: set[str],
    fact_ids: set[str],
    errors: list[str],
) -> None:
    claim_keys = {
        "canonical_claims",
        "withheld_from_authoritative_sections",
        "needs_review",
    }
    fact_keys = {
        "authoritative_facts",
        "historical_facts",
        "forbidden_current_facts",
        "forbidden_retrieval_facts",
    }
    queue = checkpoint.get("queue") or {}
    for key in ("pending", "deferred", "retryable"):
        for claim_id in queue.get(key) or []:
            if claim_id not in claim_ids:
                errors.append(
                    f"checkpoint {checkpoint_id}: unknown queued claim {claim_id}"
                )
    for key in claim_keys:
        for claim_id in checkpoint.get(key) or []:
            if claim_id not in claim_ids:
                errors.append(f"checkpoint {checkpoint_id}: unknown claim {claim_id}")
    for claim_id in checkpoint.get("claim_state_overrides") or {}:
        if claim_id not in claim_ids:
            errors.append(
                f"checkpoint {checkpoint_id}: unknown claim override {claim_id}"
            )
    for key in fact_keys:
        for fact_id in checkpoint.get(key) or []:
            if fact_id not in fact_ids:
                errors.append(f"checkpoint {checkpoint_id}: unknown fact {fact_id}")


def _section_fact_ids(sections: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for payload in sections.values():
        if isinstance(payload, list):
            values.extend(str(value) for value in payload)
        elif isinstance(payload, dict):
            values.extend(str(value) for value in payload.get("facts") or [])
    return values


def _unique_ids(rows: list[dict[str, Any]], label: str, errors: list[str]) -> set[str]:
    return _unique_values(rows, "id", label, errors)


def _unique_values(
    rows: list[dict[str, Any]], key: str, label: str, errors: list[str]
) -> set[str]:
    values = [str(row.get(key) or "") for row in rows]
    missing = sum(not value for value in values)
    if missing:
        errors.append(f"{label}: {missing} rows are missing {key}")
    duplicates = sorted(
        value for value, count in Counter(values).items() if value and count > 1
    )
    if duplicates:
        errors.append(f"{label}: duplicate {key} values {duplicates}")
    return {value for value in values if value}


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one YAML object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks.mycelium_bench.daily_driver"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("fixture_dir", type=Path)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("fixture_dir", type=Path)
    run_parser.add_argument("--output-dir", type=Path, required=True)
    run_parser.add_argument("--config-path", type=Path, default=Path("mycelium.toml"))
    run_parser.add_argument(
        "--replay-extraction-store",
        type=Path,
        help=(
            "Reuse only source, episode, claim, and raw-log extraction artifacts; "
            "rerun Dream, review actions, projection, retrieval, and answers."
        ),
    )
    run_parser.add_argument(
        "--skip-probe-answers",
        action="store_true",
        help="Run deterministic retrieval probes but skip answer generation and judging.",
    )
    run_parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Run independent end-to-end trials into trial-NN subdirectories.",
    )
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("fixture_dir", type=Path)
    compare_parser.add_argument("--output-dir", type=Path, required=True)
    compare_parser.add_argument(
        "--config-path", type=Path, default=Path("mycelium.toml")
    )
    args = parser.parse_args()
    if args.command == "validate":
        print(
            json.dumps(validate_fixture(args.fixture_dir), indent=2, ensure_ascii=False)
        )
    elif args.command == "run":
        import asyncio

        from benchmarks.mycelium_bench.daily_driver_run import (
            run_daily_driver,
            run_daily_driver_trials,
        )

        if args.trials < 1:
            parser.error("--trials must be at least 1")
        if args.trials > 1:
            summary = asyncio.run(
                run_daily_driver_trials(
                    args.fixture_dir,
                    args.output_dir,
                    trials=args.trials,
                    config_path=args.config_path,
                    replay_extraction_store=args.replay_extraction_store,
                    run_probe_answers=not args.skip_probe_answers,
                )
            )
            summary = {"output_dir": str(args.output_dir), **summary}
        else:
            result = asyncio.run(
                run_daily_driver(
                    args.fixture_dir,
                    args.output_dir,
                    config_path=args.config_path,
                    replay_extraction_store=args.replay_extraction_store,
                    run_probe_answers=not args.skip_probe_answers,
                )
            )
            summary = {
                "output_dir": result["output_dir"],
                "model": result["run"]["model"],
                "source_accounting": result["comparison"]["source_accounting"],
                "claim_comparison": {
                    key: value
                    for key, value in result["comparison"]["claim_comparison"].items()
                    if key != "rows"
                },
                "evaluation": result["evaluation"]["summary"],
            }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    elif args.command == "compare":
        from benchmarks.mycelium_bench.daily_driver_run import (
            refresh_daily_driver_comparison,
        )

        refreshed = refresh_daily_driver_comparison(
            args.fixture_dir,
            args.output_dir,
            config_path=args.config_path,
        )
        print(
            json.dumps(
                {
                    "output_dir": str(args.output_dir),
                    "source_accounting": refreshed["comparison"]["source_accounting"],
                    "projection": refreshed["comparison"]["projection"],
                    "evaluation": refreshed["evaluation"]["summary"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
