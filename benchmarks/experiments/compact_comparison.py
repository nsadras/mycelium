"""One fixed native comparison and one reserved source; no evaluator model."""

import asyncio
import hashlib
import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments import compact_contract, compact_inputs, compact_pipeline
from benchmarks.experiments.compact_inputs import INDEPENDENT, QUESTIONS, SEQUENCE
from benchmarks.experiments.compact_pipeline import CompactPipeline
from benchmarks.experiments.compact_probe import BudgetClient, metrics
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import SourceSegment
from mycelium.memory_tools import MemoryToolset
from mycelium.operations import ConsolidationRequest, RetrievalRequest, SourceInput
from mycelium.snapshots import snapshot_store
from mycelium.telemetry import trace_operation


SEED = Path("benchmark_runs/audit-sample3-0f9f7ee-20260917/snapshots/conv-41/session_5")


def copy_seed(destination):
    destination.mkdir(parents=True)
    with sqlite3.connect((SEED.resolve() / "memory.sqlite3").as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(destination / "memory.sqlite3") as target:
            source.backup(target)


def input_source(index, date, text):
    segments = []
    for line in text.strip().splitlines():
        speaker, content = line.split(":", 1)
        segments.append(SourceSegment(f"line-{len(segments)}", len(segments), content.strip(), speaker,
                                      "participant", timestamp=date))
    return SourceInput(text.strip(), f"compact-source-{index}", "meeting_transcript", date,
                       tuple(dict.fromkeys(s.speaker for s in segments)), segments=tuple(segments),
                       idempotency_key=f"compact-source-{index}")


async def arm(root, name, sequence, seconds, calls, questions):
    directory = root / name
    copy_seed(directory / "store")
    rows = []
    started = time.monotonic()
    status = "complete"
    with Mycelium(directory / "store", config_path="mycelium.toml", memory_profile="none") as memory:
        write(directory / "config.json", asdict(memory.config))
        write(directory / "models.json", (await memory.llm.client.list()).model_dump(mode="json"))
        seed_records = memory.artifacts.list_claims()
        write(directory / "seed.json", {"claims": len(seed_records), "pages": len(memory.wiki.list_all()),
              "claim_digest": hashlib.sha256(json.dumps([asdict(c) for c in seed_records], sort_keys=True).encode()).hexdigest()})
        sdk = memory.llm.client
        memory.llm.client = BudgetClient(RecordingClient(sdk, directory / "requests"), seconds, calls)
        if name != "control":
            memory.pipeline = CompactPipeline(memory)
        qa = OllamaQaClient(memory.config.llm.model, memory.config.llm.url, llm_config=memory.config.llm)
        unused_qa_sdk = qa.llm.client
        qa.llm = memory.llm
        try:
            async with asyncio.timeout(seconds):
                for index, (date, text) in enumerate(sequence):
                    with trace_operation("compact_comparison", arm=name, step=index, stage="build"):
                        source = input_source(index, date, text)
                        captured = await memory.pipeline.ingest_source(source)
                        before = time.monotonic()
                        built = await memory.pipeline.consolidate(ConsolidationRequest())
                        elapsed = time.monotonic() - before
                    rows.append({"step": index, "words": len(text.split()), "capture": asdict(captured),
                                 "build_seconds": elapsed, "result": asdict(built)})
                    write(directory / "results.json", rows)
                    snapshot_store(memory.store_path, directory / f"snapshot-{index}")
                    print(name, "STEP", index, f"{elapsed:.1f}s", len(built.report.failures), "failures", flush=True)
                answers = []
                for question in questions:
                    with trace_operation("compact_comparison", arm=name, stage="answer"):
                        retrieved = await memory.retrieve_context(RetrievalRequest(question))
                        toolset = MemoryToolset(memory.retriever, request=question, initial_evidence=retrieved.evidence)
                        answer = await qa.answer_with_memory_tools(question, toolset)
                    answers.append({"question": question, "retrieval": asdict(retrieved), "answer": asdict(answer)})
                    write(directory / "answers.json", answers)
                if any(row["result"]["report"]["failures"] for row in rows):
                    status = "complete_with_build_errors"
        except (Exception, asyncio.CancelledError) as exc:
            status = "incomplete"
            write(directory / "error.json", {"error": f"{type(exc).__name__}: {exc}"})
            print(name, "STOP", type(exc).__name__, flush=True)
        finally:
            await unused_qa_sdk._client.aclose()
            await sdk._client.aclose()
            write(directory / "completion.json", {"status": status, "steps_completed": len(rows),
                  "seconds": time.monotonic() - started, "metrics": metrics(directory), "assessment": "requires_source_review"})
            print(name, status, metrics(directory), flush=True)


async def main():
    root = fresh_run_root("compact-comparison")
    root.mkdir(parents=True)
    print("OUTPUT", root, flush=True)
    for module in (Path(__file__), Path(compact_contract.__file__), Path(compact_inputs.__file__), Path(compact_pipeline.__file__)):
        (root / module.name).write_text(module.read_text())
    production = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                  for base in (Path("mycelium"), Path("prompts")) for p in base.rglob("*")
                  if p.is_file() and p.suffix in {".py", ".jinja", ".toml"}}
    write(root / "plan.json", {"seed": str(SEED), "inputs": [asdict(input_source(i, d, t)) for i, (d, t) in enumerate(SEQUENCE)],
          "independent": asdict(input_source(0, *INDEPENDENT)), "questions": QUESTIONS, "review_actions": [],
          "per_arm_seconds": 900, "per_arm_attempts": 60, "independent_seconds": 300,
          "assessment": "Useful artifacts and total cost; no perfect coverage/identity requirement",
          "limits": "Seed contains pre-existing benchmark memory and its known quality flaws; experimental candidate lifecycle support is not adoption proof",
          "source_sha256": production})
    await arm(root, "candidate", SEQUENCE, 900, 60, QUESTIONS)
    await arm(root, "control", SEQUENCE, 900, 60, QUESTIONS)
    await arm(root, "independent", [INDEPENDENT], 300, 12,
              ["What is decided about the holiday, and what needs checking before booking?"])
    write(root / "completion.json", {"status": "finished", "assessment": "requires_source_review",
          "arms": {name: json.loads((root / name / "completion.json").read_text())
                   for name in ("candidate", "control", "independent")}})


