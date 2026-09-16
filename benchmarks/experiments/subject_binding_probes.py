"""Source discovery preserves reviewed occurrences and declared participants."""

import asyncio
import json
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.identity_review_cases import CASES
from benchmarks.shared.adapters import OllamaQaClient
from mycelium.config import Config
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt


async def main():
    root = fresh_run_root("source-subject-bindings")
    config = Config.from_toml(Path("mycelium.toml")).llm
    qa = OllamaQaClient(config.model, config.url, llm_config=config)
    qa.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", vars(config))
    write(root / "models.json", (await qa.llm.client.list()).model_dump())
    results = []
    cases = [
        *CASES,
        (
            "declared_user",
            "Lena said: I will coordinate Orchard with Rin Patel.",
            {"you": ("you", "You"), "person-rin": ("person", "Rin Patel")},
            [("person-rin", "Rin Patel")],
            {"you", "person-rin"},
            {"project"},
        ),
    ]
    for trial in range(3):
        for name, text, registry, reviews, _, _ in cases:
            bindings = {
                f"R{i:03d}": {
                    "entity_id": eid,
                    "entity_type": registry[eid][0],
                    "title": registry[eid][1],
                    "surface": surface,
                    "claim_alias": "C001",
                }
                for i, (eid, surface) in enumerate(reviews, 1)
            }
            participants = (
                {"P001": {"name": "Lena", "role": "user", "source_id": "S"}}
                if name == "declared_user"
                else {}
            )
            schema = subject_discovery_model(
                ["C001"],
                {p: value["role"] for p, value in participants.items()},
                {r: value["entity_type"] for r, value in bindings.items()},
            )
            evidence = json.dumps(
                {
                    "claims": {
                        "C001": {
                            "text": text,
                            "citations": [{"source_id": "S", "segment_id": "S1"}],
                        }
                    },
                    "sources": {
                        "S": {
                            "segments": {
                                "S1": {
                                    "text": text,
                                    "speaker": "Lena" if participants else None,
                                }
                            }
                        }
                    },
                    "participants": participants,
                }
            )
            system, user = subject_discovery_prompt(evidence, json.dumps(bindings))
            record = {
                "case": name,
                "trial": trial,
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
                    debug_label="source-subject-bindings-probe",
                )
            ).model_dump()
            # Exact occurrence IDs must stay separate when they bind different canonical identities.
            passed = all(
                len(
                    {
                        bindings[a]["entity_id"]
                        for a in s["supporting_evidence"]
                        if a in bindings
                    }
                    | ({"you"} if "P001" in s["supporting_evidence"] else set())
                )
                <= 1
                for s in response["subjects"]
            )
            required_count = 3 if name == "declared_user" else 2
            record.update(
                response=response,
                passed=passed and len(response["subjects"]) >= required_count,
            )
            write(root / "results.json", results)
            print(trial, name, record["passed"], response, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Subject binding contract failed")


if __name__ == "__main__":
    asyncio.run(main())
