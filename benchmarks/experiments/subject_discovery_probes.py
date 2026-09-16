"""Neutral source-first type and identity-scope discovery probes."""

import asyncio
import json
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from mycelium.config import Config
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt


CASES = [
    (
        "new_colleague",
        "Nora is a new colleague who joined the museum team.",
        {"person"},
    ),
    (
        "software_project",
        "Nora is a software project for museum catalogs.",
        {"project"},
    ),
    (
        "shared_name",
        "Nora, the person, maintains a software project also called Nora.",
        {"person", "project"},
    ),
    (
        "ambiguous_person",
        "Alex offered to help. No surname or other identifying information is available.",
        {"person"},
    ),
    (
        "person_and_project",
        "Rin Patel leads Orchard, an ongoing toolchain upgrade project.",
        {"person", "project"},
    ),
]


async def main():
    root = fresh_run_root("subject-discovery")
    config = Config.from_toml(Path("mycelium.toml")).llm
    qa = OllamaQaClient(config.model, config.url, llm_config=config)
    qa.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", vars(config))
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(config.url.rstrip("/") + "/api/tags")
        response.raise_for_status()
        write(root / "models.json", response.json())
    schema = subject_discovery_model(["C001"], {}, {})
    results = []
    for trial in range(3):
        for name, text, expected in CASES:
            evidence = json.dumps(
                {
                    "claims": {
                        "C001": {
                            "text": text,
                            "citations": [{"source_id": "S", "segment_id": "S1"}],
                        }
                    },
                    "sources": {"S": {"segments": {"S1": {"text": text}}}},
                }
            )
            system, user = subject_discovery_prompt(evidence, "none")
            record = {
                "trial": trial,
                "case": name,
                "system": system,
                "user": user,
                "schema": schema.model_json_schema(),
            }
            results.append(record)
            write(root / "results.json", results)
            response = schema.model_validate(
                await qa.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=4096,
                    debug_label="subject-discovery-probe",
                )
            ).model_dump()
            types = {s["entity_type"] for s in response["subjects"]}
            record.update(
                response=response,
                passed=types == expected and len(response["subjects"]) == len(expected),
            )
            write(root / "results.json", results)
            print(trial, name, record["passed"], response, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(r["passed"] for r in results):
        raise SystemExit("Source-first discovery failed a neutral case")


if __name__ == "__main__":
    asyncio.run(main())
