"""Direct metadata-only correction probes with time references handled separately."""

import asyncio
import json
from pathlib import Path
from dataclasses import asdict


from mycelium.config import Config
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import ReplacementMetadata
from mycelium.prompting import render_prompt
from benchmarks.experiments.probe_support import fresh_run_root, write


async def main():
    root = fresh_run_root("correction-metadata")
    config = Config.from_toml(Path("mycelium.toml")).llm
    write(root / "config.json", asdict(config))
    llm = OllamaClient(
        url=config.url,
        model=config.model,
        temperature=config.temperature,
        timeout=config.timeout_seconds,
        context_window_tokens=config.context_window_tokens,
        top_p=config.top_p,
        top_k=config.top_k,
        reasoning_enabled=config.reasoning_enabled,
        reasoning_output_tokens=config.reasoning_output_tokens,
        reasoning_format=config.reasoning_format,
        trace_path=root / "calls.jsonl",
    )
    system = render_prompt("memory/correction.system.jinja")
    schema = ReplacementMetadata
    cases = [
        (
            "both",
            "Niko will deliver the sculpture in two days, provided payment arrives tomorrow.",
        ),
        (
            "new",
            "This is a new plan from this correction: Niko will deliver the sculpture in two days.",
        ),
        ("today", "Starting today, Niko plans to deliver the sculpture in two days."),
        ("no_time", "Niko prefers quiet rooms."),
        ("vague", "Niko hopes to deliver the sculpture in a few weeks."),
        ("absolute", "Niko will deliver the sculpture on 2031-02-14."),
    ]
    results = []
    for trial in range(3):
        for name, replacement in cases:
            payload = {
                "original_statement": "Niko will deliver the sculpture in three days, provided payment arrives tomorrow.",
                "replacement": replacement,
            }
            result = await llm.call_structured(
                system,
                json.dumps(payload),
                schema,
                num_predict=2048,
                debug_label="correction-metadata-probe",
            )
            results.append(
                dict(
                    case=name,
                    trial=trial,
                    system=system,
                    user=payload,
                    schema=schema.model_json_schema(),
                    response=result,
                )
            )
            write(root / "results.json", results)
            print(json.dumps(results[-1]), flush=True)
    print("OUTPUT", root, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
