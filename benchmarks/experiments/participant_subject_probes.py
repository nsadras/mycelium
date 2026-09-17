"""Prove required participant bindings with neutral and retained failure inputs."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from mycelium.subject_discovery import (
    subject_discovery_model,
    subject_discovery_prompt,
)
from benchmarks.experiments.subject_occurrence_probes import neutral_cases, route_case
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay-failure", type=Path, action="append", default=[])
    parser.add_argument("--pipeline", action="store_true")
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    root = fresh_run_root(
        "participant-subject-pipeline"
        if args.pipeline
        else "participant-subject-contract"
    )
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump(mode="json"))
    (root / "proposal.py").write_text(Path("mycelium/subject_discovery.py").read_text())
    (root / "probe.py").write_text(Path(__file__).read_text())
    llm.client = RecordingClient(llm.client, root / "requests")
    print("OUTPUT", root, flush=True)
    inputs = [(n, e, False) for n, e, _ in neutral_cases()]
    inputs.append(
        (
            "reporting_only_speaker",
            {
                "participants": {
                    "P001": {"name": "Leah", "role": "participant", "source_id": "s"}
                },
                "claims": {
                    "C001": {
                        "text": "Omar repairs violins.",
                        "citations": [{"source_id": "s", "segment_id": "s1"}],
                    }
                },
                "sources": {
                    "s": {
                        "source_type": "meeting_transcript",
                        "segments": {
                            "s1": {
                                "speaker": "Leah",
                                "role": "participant",
                                "text": "Omar repairs violins; I am just passing that along.",
                            }
                        },
                    }
                },
            },
            False,
        )
    )
    inputs.append(
        (
            "same_speaker_two_sources",
            {
                "participants": {
                    "P001": {"name": "Leah", "role": "participant", "source_id": "s1"},
                    "P002": {"name": "Leah", "role": "participant", "source_id": "s2"},
                },
                "claims": {
                    "C001": {
                        "text": "Leah repairs violins.",
                        "citations": [{"source_id": "s1", "segment_id": "a"}],
                    },
                    "C002": {
                        "text": "Leah also repairs cellos.",
                        "citations": [{"source_id": "s2", "segment_id": "b"}],
                    },
                },
                "sources": {
                    "s1": {
                        "source_type": "meeting_transcript",
                        "segments": {
                            "a": {
                                "speaker": "Leah",
                                "role": "participant",
                                "text": "I repair violins.",
                            }
                        },
                    },
                    "s2": {
                        "source_type": "meeting_transcript",
                        "segments": {
                            "b": {
                                "speaker": "Leah",
                                "role": "participant",
                                "text": "I am the same Leah from the earlier violin conversation. I also repair cellos.",
                            }
                        },
                    },
                },
            },
            False,
        )
    )
    for path in args.replay_failure:
        dump = json.loads(path.read_text())
        user = next(m["content"] for m in dump["messages"] if m["role"] == "user")
        raw = user.split("\n", 1)[1].split(
            "\n\nHUMAN-REVIEWED IDENTITY OCCURRENCES", 1
        )[0]
        inputs.append(
            (
                str(path),
                json.loads(raw),
                "SubjectsWithDeclaredUser" in str(dump["format"]),
            )
        )
    if args.case:
        unknown = set(args.case) - {item[0] for item in inputs}
        if unknown:
            parser.error(f"Unknown cases: {sorted(unknown)}")
        inputs = [item for item in inputs if item[0] in args.case]
    rows = []
    for trial in range(3):
        for name, evidence, canonical_user in inputs:
            roles = {p: row["role"] for p, row in evidence["participants"].items()}
            schema = subject_discovery_model(
                evidence["claims"], roles, {}, canonical_user=canonical_user
            )
            system, user = subject_discovery_prompt(
                json.dumps(evidence), "none", canonical_user=canonical_user
            )
            row = {"trial": trial, "case": name, "status": "running"}
            rows.append(row)
            write(root / "results.json", rows)
            try:
                if args.pipeline:
                    output, row["routing"] = await route_case(
                        root / f"{trial}-{name}", evidence, llm, config
                    )
                else:
                    output = schema.model_validate(
                        await llm.call_structured(
                            system,
                            user,
                            schema,
                            num_predict=8192,
                            debug_label="participant-subject-probe",
                        )
                    ).model_dump()
                row.update(status="complete", output=output)
            except Exception as exc:
                row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            write(root / "results.json", rows)
            print(trial, name, row["status"], flush=True)
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
