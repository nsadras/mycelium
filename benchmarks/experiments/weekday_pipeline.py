"""Native weekday encoding, reviewed correction, retrieval and rebuild checks."""

import argparse
import asyncio
from dataclasses import asdict

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import SourceSegment
from mycelium.artifact_integrity import coverage_report
from mycelium.claim_lifecycle import ClaimLifecycleService
from mycelium.correction_review import CorrectionPreview
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.operations import ConsolidationRequest, RetrievalRequest, SourceInput
from mycelium.snapshots import snapshot_store
from mycelium.telemetry import trace_operation


async def trial(root, number):
    with Mycelium(
        root / "store", config_path="mycelium.toml", memory_profile="none"
    ) as memory:
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        memory.llm.trace_path = root / "calls.jsonl"
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        texts = [
            ("2031-05-06T10:00:00-07:00", "I will deliver the sculpture by Friday."),
            ("2031-05-08T10:00:00-07:00", "I will visit the gallery next Thursday."),
            ("2031-05-11T10:00:00-07:00", "I attend a drawing class every Thursday."),
        ]
        with trace_operation("weekday_pipeline_encoding", trial=number):
            await memory.ingest_source(
                SourceInput(
                    "\n".join(text for _, text in texts),
                    "weekday-schedule",
                    occurred_at="2031-06-01",
                    participants=("Rae",),
                    segments=tuple(
                        SourceSegment("", i, text, "Rae", "user", timestamp)
                        for i, (timestamp, text) in enumerate(texts)
                    ),
                )
            )
            build = await memory.consolidate(ConsolidationRequest())
        write(root / "build.json", asdict(build))
        claims = memory.artifacts.list_claims(status="active")
        write(root / "encoded_claims.json", [asdict(c) for c in claims])
        snapshot_store(memory.store_path, root / "encoded_snapshot")
        times = [t for claim in claims for t in claim.facets["temporal"]]
        assert any(
            t["role"] == "deadline" and t["start"] == "2031-05-09" for t in times
        ), times
        assert any(
            t["role"] == "event_time" and t["start"] == "2031-05-15" for t in times
        ), times
        assert any(t["status"] == "recurring" and t["start"] is None for t in times), (
            times
        )
        targets = [
            c
            for c in claims
            if any(t["role"] == "deadline" for t in c.facets["temporal"])
        ]
        assert len(targets) == 1, targets
        target = targets[0]
        service = ClaimLifecycleService(
            memory.artifacts,
            PageMaterializer(memory.wiki, memory.artifacts, memory.config),
            FactResolver(memory.llm, memory.artifacts, memory.config),
        )
        text = "I will deliver the sculpture by Monday."
        with trace_operation("weekday_pipeline_correction", trial=number):
            preview = await service.correct_claim(target.claim_id, text)
            write(root / "preview.json", asdict(preview))
            assert isinstance(preview, CorrectionPreview), preview
            assert memory.artifacts.get_claim(target.claim_id).status == "active"
            choices = {
                t["time_id"]: next(
                    o["reference_id"]
                    for o in t["options"]
                    if o["reference_id"].startswith("T") and o["start"] == "2031-05-12"
                )
                for t in preview.times
            }
            result = await service.correct_claim(
                target.claim_id,
                text,
                draft_id=preview.draft_id,
                time_references=choices,
            )
        replacement = memory.artifacts.get_claim(result.claim_ids[0])
        write(root / "replacement.json", asdict(replacement))
        assert [(t["role"], t["start"]) for t in replacement.facets["temporal"]] == [
            ("deadline", "2031-05-12")
        ]
        assert all(t["reference_reason"] for t in replacement.facets["temporal"])
        assert memory.artifacts.get_claim(target.claim_id).status == "superseded"
        snapshot_store(memory.store_path, root / "corrected_snapshot")
        with trace_operation("weekday_pipeline_retrieval", trial=number):
            retrieved = await memory.retrieve_context(
                RetrievalRequest(
                    "When must I deliver the sculpture, and when is the gallery visit?"
                )
            )
        write(root / "retrieved.json", asdict(retrieved))
        assert (
            "2031-05-12" in retrieved.rendered_context
            and "2031-05-15" in retrieved.rendered_context
        )
        assert "2031-05-09" not in retrieved.rendered_context
        with trace_operation("weekday_pipeline_rebuild", trial=number):
            rebuilt = await memory.consolidate(ConsolidationRequest())
        write(root / "rebuild.json", asdict(rebuilt))
        snapshot_store(memory.store_path, root / "final_snapshot")
        coverage = coverage_report(memory.artifacts)
        write(root / "coverage.json", coverage)
        assert not coverage["pending_extraction_segments"]
        assert not coverage["unresolved_provenance_ids"]
        assert not memory.db.publication_status()


async def main(args):
    root = fresh_run_root("weekday-pipeline")
    print("OUTPUT", root, flush=True)
    results = []
    for number in range(args.trials):
        try:
            await trial(root / str(number), number)
            result = {"trial": number, "passed": True}
        except Exception as exc:
            result = {
                "trial": number,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        results.append(result)
        write(root / "results.json", results)
        print(result, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in results), "total": len(results)},
    )
    if not all(r["passed"] for r in results):
        raise SystemExit("Weekday pipeline acceptance failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    asyncio.run(main(parser.parse_args()))
