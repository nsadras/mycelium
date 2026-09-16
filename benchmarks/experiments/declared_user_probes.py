"""Direct contract proof separating the declared user from other discovered subjects."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path


from benchmarks.experiments.agent_user_role_probes import CASES
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt


async def main(args):
    root = fresh_run_root("declared-user-contract")
    print("OUTPUT", root, flush=True)
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump())
    llm.client = RecordingClient(llm.client, root / "requests")
    results = []
    for trial in range(args.trials):
        for name, raw, texts, required, forbidden in CASES:
            aliases = {
                f"C{i:03d}": {
                    "text": text,
                    "citations": [{"source_id": "source", "segment_id": f"S{i:03d}"}],
                }
                for i, text in enumerate(texts, 1)
            }
            evidence = {
                "claims": aliases,
                "participants": {
                    "P001": {"name": "Rae", "role": "user", "source_id": "source"}
                },
                "sources": {
                    "source": {
                        "source_type": "agent_conversation",
                        "segments": {
                            f"S{i:03d}": {
                                "speaker": "Rae",
                                "role": "user",
                                "text": text,
                            }
                            for i, text in enumerate(raw, 1)
                        },
                    }
                },
            }
            system, user = subject_discovery_prompt(
                json.dumps(evidence), "none", canonical_user=True
            )
            schema = subject_discovery_model(
                aliases, {"P001": "user"}, {}, canonical_user=True
            )
            response = schema.model_validate(
                await llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=8192,
                    debug_label="declared-user-probe",
                )
            ).model_dump()
            support = set(response["declared_user"]["supporting_claims"])
            other_support = {
                alias
                for subject in response["subjects"]
                for alias in subject["supporting_evidence"]
            }
            record = {
                "trial": trial,
                "case": name,
                "response": response,
                "passed": required <= support
                and not forbidden.intersection(support)
                and forbidden <= other_support,
            }
            results.append(record)
            write(root / "results.json", results)
            print(trial, name, record["passed"], response, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in results), "total": len(results)},
    )
    if not all(r["passed"] for r in results):
        raise SystemExit("Declared user contract failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    asyncio.run(main(parser.parse_args()))