async def finish_remaining(previous):
    """One user-directed contract revision within the original arm allowances."""
    root = fresh_run_root("compact-shared-evidence")
    root.mkdir(parents=True)
    print("OUTPUT", root, flush=True)
    for module in (Path(__file__), Path(compact_contract.__file__), Path(compact_inputs.__file__), Path(compact_pipeline.__file__)):
        (root / module.name).write_text(module.read_text())
    earlier = json.loads((previous / "completion.json").read_text())["arms"]
    allowances = {name: {"seconds": max(0, seconds - earlier[name]["seconds"]),
                         "calls": max(0, calls - earlier[name]["metrics"]["attempts"])}
                  for name, seconds, calls in [("candidate", 900, 60), ("independent", 300, 12)]}
    write(root / "plan.json", {"previous_run": str(previous), "remaining_allowances": allowances,
          "change": "User permits distinct view items to cite the same retained statement; ownership belongs to items",
          "limits": "Control exhausted 60 calls with no completed Build. Independent source already ran under the old contract; its output was not reviewed before freezing this revision. This is not a fresh holdout.",
          "questions": QUESTIONS, "review_actions": [], "seed": str(SEED)})
    for name, sequence, questions in [("candidate", SEQUENCE, QUESTIONS),
            ("independent", [INDEPENDENT], ["What is decided about the holiday, and what needs checking before booking?"])]:
        allowance = allowances[name]
        if allowance["seconds"] > 0 and allowance["calls"] > 0:
            await arm(root, name, sequence, allowance["seconds"], allowance["calls"], questions)
    write(root / "completion.json", {"status": "finished", "assessment": "requires_source_review",
          "arms": {name: json.loads((root / name / "completion.json").read_text())
                   for name in allowances if (root / name / "completion.json").exists()}})


if __name__ == "__main__":
    asyncio.run(main())
