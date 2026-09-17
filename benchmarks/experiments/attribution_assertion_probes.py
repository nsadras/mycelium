"""Direct attribution checks, including a retained named-user counterexample."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from benchmarks.experiments.attribution_contract_probes import cases
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.source_attribution import (
    source_attribution_model,
    source_attribution_prompt,
)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--named-self-request",
        type=Path,
        help="Retained two-claim teacher/architect attribution request",
    )
    args = parser.parse_args()
    inputs = []
    for name, subjects, raw, statement, _, _, described, _, _ in cases():
        evidence = {
            "claims": {
                "C001": {
                    "text": statement,
                    "citations": [{"source_id": "s", "segment_id": "s1"}],
                }
            },
            "participants": {"P001": {"name": "Rae", "role": "user", "source_id": "s"}},
            "sources": {
                "s": {
                    "source_type": "agent_conversation",
                    "segments": {"s1": {"text": raw, "speaker": "Rae", "role": "user"}},
                }
            },
        }
        inputs.append((name, subjects, evidence, {"C001": described}))
    if args.named_self_request:
        raw = json.loads(args.named_self_request.read_text())["request"]["messages"][1][
            "content"
        ].split("\n\nOUTPUT CONTRACT", 1)[0]
        evidence = json.loads(raw)
        subjects = evidence.pop("resolved_subjects")
        if set(evidence["claims"]) != {"C001", "C002"} or {
            s["entity_id"] for s in subjects
        } != {"you", "person-morgan-the-architect"}:
            parser.error(
                "This retained-case check requires the named-user teacher/architect request"
            )
        inputs.append(
            (
                str(args.named_self_request),
                subjects,
                evidence,
                {
                    "C001": {"you", "person-morgan-the-architect"},
                    "C002": {"person-morgan-the-architect"},
                },
            )
        )
    root = fresh_run_root("asserted-attribution-contract")
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
        for name, subjects, evidence, expected in inputs:
            schema = source_attribution_model(
                evidence["claims"],
                [s["entity_id"] for s in subjects],
                {s["entity_id"] for s in subjects if s["participant_bindings"]},
            )
            system, user = source_attribution_prompt(subjects, evidence)
            row = {"trial": trial, "case": name, "status": "running", "passed": False}
            rows.append(row)
            write(root / "results.json", rows)
            try:
                output = schema.model_validate(
                    await llm.call_structured(
                        system,
                        user,
                        schema,
                        num_predict=8192,
                        debug_label="asserted-attribution-probe",
                    )
                ).model_dump()["attributions"]
                described = {
                    cid: {
                        eid
                        for eid, d in choices.items()
                        if d["relation_to_claim"] == "described"
                    }
                    for cid, choices in output.items()
                }
                row.update(
                    status="complete", output=output, passed=described == expected
                )
            except Exception as exc:
                row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            write(root / "results.json", rows)
            print(trial, name, row["passed"], flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in rows), "total": len(rows)},
    )
    if not all(r["passed"] for r in rows):
        raise SystemExit("Attribution acceptance did not pass")


if __name__ == "__main__":
    asyncio.run(main())
