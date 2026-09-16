"""Prove page admission and placement scoped by exact human evidence reviews."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path


from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.artifacts import EntityRecord
from mycelium.config import Config
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.page_admission import (
    NO_PAGE_BASIS,
    page_admission_model,
    page_admission_prompt,
)
from benchmarks.experiments.attribution_contract_probes import decide
from mycelium.telemetry import trace_operation


def cases():
    claims = {
        "C001": "The user used a hand drill to fix a shelf.",
        "C002": "The hand drill is a restored precision instrument with an ongoing maintenance log; its gearbox needs oil every month.",
        "C003": "The user prefers repairing household furniture to replacing it.",
    }
    for name, keys, state in [
        ("only_reviewed_support", ["C001"], "provisional"),
        ("independent_support", ["C001", "C002", "C003"], "provisional"),
        ("existing_page", ["C001", "C002", "C003"], "materialized"),
    ]:
        yield (
            name,
            {k: claims[k] for k in keys},
            state,
            "artifact",
            "artifact-drill",
            "Hand drill",
        )
    yield (
        "independent_project_support",
        {
            "C001": "The user checked one spelling in the museum catalog project.",
            "C002": "The museum catalog project is an ongoing digitization effort led by Rae, with a dedicated budget and quarterly releases.",
            "C003": "The user prefers searchable archives to printed inventories.",
        },
        "provisional",
        "project",
        "project-catalog",
        "Museum catalog project",
    )


async def main(args):
    root = fresh_run_root("page-review-contract")
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump())
    llm.client = RecordingClient(llm.client, root / "requests")
    write(
        root / "experiment.json",
        {
            "concurrent_benchmark": args.concurrent_benchmark,
            "latencies_comparable": not bool(args.concurrent_benchmark),
        },
    )
    print("OUTPUT", root, flush=True)
    results = []
    for trial in range(args.trials):
        for name, claims, state, subject_kind, subject_id, subject_title in cases():
            entities = {
                eid: EntityRecord(
                    eid,
                    kind,
                    title,
                    eid,
                    [],
                    "active",
                    "2031-05-06",
                    "2031-05-06",
                    materialization_state=page_state,
                )
                for eid, kind, title, page_state in [
                    ("you", "you", "You", "materialized"),
                    (subject_id, subject_kind, subject_title, state),
                ]
            }
            excluded = {"C001": {subject_id}}
            plan = json.dumps(
                {
                    "subjects": [
                        {
                            "entity_id": eid,
                            "entity_type": e.entity_type,
                            "title": e.title,
                        }
                        for eid, e in entities.items()
                    ],
                    "human_page_reviews": [
                        {
                            "entity_id": subject_id,
                            "claim_ids": ["C001"],
                            "page_state": "no_page",
                        }
                    ],
                }
            )
            evidence = json.dumps(
                {
                    "claims": {
                        cid: {
                            "text": text,
                            "citations": [{"source_id": "source", "segment_id": cid}],
                        }
                        for cid, text in claims.items()
                    },
                    "sources": {
                        "source": {
                            "segments": {
                                cid: {"text": text} for cid, text in claims.items()
                            }
                        }
                    },
                }
            )
            record = {"trial": trial, "case": name}
            try:
                admissions = {}
                if state == "provisional":
                    schema = page_admission_model(
                        claims, entities, excluded_pages=excluded
                    )
                    system, user = page_admission_prompt(
                        RoutingFormatter.entity_catalog(
                            entities.values(), include_sections=False
                        ),
                        plan,
                        evidence,
                        reviewed_pages=True,
                    )
                    with trace_operation(
                        "page_review_admission_probe", case=name, trial=trial
                    ):
                        admissions = schema.model_validate(
                            await llm.call_structured(
                                system,
                                user,
                                schema,
                                num_predict=4096,
                                debug_label="page-review-admission-probe",
                            )
                        ).model_dump()["page_admissions"]
                routable = {
                    eid: e.entity_type
                    for eid, e in entities.items()
                    if e.materialization_state == "materialized"
                    or admissions[eid]["basis"] != NO_PAGE_BASIS
                }
                subjects = [
                    {
                        "entity_id": eid,
                        "entity_type": e.entity_type,
                        "title": e.title,
                        "participant_bindings": [],
                    }
                    for eid, e in entities.items()
                ]
                with trace_operation(
                    "page_review_placement_probe", case=name, trial=trial
                ):
                    attribution, placements, _ = await decide(
                        llm, subjects, json.loads(evidence), routable, excluded
                    )
                record["attribution"] = attribution
                scope_passed = subject_id not in placements.get("C001", {}).get(
                    "pages", {}
                ) and "you" in placements.get("C001", {}).get("pages", {})
                passed = scope_passed
                if "C002" in claims:
                    passed = passed and subject_id in placements.get("C002", {}).get(
                        "pages", {}
                    )
                else:
                    passed = passed and admissions[subject_id]["basis"] == NO_PAGE_BASIS
                record.update(
                    admissions=admissions,
                    placements=placements,
                    passed=passed,
                    review_scope_passed=scope_passed,
                )
            except Exception as exc:
                record.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            results.append(record)
            write(root / "results.json", results)
            print(trial, name, record["passed"], record.get("error", ""), flush=True)
    write(
        root / "completion.json",
        {
            "passed": sum(r["passed"] for r in results),
            "total": len(results),
            "review_scope_passed": sum(
                r.get("review_scope_passed", False) for r in results
            ),
        },
    )
    if not all(r.get("review_scope_passed", False) for r in results):
        raise SystemExit("Page review contract failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--concurrent-benchmark")
    asyncio.run(main(parser.parse_args()))
