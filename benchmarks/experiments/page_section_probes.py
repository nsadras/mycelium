"""Direct neutral tests of production content-only page sections."""

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
from mycelium.page_plan import page_plan_model, page_plan_prompt

CASES = [
    (
        "unnamed_effort",
        "project",
        "Garden Restoration",
        "The garden restoration project does not have a name yet.",
        {"overview", "current_status", "decisions"},
    ),
    (
        "open_choice",
        "project",
        "Garden Restoration",
        "The garden restoration team has not decided which greenhouse design to use.",
        {"current_status", "decisions", "next_steps_deadlines"},
    ),
    (
        "planned_review",
        "project",
        "Garden Restoration",
        "The garden restoration team will review its budget next week.",
        {"next_steps_deadlines"},
    ),
    (
        "personal_priority",
        "you",
        "You",
        "The user plans to learn bookbinding.",
        {"priorities_plans"},
    ),
    (
        "person",
        "person",
        "Devon",
        "Devon restores musical instruments.",
        {"profile", "current_context"},
    ),
    (
        "artifact",
        "artifact",
        "Survey Notebook",
        "The survey notebook contains measurements of the orchard.",
        {"overview", "purpose", "current_state"},
    ),
    (
        "place",
        "place",
        "East Annex",
        "The East Annex has a public reading room.",
        {"overview", "current_context"},
    ),
]


async def main():
    root = fresh_run_root("content-section-contract")
    print("OUTPUT", root, flush=True)
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump(mode="json"))
    (root / "probe.py").write_text(Path(__file__).read_text())
    llm.client = RecordingClient(llm.client, root / "requests")
    rows = []
    for trial in range(3):
        for name, kind, title, statement, expected in CASES:
            eid = "you" if kind == "you" else "subject"
            registry = json.loads(
                RoutingFormatter.entity_catalog(
                    [
                        EntityRecord(
                            eid,
                            kind,
                            title,
                            "subject",
                            [],
                            "active",
                            "2031-01-01",
                            "2031-01-01",
                        )
                    ],
                    include_sections=True,
                )
            )
            schema = page_plan_model({"C1": [eid]}, {eid: kind})
            evidence = {
                "claims": {
                    "C1": {
                        "text": statement,
                        "citations": [{"source_id": "S", "segment_id": "S1"}],
                    }
                },
                "sources": {"S": {"segments": {"S1": {"text": statement}}}},
            }
            system, user = page_plan_prompt(
                registry,
                {
                    "C1": {
                        eid: {
                            "relation_to_claim": "described",
                            "reason": "This source describes the supplied subject.",
                        }
                    }
                },
                evidence,
            )
            row = {"trial": trial, "case": name, "status": "running", "passed": False}
            rows.append(row)
            write(root / "results.json", rows)
            result = schema.model_validate(
                await llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=2048,
                    debug_label="content-section-probe",
                )
            ).model_dump()
            d = result["decisions"]["C1"]
            row.update(
                status="complete",
                response=result,
                passed=d["pages"][eid] in expected and d["uncertainty"] is None,
            )
            write(root / "results.json", rows)
            print(trial, name, row["passed"], d, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in rows), "total": len(rows)},
    )


asyncio.run(main())
