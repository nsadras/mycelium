"""Compare prose rendering with keyed claims versus the same ordered records."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.fact_groups import FactText, fact_text_prompt


def cases():
    groups = [
        (
            "combined_responsibility",
            "Isha",
            [
                "Isha will draft the exhibition evaluation rubric and recruit the guides.",
                "Isha plans to lead exhibition evaluation and recruit four guides.",
            ],
        ),
        (
            "conditional_schedule",
            "Workshop",
            [
                "The workshop is scheduled for Wednesday.",
                "The workshop will proceed only if the inspection passes on Tuesday.",
            ],
        ),
        (
            "identifier_in_content",
            "Test procedure",
            [
                "The operator runs test C001 before every shipment.",
                "Test C001 verifies that the coolant valve opens.",
            ],
        ),
    ]
    for name, owner, texts in groups:
        yield (
            name,
            owner,
            {
                f"C{i:03d}": {
                    "text": text,
                    "temporal_status": "current",
                    "temporal": [],
                    "source_times": [],
                }
                for i, text in enumerate(texts, 1)
            },
        )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-request", type=Path, action="append", default=[])
    args = parser.parse_args()
    root = fresh_run_root("fact-prose-input-contract")
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump(mode="json"))
    (root / "probe.py").write_text(Path(__file__).read_text())
    llm.client = RecordingClient(llm.client, root / "requests")
    inputs = list(cases())
    for path in args.frozen_request:
        raw = json.loads(path.read_text())["request"]["messages"][1]["content"].split(
            "\n\nOUTPUT CONTRACT", 1
        )[0]
        owner = raw.split("SUBJECT\n", 1)[1].split("\n\nCANONICAL STORED CLAIMS", 1)[0]
        claims = json.loads(raw.split("CANONICAL STORED CLAIMS\n", 1)[1])
        inputs.append((str(path), owner, claims))
    rows = []
    print("OUTPUT", root, flush=True)
    for trial in range(3):
        for name, owner, claims in inputs:
            for arm, value in [("keyed", claims), ("ordered", list(claims.values()))]:
                system, user = fact_text_prompt(
                    owner,
                    json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
                )
                row = {"trial": trial, "case": name, "arm": arm, "status": "running"}
                rows.append(row)
                write(root / "results.json", rows)
                try:
                    text = FactText.model_validate(
                        await llm.call_structured(
                            system,
                            user,
                            FactText,
                            num_predict=1024,
                            debug_label="fact-prose-input-probe",
                        )
                    ).text
                    row.update(status="complete", text=text)
                except Exception as exc:
                    row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                write(root / "results.json", rows)
                print(trial, name, arm, row.get("text", row.get("error")), flush=True)
    write(
        root / "completion.json",
        {
            "complete": sum(r["status"] == "complete" for r in rows),
            "total": len(rows),
            "assessment_status": "requires_source_review",
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
