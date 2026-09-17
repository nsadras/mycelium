"""Current extraction date checks in mixed sources, optionally including a saved regression.

Expected dates remain evaluation data outside production prompts and schemas.
"""
import argparse
import asyncio
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import SourceSegment
from mycelium.encoder import Encoder
from mycelium.prompts import claim_extraction_prompt
from mycelium.structured_outputs import extraction_output_model, extraction_records
from mycelium.temporal_contract import TimeAnnotation, resolve_annotation


NEUTRAL = [
    ("future_deadline_in_discussion", "2031-05-06", [
        ("Rae", "The exhibition will combine wooden panels and a steel frame."),
        ("Amina", "I will assemble the steel frame and check the welds."),
        ("Zuri", "I will prepare the gallery labels and invitations."),
        ("Rae", "The rehearsal should check lighting and access for wheelchair users."),
        ("Amina", "We can have the assembled frame by Friday."),
        ("Rae", "Let us schedule the public opening for May 23."),
    ], {4: {("deadline", "2031-05-09")}}),
    ("past_and_future_deadlines", "2031-04-02", [
        ("Rae", "The library is reorganizing its reading room."),
        ("Amina", "The shelf delivery was due on Monday two days ago."),
        ("Zuri", "The supplier says the replacement shelves will arrive by Friday."),
        ("Rae", "The existing tables will remain in use while we wait."),
    ], {1: {("deadline", "2031-03-31")}, 2: {("deadline", "2031-04-04")}}),
    ("condition_and_deadline", "2031-06-06", [
        ("Rae", "The class needs a working kiln for its demonstrations."),
        ("Amina", "I can finish repairs by next Thursday if the parts arrive next Monday."),
        ("Zuri", "I will check the safety instructions with the technician."),
    ], {1: {("deadline", "2031-06-12"), ("condition_time", "2031-06-09")}}),
]


def cases(args):
    output = []
    for name, anchor, lines, expected in NEUTRAL:
        segments = [SourceSegment(f"S{i+1}", i, text, speaker, "participant")
                    for i, (speaker, text) in enumerate(lines)]
        output.append((name, "multi_party_conversation", "neutral", anchor, segments,
                       {segments[index].segment_id: value for index, value in expected.items()}))
    if args.saved_store:
        with sqlite3.connect(f"file:{args.saved_store / 'memory.sqlite3'}?mode=ro", uri=True) as db:
            source = json.loads(db.execute(
                "SELECT payload FROM records WHERE kind='sources' AND id=?", (args.source_id,),
            ).fetchone()[0])
        segments = [SourceSegment(**row) for row in source["segments"]]
        output.append(("saved_source_regression", source["source_type"], source["source_id"],
                       source["occurred_at"], segments,
                       {args.segment_id: {("deadline", args.expected_date)}}))
    return output


async def main(args):
    root = fresh_run_root("calendar-context-contract")
    print("OUTPUT", root, flush=True)
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        memory.llm.trace_path = root / "calls.jsonl"
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        results = []
        for trial in range(args.trials):
            for name, source_type, source_id, anchor, segments, expected in cases(args):
                anchors = {s.segment_id: s.timestamp or anchor for s in segments}
                system, user = claim_extraction_prompt(
                    source_type, source_id, sorted({s.speaker for s in segments}),
                    Encoder._render_claim_segments(segments, anchors),
                )
                schema = extraction_output_model([s.segment_id for s in segments])
                row = dict(case=name, trial=trial, expected={k: sorted(v) for k,v in expected.items()})
                results.append(row)
                write(root / "results.json", results)
                try:
                    response = schema.model_validate(await memory.llm.call_structured(
                        system, user, schema, num_predict=8192, debug_label="calendar-context-production",
                    )).model_dump()
                    found = {sid: set() for sid in expected}
                    for claim in extraction_records(response)["claims"]:
                        for value in claim["facets"]["times"]:
                            sid = value["evidence_segment_id"]
                            if sid not in expected:
                                continue
                            time = resolve_annotation(TimeAnnotation.model_validate(value), anchors[sid], sid)
                            found[sid].add((time.role, time.start))
                    row.update(output=response, found={k: sorted(v) for k,v in found.items()}, passed=found == expected)
                except Exception as exc:
                    row.update(passed=False, error=f"{type(exc).__name__}: {exc}")
                write(root / "results.json", results)
                print(trial, name, row["passed"], row.get("found", row.get("error")), flush=True)
        write(root / "summary.json", {"passed": sum(r["passed"] for r in results), "total": len(results)})
        if not all(r["passed"] for r in results):
            raise SystemExit("Calendar context checks failed")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--saved-store", type=Path)
    parser.add_argument("--source-id")
    parser.add_argument("--segment-id")
    parser.add_argument("--expected-date")
    args = parser.parse_args()
    if args.saved_store and not all((args.source_id, args.segment_id, args.expected_date)):
        parser.error("saved-store requires source-id, segment-id and expected-date")
    asyncio.run(main(args))
