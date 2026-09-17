"""Prove a named-weekday declaration before integrating calendar arithmetic."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path


from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.prompts import claim_extraction_prompt
from mycelium.prompting import render_prompt
from mycelium.structured_outputs import (
    ReplacementMetadata,
    extraction_output_model,
    extraction_records,
)
from mycelium.temporal_contract import TimeAnnotation, resolve_annotation
from mycelium.telemetry import trace_operation


CASES = [
    (
        "weekday_deadline",
        "2031-05-06",
        "I will deliver the sculpture by Friday.",
        {("deadline", "2031-05-09")},
    ),
    (
        "same_weekday_next_week",
        "2031-05-08",
        "I will visit the gallery next Thursday.",
        {("event_time", "2031-05-15")},
    ),
    (
        "year_boundary",
        "2030-12-30",
        "I will collect the permit this Friday.",
        {("event_time", "2031-01-03")},
    ),
    (
        "earlier_this_week",
        "2031-01-01",
        "I collected the permit on Tuesday earlier this week.",
        {("event_time", "2030-12-31")},
    ),
    (
        "sunday_to_monday",
        "2031-05-11",
        "I will collect the permit this coming Monday.",
        {("event_time", "2031-05-12")},
    ),
    (
        "explicit_calendar_week",
        "2031-05-06",
        "I will collect the permit on Friday of next calendar week.",
        {("event_time", "2031-05-16")},
    ),
    (
        "condition_and_event",
        "2031-06-06",
        "I can deliver the sculpture next Wednesday only if payment arrives next Monday.",
        {("event_time", "2031-06-11"), ("condition_time", "2031-06-09")},
    ),
    (
        "recurring_counterexample",
        "2031-05-06",
        "I attend a drawing class every Thursday.",
        set(),
    ),
    (
        "day_offset_control",
        "2031-05-06",
        "I will collect the permit tomorrow.",
        {("event_time", "2031-05-07")},
    ),
    (
        "absolute_control",
        "2031-05-06",
        "The exhibition opens on 2031-06-18.",
        {("event_time", "2031-06-18")},
    ),
    (
        "past_deadline", "2031-05-06",
        "The permit application was due last Friday.",
        {("deadline", "2031-05-02")},
    ),
    (
        "same_day_deadline", "2031-05-09",
        "I will submit the application by this Friday, today.",
        {("deadline", "2031-05-09")},
    ),
    (
        "missing_reference", None,
        "I will return the library book this coming Monday.", set(),
    ),
    (
        "undated_report", "2031-05-06",
        "I found an undated note from an old trip: 'I will return the library book next Monday.' I do not know when it was written.",
        set(),
    ),
]


async def main(args):
    root = fresh_run_root(
        "weekday-correction-contract"
        if args.correction
        else "weekday-declaration-contract"
    )
    settings = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(
        settings.llm.model, settings.llm.url, llm_config=settings.llm
    ).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(settings))
    write(root / "models.json", (await llm.client.list()).model_dump())
    llm.client = RecordingClient(llm.client, root / "requests")
    write(
        root / "experiment.json",
        {
            "concurrent_benchmark": args.concurrent_benchmark,
            "latencies_comparable": not bool(args.concurrent_benchmark),
        },
    )
    print("OUTPUT", root, flush=True)
    results = []
    for trial in range(args.trials):
        for name, anchor, text, expected in CASES:
            system, user = claim_extraction_prompt(
                "agent_conversation",
                "source",
                ["Rae"],
                "[new] speaker=Rae; role=user"
                + (f"; message_time={anchor}T10:00:00" if anchor else "")
                + f"\n{text}",
            )
            schema = extraction_output_model(["new"])
            if args.correction:
                system = render_prompt("memory/correction.system.jinja")
                user = json.dumps(
                    {
                        "original_statement": "The user has no scheduled activity yet.",
                        "replacement": text,
                    }
                )
                schema = ReplacementMetadata
            record = {
                "trial": trial,
                "case": name,
                "system": system,
                "user": user,
                "schema": schema.model_json_schema(),
                "anchor": anchor,
            }
            try:
                with trace_operation("weekday_contract_probe", trial=trial, case=name):
                    output = schema.model_validate(
                        await llm.call_structured(
                            system,
                            user,
                            schema,
                            num_predict=2048 if args.correction else 8192,
                            debug_label="weekday-declaration-probe",
                        )
                    ).model_dump()
                found = set()
                declarations = []
                claims = (
                    [output]
                    if args.correction
                    else extraction_records(output)["claims"]
                )
                for claim in claims:
                    for item in claim["facets"]["times"]:
                        meaning = item["meaning"]
                        declarations.append(meaning)
                        resolved = resolve_annotation(
                            TimeAnnotation.model_validate(item),
                            anchor,
                            item["evidence_segment_id"],
                        )
                        if resolved.start:
                            found.add((item["role"], resolved.start))
                typed = name in {
                    "day_offset_control",
                    "absolute_control",
                    "recurring_counterexample",
                } or all(
                    m["kind"] in {"weekday_in_week", "weekday_occurrence"}
                    for m in declarations
                )
                if name == "recurring_counterexample":
                    typed = bool(declarations) and all(
                        m["kind"] == "recurring" for m in declarations
                    )
                if name == "same_day_deadline":
                    typed = bool(declarations)
                if name == "missing_reference":
                    typed = bool(declarations) and all(
                        m["kind"] in {"weekday_occurrence", "weekday_in_week"}
                        for m in declarations
                    )
                if name == "undated_report":
                    typed = bool(declarations) and all(
                        m["kind"] == "unresolved" for m in declarations
                    )
                record.update(
                    output=output,
                    found=sorted(found),
                    expected=sorted(expected),
                    passed=found == expected and typed,
                )
            except Exception as exc:
                record.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            results.append(record)
            write(root / "results.json", results)
            print(
                trial,
                name,
                record["passed"],
                record.get("found", record.get("error")),
                flush=True,
            )
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in results), "total": len(results)},
    )
    if not all(r["passed"] for r in results):
        raise SystemExit("Weekday declaration contract failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--correction", action="store_true")
    parser.add_argument("--concurrent-benchmark")
    asyncio.run(main(parser.parse_args()))
