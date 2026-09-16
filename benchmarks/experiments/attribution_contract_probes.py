"""Direct neutral proof of source attribution before page presentation.

Run with the configured model. Requests, intermediate decisions and failures are
retained; fixture expectations are never included in model inputs.
"""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.artifacts import EntityRecord
from mycelium.config import Config
from mycelium.consolidation_formatting import RoutingFormatter


from mycelium.source_attribution import (
    source_attribution_model as attribution_model,
    source_attribution_prompt,
    attributed_pages,
)
from mycelium.page_plan import page_plan_model as presentation_model, page_plan_prompt


def cases():
    user = {
        "entity_id": "you",
        "entity_type": "you",
        "title": "You",
        "participant_bindings": ["P001"],
    }
    basic = [
        (
            "other_person",
            "Morgan Vale is a cabinetmaker. Morgan will deliver the cabinet.",
            "Morgan Vale is a cabinetmaker who will deliver the cabinet.",
            "person",
            "Morgan Vale",
            {"other"},
        ),
        (
            "owned_item",
            "I own a hand drill.",
            "The user owns a hand drill.",
            "artifact",
            "Hand Drill",
            {"you", "other"},
        ),
        (
            "explicit_relationship",
            "Morgan agreed to repair my desk.",
            "Morgan agreed to repair the user's desk.",
            "person",
            "Morgan",
            {"you", "other"},
        ),
        (
            "reported_event",
            "A bridge in Porto reopened.",
            "A bridge in Porto reopened.",
            "artifact",
            "Bridge",
            {"other"},
        ),
        (
            "self",
            "I prefer written progress reports.",
            "The user prefers written progress reports.",
            None,
            None,
            {"you"},
        ),
        (
            "reported_project",
            "The community catalog project now has 150 entries.",
            "The community catalog project now has 150 entries.",
            "project",
            "Community Catalog",
            {"other"},
        ),
    ]
    for name, raw, statement, kind, title, described in basic:
        subjects = [user]
        if kind:
            subjects += [
                {
                    "entity_id": "other",
                    "entity_type": kind,
                    "title": title,
                    "participant_bindings": [],
                }
            ]
        pages = described & {"you"}
        yield (
            name,
            subjects,
            raw,
            statement,
            {"you"},
            set(),
            described,
            pages,
            "you" if pages else None,
        )
    subjects = [
        user,
        {
            "entity_id": "actor",
            "entity_type": "person",
            "title": "Morgan",
            "participant_bindings": [],
        },
        {
            "entity_id": "project",
            "entity_type": "project",
            "title": "Community Catalog",
            "participant_bindings": [],
        },
    ]
    broad = [
        (
            "personal_relationship",
            "Morgan repairs my furniture.",
            {"actor", "you"},
            set(),
            {"actor", "you"},
            "actor",
        ),
        (
            "joint_role",
            "Morgan leads evaluation for the community catalog project.",
            {"actor", "project"},
            set(),
            {"actor", "project"},
            "actor",
        ),
        (
            "user_role",
            "I lead evaluation for the community catalog project.",
            {"you", "project"},
            set(),
            {"you", "project"},
            "you",
        ),
        (
            "explicit_reporting_event",
            "I presented the budget to the community catalog project's board.",
            {"you", "project"},
            set(),
            {"you", "project"},
            "you",
        ),
        (
            "excluded_occurrence",
            "I corrected one spelling in the community catalog project.",
            {"you", "project"},
            {"project"},
            {"you"},
            "you",
        ),
        (
            "no_pages",
            "Morgan leads evaluation for the community catalog project.",
            {"actor", "project"},
            set(),
            set(),
            None,
        ),
        (
            "project_with_coordinator",
            "Community Catalog is a four-month digitization project with a budget of 600 units; Morgan is its coordinator.",
            {"actor", "project"},
            set(),
            {"actor", "project"},
            "project",
        ),
    ]
    for name, statement, described, excluded, pages, primary in broad:
        eligible = set() if name == "no_pages" else {"you", "actor", "project"}
        yield (
            name,
            subjects,
            statement,
            statement,
            eligible,
            excluded,
            described,
            pages,
            primary,
        )


