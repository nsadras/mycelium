"""Direct source discovery with the production ontology's type definitions."""

import asyncio
import json

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.page_admission_probes import CASES
from mycelium import Mycelium
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt


async def main():
    root = fresh_run_root("source-subject-types")
    memory = Mycelium(root / "store", config_path="mycelium.toml")
    memory.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", vars(memory.config.llm))
    write(root / "models.json", (await memory.llm.client.list()).model_dump())
    results = []
    for trial in range(3):
        for name, _, statements, _, _ in CASES:
            claims = {
                f"C{i:03d}": {
                    "text": text,
                    "citations": [
                        {"source_id": "source", "segment_id": f"segment-{i}"}
                    ],
                }
                for i, text in enumerate(statements, 1)
            }
            evidence = {
                "claims": claims,
                "sources": {
                    "source": {
                        "source_type": "agent_conversation",
                        "occurred_at": "2031-05-08",
                        "segments": {
                            f"segment-{i}": {"text": text}
                            for i, text in enumerate(statements, 1)
                        },
                    }
                },
            }
            schema = subject_discovery_model(claims, {}, {})
            system, user = subject_discovery_prompt(json.dumps(evidence), "none")
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
                await memory.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=8192,
                    debug_label="source-subject-types-probe",
                )
            ).model_dump()
            types = {s["entity_type"] for s in response["subjects"]}
            if name == "substantial_event":
                passed = "event" in types and "project" not in types
            elif name == "project_responsibility":
                passed = "project" in types
            elif name == "useful_artifact":
                passed = "artifact" in types
            else:
                passed = "person" in types
            record.update(response=response, passed=passed)
            write(root / "results.json", results)
            print(trial, name, passed, response, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Source subject types failed")


if __name__ == "__main__":
    asyncio.run(main())
