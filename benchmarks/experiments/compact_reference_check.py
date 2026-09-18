"""Bounded reference-contract check; one neutral call and one native source retry."""

import asyncio
import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments import compact_contract, compact_pipeline
from benchmarks.experiments.compact_probe import BudgetClient, metrics
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.snapshots import snapshot_store
from mycelium.telemetry import trace_operation


async def main():
    root = fresh_run_root("compact-references")
    root.mkdir(parents=True)
    print("OUTPUT", root, flush=True)
    for module in (Path(__file__), Path(compact_contract.__file__), Path(compact_pipeline.__file__)):
        (root / module.name).write_text(module.read_text())
    seed = Path("benchmark_runs/compact-shared-evidence-20260917T232020Z-13fc977d/candidate/snapshot-2")
    store = root / "store"
    store.mkdir()
    with sqlite3.connect((seed.resolve() / "memory.sqlite3").as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(store / "memory.sqlite3") as target:
            source.backup(target)
    payload = {"source_type": "meeting_transcript", "occurred_at": "2034-03-02",
        "segments": [
            {"id": "source-71afe2#seg-0041", "text": "I will bring the maps if the office opens on Friday.", "speaker": "Rowan", "role": "participant"},
            {"id": "source-71afe2#seg-0042", "text": "The office opening is not confirmed; we have not booked the visit.", "speaker": "Sasha", "role": "participant"}],
        "context_segments": [], "prior_memories": [], "existing_subjects": [],
        "new_subject_ids": ["subject-31ea", "subject-6fa2", "subject-22bb"]}
    write(root / "plan.json", {"seed": str(seed), "seconds": 300, "attempts": 12,
          "neutral_input": payload, "scope": "Exact ID selection; no semantic wording changes or additional stages"})
    started = time.monotonic()
    with Mycelium(store, config_path="mycelium.toml", memory_profile="none") as memory:
        sdk = memory.llm.client
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await sdk.list()).model_dump(mode="json"))
        memory.llm.client = BudgetClient(RecordingClient(sdk, root / "requests"), 300, 12)
        status = "complete"
        try:
            async with asyncio.timeout(300):
                with trace_operation("reference_check", stage="neutral"):
                    write(root / "neutral.json", await compact_contract.retain(memory.llm, payload))
                memory.pipeline = compact_pipeline.CompactPipeline(memory)
                with trace_operation("reference_check", stage="native"):
                    result = await memory.pipeline.consolidate()
                write(root / "native.json", asdict(result))
                snapshot_store(store, root / "snapshot")
                if result.report.failures:
                    status = "build_failed"
        except (Exception, asyncio.CancelledError) as exc:
            status = "incomplete"
            write(root / "error.json", {"error": f"{type(exc).__name__}: {exc}"})
        finally:
            await sdk._client.aclose()
            write(root / "completion.json", {"status": status, "seconds": time.monotonic() - started,
                  "metrics": metrics(root), "assessment": "requires_source_review"})
            print(status, json.dumps(metrics(root)), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
