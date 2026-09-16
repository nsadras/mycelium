"""Neutral direct probes for truth comparisons independent of page ownership."""

import asyncio
import json
import sys
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from mycelium.config import Config
from mycelium.truth_contract import truth_candidates_model, truth_comparison_model, truth_comparison_prompt
from mycelium.prompting import render_prompt_pair


CASES = [
    ("cross_owner", "Mara will deliver the draft on Friday.",
     "Mara corrected the draft delivery plan: Monday replaces Friday.",
     "project-draft", "person-mara", "right_supersedes_left"),
    ("same_batch", "The hall reservation for the concert on 2031-06-07 costs 80 euros.",
     "The hall reservation for the same concert on 2031-06-07 costs 120 euros.",
     "concert", "venue", "contradicts"),
    ("reverse_order", "Mara corrected the draft delivery plan: Monday replaces Friday.",
     "Mara will deliver the draft on Friday.", "person-mara", "project-draft", "left_supersedes_right"),
    ("coexisting_plans", "Mara plans to learn pottery.", "Mara plans to learn guitar.",
     "person-mara", "person-mara", "no_change"),
    ("different_people", "Mara lives in Oslo.", "Jules lives in Rome.",
     "household", "household", "no_change"),
    ("different_events", "The January lecture begins at 10:00.", "The February lecture begins at 11:00.",
     "lecture-series", "lecture-series", "no_change"),
]


async def main():
    candidate_mode = "--candidates" in sys.argv
    root = fresh_run_root("truth-candidates" if candidate_mode else "truth-scope")
    config = Config.from_toml(Path("mycelium.toml")).llm
    qa = OllamaQaClient(model=config.model, url=config.url, llm_config=config)
    qa.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", vars(config))
    async with httpx.AsyncClient(timeout=10) as client:
        tags = await client.get(config.url.rstrip("/") + "/api/tags")
        tags.raise_for_status()
        write(root / "models.json", tags.json())
    schema = truth_candidates_model({"C001": ["X001", "X003"]}) if candidate_mode else truth_comparison_model(["P001"])
    results = []
    for trial in range(3):
        for name, left, right, left_owner, right_owner, expected in CASES:
            payload = {"P001": {
                "left": {"claim_id": "L", "text": left, "page_owner": left_owner,
                         "citations": [{"segment_id": "S1", "text": left}]},
                "right": {"claim_id": "R", "text": right, "page_owner": right_owner,
                          "citations": [{"segment_id": "S2", "text": right}]},
            }}
            if candidate_mode:
                pair = payload["P001"]
                system, user = render_prompt_pair("memory/truth_candidates", payload=json.dumps({
                    "incoming": {"C001": pair["right"]}, "candidates": {
                        "X001": pair["left"], "X002": pair["right"],
                        "X003": {"claim_id": "O", "text": "Eden prefers quiet rooms.", "page_owner": "household"},
                    },
                    "eligible_candidates": {"C001": ["X001", "X003"]},
                }))
            else:
                system, user = truth_comparison_prompt(json.dumps(payload))
            record = {"trial": trial, "case": name, "system": system, "user": user,
                      "schema": schema.model_json_schema(), "expected_relation": expected}
            results.append(record)
            write(root / "results.json", results)
            response = await qa.llm.call_structured(system, user, schema, num_predict=2048,
                                                    debug_label="truth-scope-probe", think=True)
            if candidate_mode:
                decision = schema.model_validate(response).model_dump()["decisions"]["C001"]
                selected = {target for target, value in decision["candidates"].items() if value != "unrelated"}
                passed = selected <= {"X001"} and (expected == "no_change" or "X001" in selected)
            else:
                decision = schema.model_validate(response).model_dump()["comparisons"]["P001"]
                passed = decision["relation"] == expected
            record.update(response=response, passed=passed)
            write(root / "results.json", results)
            print(name, trial, decision, record["passed"], flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Truth-scope contract failed a neutral case")


if __name__ == "__main__":
    asyncio.run(main())
