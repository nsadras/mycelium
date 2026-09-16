"""Opt-in neutral probes of the production extraction/time contract."""

import asyncio
import argparse
import json
from pathlib import Path
from dataclasses import asdict

from mycelium.config import Config
from mycelium.ollama import OllamaClient
from mycelium.prompts import claim_extraction_prompt
from mycelium.structured_outputs import extraction_output_model
from mycelium.temporal_contract import temporal_details_model
from benchmarks.experiments.probe_support import fresh_run_root, write

CASES = [
    (
        "two_dates",
        "Niko",
        "I will deliver the sculpture in three days. The payment must arrive tomorrow for that to happen.",
    ),
    (
        "deadline_and_event",
        "Sam",
        "The exhibition opens on 2031-02-14. My application must be submitted by 2031-01-20.",
    ),
    (
        "vague",
        "Rae",
        "I hope to visit the museum in a few weeks. The curator spoke to me recently.",
    ),
    ("period", "Dara", "I moved to Lima last month."),
    ("missing_year", "Alex", "The course starts February 14."),
    ("no_time", "Eden", "I prefer quiet rooms."),
]


async def main():
    c = Config.from_toml(Path("mycelium.toml")).llm
    root = fresh_run_root("temporal-contract")
    root.mkdir(parents=True)
    write(root / "config.json", asdict(c))
    client = OllamaClient(
        url=c.url,
        model=c.model,
        temperature=c.temperature,
        timeout=c.timeout_seconds,
        context_window_tokens=c.context_window_tokens,
        top_p=c.top_p,
        top_k=c.top_k,
        reasoning_enabled=c.reasoning_enabled,
        reasoning_output_tokens=c.reasoning_output_tokens,
        reasoning_format=c.reasoning_format,
        trace_path=root / "calls.jsonl",
    )
    results = []
    for trial in range(3):
        for name, speaker, text in CASES:
            system, user = claim_extraction_prompt(
                "agent_conversation",
                "source",
                [speaker],
                f"[new] speaker={speaker}; role=user"
                + ("; message_time=2026-06-10T10:00:00")
                + f"\n{text}",
            )
            schema = extraction_output_model(["new"])
            response = await client.call_structured(
                system, user, schema, num_predict=8192, debug_label="time-contract"
            )
            for value in response["segments"].values():
                for claim in (value or {}).get("claims", []):
                    temporal_details_model(["new"]).model_validate(claim["facets"])
            results.append(
                dict(
                    trial=trial,
                    case=name,
                    system=system,
                    user=user,
                    schema=schema.model_json_schema(),
                    response=response,
                )
            )
            write(root / "results.json", results)
            print(json.dumps(results[-1]["response"]), flush=True)
    print("OUTPUT", root, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    asyncio.run(main())
