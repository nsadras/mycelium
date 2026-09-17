"""Configured-model calendar controls, with an optional native Build check."""

import argparse
import asyncio
import json
import sqlite3
from dataclasses import asdict

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import SourceSegment
from mycelium.encoder import Encoder
from mycelium.prompts import claim_extraction_prompt
from mycelium.structured_outputs import extraction_output_model, extraction_records
from mycelium.temporal_contract import TimeAnnotation, resolve_annotation


def cases(args):
    for name, anchor, raw, expected in [
        (
            "scheduled_clock_times",
            "2031-05-06",
            "The studio visit is scheduled for May 10, 2031, from 15:00 to 16:30.",
            {"2031-05-10"},
        ),
        (
            "calendar_range",
            "2031-04-01",
            "The exhibition runs April 10 through April 12, 2031.",
            {"2031-04-10"},
        ),
        (
            "relative_with_clock",
            "2031-05-06",
            "We will meet tomorrow at 10 a.m.",
            {"2031-05-07"},
        ),
        (
            "explicit_transition",
            "2031-05-06",
            "Kai cannot book the room by May 22, so the first rehearsal moves to May 28.",
            {"2031-05-22", "2031-05-28"},
        ),
        (
            "undated_clock",
            None,
            "The appointment is at 3 p.m.; no calendar date has been specified.",
            {None},
        ),
    ]:
        yield (
            name,
            "agent_conversation",
            name,
            anchor,
            [SourceSegment("S1", 0, raw, "Rae", "user")],
            expected,
        )
    for store, source_id, dates in args.saved:
        with sqlite3.connect(f"file:{store}/memory.sqlite3?mode=ro", uri=True) as db:
            source = json.loads(
                db.execute(
                    "SELECT payload FROM records WHERE kind='sources' AND id=?",
                    (source_id,),
                ).fetchone()[0]
            )
        yield (
            source_id,
            source["source_type"],
            source["source_id"],
            source["occurred_at"],
            [SourceSegment(**r) for r in source["segments"]],
            set(dates.split(",")),
        )


async def run(args):
    root = fresh_run_root("calendar-date-contract")
    print("OUTPUT", root, flush=True)
    results = []
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        memory.llm.trace_path = root / "calls.jsonl"
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        for name, kind, sid, anchor, segments, expected in cases(args):
            anchors = {s.segment_id: s.timestamp or anchor for s in segments}
            system, user = claim_extraction_prompt(
                kind,
                sid,
                sorted({s.speaker for s in segments}),
                Encoder._render_claim_segments(segments, anchors),
            )
            for arm in ("production",):
                schema = extraction_output_model([s.segment_id for s in segments])
                row = dict(
                    case=name,
                    arm=arm,
                    status="running",
                    expected=sorted(expected, key=str),
                )
                results.append(row)
                write(root / "results.json", results)
                try:
                    response = schema.model_validate(
                        await memory.llm.call_structured(
                            system,
                            user,
                            schema,
                            num_predict=8192,
                            debug_label="calendar-date-contract",
                        )
                    ).model_dump()
                    actual = set()
                    for claim in extraction_records(response)["claims"]:
                        for value in claim["facets"]["times"]:
                            annotation = TimeAnnotation.model_validate(value)
                            resolved = resolve_annotation(
                                annotation,
                                anchors[annotation.evidence_segment_id],
                                annotation.evidence_segment_id,
                            )
                            actual.add(resolved.start)
                    row.update(
                        status="complete",
                        output=response,
                        actual=sorted(actual, key=str),
                        passed=actual == expected,
                    )
                except Exception as exc:
                    row.update(
                        status="failed",
                        passed=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                write(root / "results.json", results)
                print(
                    name,
                    arm,
                    row["passed"],
                    row.get("actual", row.get("error", "")[:500]),
                    flush=True,
                )

        if args.pipeline:
            from mycelium.operations import SourceInput, RetrievalRequest
            from mycelium.snapshots import snapshot_store

            text = "The studio visit is scheduled for May 10, 2031, from 15:00 to 16:30. The exhibition runs May 12 through May 14, 2031."
            await memory.ingest_source(
                SourceInput(
                    transcript=text,
                    session_id="calendar-clock-controls",
                    participants=("Rae",),
                    occurred_at="2031-05-06T10:00:00-07:00",
                    segments=(SourceSegment("", 0, text, "Rae", "user"),),
                )
            )
            result = await memory.consolidate()
            write(root / "build.json", asdict(result))
            snapshot_store(memory.store_path, root / "final-store")
            claims = memory.artifacts.list_claims(status="active")
            times = [t for c in claims for t in c.facets.get("temporal", [])]
            expected = {("2031-05-10", "2031-05-10"), ("2031-05-12", "2031-05-14")}
            actual = {(t["start"], t["end"]) for t in times}
            assert not result.report.failures, result.report.failures
            assert actual == expected, times
            retrieved = await memory.retrieve_context(
                RetrievalRequest("When are the studio visit and the exhibition?")
            )
            write(root / "retrieval.json", asdict(retrieved))
            assert all(
                value in retrieved.rendered_context
                for pair in expected
                for value in pair
            )
            write(
                root / "pipeline-result.json",
                {
                    "status": "complete",
                    "expected": sorted(expected),
                    "actual": sorted(actual),
                },
            )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--saved", action="append", nargs=3, default=[])
    p.add_argument("--pipeline", action="store_true")
    asyncio.run(run(p.parse_args()))
