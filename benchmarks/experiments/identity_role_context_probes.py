"""Verify source participant context reaches identity matching for mentioned people."""

import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from benchmarks.experiments.identity_boundary_probes import record
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.subject_identity import subject_identity_model, subject_identity_prompt


def cases():
    yield (
        "named_user",
        "Morgan the teacher",
        "The teacher who runs the pottery club",
        "Morgan the teacher",
        "I run a pottery club. Morgan the architect is a different person who designs bridges.",
        "Morgan the teacher runs a pottery club; the architect is a different person.",
        True,
        "existing",
        "you",
    )
    yield (
        "reported_other",
        "Omar",
        "A person who repairs violins",
        "Leah",
        "Omar repairs violins. I am only passing that along.",
        "Omar repairs violins.",
        True,
        "new",
        None,
    )
    yield (
        "named_other",
        "Alex Mercer",
        "The architect who is distinct from the source user",
        "Alex Chen",
        "Alex Mercer designs bridges. I am Alex Chen, a different person and a nurse.",
        "Alex Mercer designs bridges.",
        True,
        "new",
        None,
    )
    yield (
        "no_user_profile",
        "Rae",
        "The source speaker who repairs violins",
        "Rae",
        "I repair violins.",
        "Rae repairs violins.",
        False,
        "new",
        None,
    )


async def main():
    root = fresh_run_root("identity-role-context-contract")
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump(mode="json"))
    (root / "probe.py").write_text(Path(__file__).read_text())
    llm.client = RecordingClient(llm.client, root / "requests")
    print("OUTPUT", root, flush=True)
    rows = []
    for trial in range(3):
        for (
            name,
            title,
            description,
            speaker,
            raw,
            text,
            canonical_user,
            resolution,
            eid,
        ) in cases():
            registry = {"you": record("you", "You", "")} if canonical_user else {}
            subject = {
                "entity_type": "person",
                "title": title,
                "description": description,
                "alternate_names": [],
                "supporting_evidence": ["C001"],
            }
            evidence = {
                "claims": {
                    "C001": {
                        "text": text,
                        "citations": [{"source_id": "s", "segment_id": "s1"}],
                    }
                },
                "participants": {
                    "P001": {
                        "name": speaker,
                        "role": "user",
                        "source_id": "s",
                        "canonical_entity_id": "you" if canonical_user else None,
                    }
                },
                "sources": {
                    "s": {
                        "source_type": "meeting_transcript",
                        "segments": {
                            "s1": {"speaker": speaker, "role": "user", "text": raw}
                        },
                    }
                },
            }
            system, user = subject_identity_prompt(
                subject, registry, json.dumps(evidence)
            )
            schema = subject_identity_model(registry, json.dumps(evidence))
            row = {"trial": trial, "case": name, "status": "running"}
            rows.append(row)
            write(root / "results.json", rows)
            try:
                result = schema.model_validate(
                    await llm.call_structured(
                        system,
                        user,
                        schema,
                        num_predict=2048,
                        debug_label="identity-role-context-probe",
                    )
                ).model_dump()["decision"]
                row.update(
                    status="complete",
                    decision=result,
                    passed=result["resolution"] == resolution
                    and result.get("entity_id") == eid,
                )
            except Exception as exc:
                row.update(
                    status="failed", passed=False, error=f"{type(exc).__name__}: {exc}"
                )
            write(root / "results.json", rows)
            print(trial, name, row["passed"], row.get("decision"), flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in rows), "total": len(rows)},
    )


if __name__ == "__main__":
    asyncio.run(main())