async def decide(llm, subjects, evidence, eligible, excluded):
    types = {s["entity_id"]: s["entity_type"] for s in subjects}
    participants = {s["entity_id"] for s in subjects if s["participant_bindings"]}
    schema = attribution_model(evidence["claims"], types, participants)
    system, user = source_attribution_prompt(subjects, evidence)
    attribution = schema.model_validate(
        await llm.call_structured(
            system,
            user,
            schema,
            num_predict=8192,
            debug_label="source-attribution-probe",
        )
    ).model_dump()["attributions"]
    pages = attributed_pages(attribution, eligible, excluded)
    presentation = {}
    if any(pages.values()):
        registry = json.loads(
            RoutingFormatter.entity_catalog(
                [
                    EntityRecord(
                        s["entity_id"],
                        s["entity_type"],
                        s["title"],
                        s["entity_id"],
                        [],
                        "active",
                        "2031-05-06",
                        "2031-05-06",
                    )
                    for s in subjects
                    if s["entity_id"] in eligible
                ],
                include_sections=True,
            )
        )
        schema = presentation_model(pages, types)
        system, user = page_plan_prompt(registry, attribution, evidence)
        presentation = schema.model_validate(
            await llm.call_structured(
                system,
                user,
                schema,
                num_predict=8192,
                debug_label="attributed-page-presentation-probe",
            )
        ).model_dump()["decisions"]
    return attribution, presentation, pages


async def main(args):
    root = fresh_run_root("attribution-contract")
    print("OUTPUT", root, flush=True)
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump())
    llm.client = RecordingClient(llm.client, root / "requests")
    results, stopped = [], False
    for trial in range(args.trials):
        for (
            name,
            subjects,
            raw,
            statement,
            eligible,
            excluded,
            expected,
            expected_pages,
            primary,
        ) in cases():
            row = {"trial": trial, "case": name, "status": "running", "passed": False}
            results.append(row)
            write(root / "results.json", results)
            evidence = {
                "claims": {
                    "C001": {
                        "text": statement,
                        "citations": [{"source_id": "source", "segment_id": "S001"}],
                    }
                },
                "participants": {
                    "P001": {"name": "Rae", "role": "user", "source_id": "source"}
                },
                "sources": {
                    "source": {
                        "source_type": "agent_conversation",
                        "segments": {
                            "S001": {"speaker": "Rae", "role": "user", "text": raw}
                        },
                    }
                },
            }
            try:
                attribution, presentation, pages = await decide(
                    llm, subjects, evidence, eligible, {"C001": excluded}
                )
                actual = {
                    eid
                    for eid, r in attribution["C001"].items()
                    if r["relation_to_claim"] == "described"
                }
                checks = {
                    "attribution": actual == expected,
                    "pages": set(pages["C001"]) == expected_pages,
                    "primary": presentation.get("C001", {}).get("primary_subject")
                    == primary,
                }
                row.update(
                    status="complete",
                    attribution=attribution,
                    presentation=presentation,
                    checks=checks,
                    passed=all(checks.values()),
                )
            except (ConnectionError, httpx.TransportError) as exc:
                row.update(
                    status="infrastructure_failure",
                    error=f"{type(exc).__name__}: {exc}",
                )
                stopped = True
            except Exception as exc:
                row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            write(root / "results.json", results)
            print(
                trial,
                name,
                row["passed"],
                row.get("checks", row.get("error")),
                flush=True,
            )
            if stopped:
                break
        if stopped:
            break
    write(
        root / "completion.json",
        {
            "status": "incomplete" if stopped else "complete",
            "passed": sum(r["passed"] for r in results),
            "attempted": len(results),
            "planned": args.trials * len(list(cases())),
        },
    )
    if stopped or not all(r["passed"] for r in results):
        raise SystemExit("Attribution contract acceptance did not pass")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    asyncio.run(main(parser.parse_args()))
