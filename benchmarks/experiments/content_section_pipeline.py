"""Exercise content routing and projection through fresh native builds."""

import asyncio
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from benchmarks.suites.daily_driver.run import _snapshot
from mycelium import Mycelium
from mycelium.artifacts import SourceSegment
from mycelium.operations import ConsolidationRequest, SourceInput
from mycelium.snapshots import snapshot_store
from mycelium.telemetry import trace_operation


async def main():
    root = fresh_run_root("content-section-pipeline")
    print("OUTPUT", root, flush=True)
    root.mkdir(parents=True, exist_ok=True)
    (root / "probe.py").write_text(Path(__file__).read_text())
    results = []
    texts = [
        "I am restoring the community garden, with a greenhouse and an irrigation upgrade. I have not chosen a name for this project.",
        "The garden restoration team has not decided which greenhouse design to use.",
        "I plan to learn bookbinding.",
    ]
    for trial in range(3):
        directory = root / str(trial)
        row = {"trial": trial, "status": "running", "passed": False}
        results.append(row)
        write(root / "results.json", results)
        with Mycelium(directory / "store", config_path="mycelium.toml") as memory:
            memory.llm.trace_path = directory / "calls.jsonl"
            write(directory / "config.json", asdict(memory.config))
            write(
                directory / "models.json",
                (await memory.llm.client.list()).model_dump(mode="json"),
            )
            memory.llm.client = RecordingClient(
                memory.llm.client, directory / "requests"
            )
            with trace_operation("content_section_pipeline", trial=trial):
                await memory.ingest_source(
                    SourceInput(
                        "\n".join(texts),
                        "garden-plans",
                        occurred_at="2031-05-06",
                        participants=("Rae",),
                        segments=tuple(
                            SourceSegment("", i, text, "Rae", "user")
                            for i, text in enumerate(texts)
                        ),
                    )
                )
                build = await memory.consolidate(ConsolidationRequest())
            write(directory / "build.json", asdict(build))
            snapshot = _snapshot(memory, "built")
            write(directory / "snapshot.json", snapshot)
            snapshot_store(memory.store_path, directory / "snapshot_store")
            placed = {
                p["claim_id"] for p in snapshot["placements"] if p["status"] == "placed"
            }
            items = [
                item
                for p in snapshot["pages"]
                for s in p["sections"]
                for item in s["items"]
                if item.get("kind") == "fact"
            ]
            rendered = {cid for item in items for cid in item["claim_ids"]}
            checks = {
                "claims_published": bool(placed) and placed <= rendered,
                "no_false_review": all(item["authoritative"] for item in items),
                "no_review_or_navigation_assignments": all(
                    s not in {"needs_review", "memory_map"}
                    for p in snapshot["placements"]
                    for s in p.get("page_sections", {}).values()
                ),
                "no_backlog": not memory.log_store.get_unconsolidated(days=None)
                and not memory.db.publication_status(),
            }
            row.update(
                status="complete",
                checks=checks,
                passed=all(checks.values()),
                counts=snapshot["counts"],
            )
        write(root / "results.json", results)
        print(trial, row, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in results), "total": len(results)},
    )
    if not all(r["passed"] for r in results):
        raise SystemExit("Content section pipeline failed")


if __name__ == "__main__":
    asyncio.run(main())
