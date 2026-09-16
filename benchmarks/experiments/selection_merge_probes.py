"""Neutral direct probes of selection across independently budgeted batches."""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from mycelium.config import Config
from mycelium.context_selection import AssistantContextCandidate, AssistantContextSelector
from mycelium.ollama import OllamaClient
from mycelium import prompts
from mycelium.budget import request_tokens
from mycelium.structured_outputs import complementary_selection_model


CASES = [
    {
        "name": "complementary",
        "query": "Where is the workshop, when does it start, and what should attendees bring?",
        "batches": [
            ["The workshop takes place in Room 4.", "The instructor enjoys gardening."],
            ["The workshop starts at 10:00.", "Attendees should bring a notebook."],
        ],
        "required": [{"0-0"}, {"1-0"}, {"1-1"}],
    },
    {
        "name": "duplicate_across_batches",
        "query": "Where is the workshop, when does it start, and what is the fee?",
        "batches": [
            ["The workshop takes place in Room 4.", "The workshop fee is 15 euros."],
            ["The workshop takes place in Room 4.", "The workshop starts at 10:00."],
        ],
        "required": [{"0-0", "1-0"}, {"0-1"}, {"1-1"}],
    },
    {
        "name": "unrelated",
        "query": "How far is the nearest train station from the workshop?",
        "batches": [
            ["The workshop fee is 15 euros.", "The instructor enjoys gardening."],
            ["Attendees should bring a notebook.", "The workshop starts at 10:00."],
        ],
        "required": [],
    },
]


class RecordedCalls:
    """Keep the exact production schema, prompt, settings and response."""

    def __init__(self, llm, root):
        self.llm, self.root = llm, root
        self.context_window_tokens = llm.context_window_tokens
        self.calls = []

    async def call_structured(self, system, user, schema, **kwargs):
        record = {"system": system, "user": user, "schema": schema.model_json_schema(), "options": kwargs}
        self.calls.append(record)
        write(self.root / "requests.json", self.calls)
        try:
            response = await self.llm.call_structured(system, user, schema, **kwargs)
            record["response"] = response
            return response
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            write(self.root / "requests.json", self.calls)


async def main():
    pipeline = "--pipeline" in sys.argv
    root = fresh_run_root("selection-merge-pipeline" if pipeline else "selection-merge")
    config = Config.from_toml(Path("mycelium.toml")).llm
    write(root / "config.json", asdict(config))
    async with httpx.AsyncClient(timeout=10) as client:
        tags = await client.get(config.url.rstrip("/") + "/api/tags")
        tags.raise_for_status()
        write(root / "models.json", tags.json())
    llm = OllamaClient(
        url=config.url, model=config.model, temperature=config.temperature,
        timeout=config.timeout_seconds, context_window_tokens=config.context_window_tokens,
        top_p=config.top_p, top_k=config.top_k, reasoning_enabled=config.reasoning_enabled,
        reasoning_output_tokens=config.reasoning_output_tokens, reasoning_format=config.reasoning_format,
        trace_path=root / "calls.jsonl",
    )
    recorded = RecordedCalls(llm, root)
    selector = AssistantContextSelector(recorded)
    results = []
    for trial in range(3):
        for case in CASES:
            admitted = []
            selections = []
            batches = []
            for batch_index, contents in enumerate(case["batches"]):
                if pipeline:
                    contents = [*contents, "The instructor keeps a travel journal.",
                                "The venue opened in 1995.", "The administrator enjoys swimming."]
                candidates = [AssistantContextCandidate(f"{batch_index}-{index}", "claim", "Workshop", content)
                              for index, content in enumerate(contents)]
                batches.append(candidates)
                if not pipeline:
                    selection = await selector.select_with_trace(case["query"], candidates)
                    selections.append(asdict(selection))
                    admitted.extend(candidate for candidate in candidates if candidate.candidate_id in selection.selected_ids)
            if pipeline:
                # Constrain only the selector's planning envelope; actual model
                # requests retain the configured host model's full context size.
                # The larger complete batch fits, while their combined input does
                # not. No records are truncated and the production selector splits.
                def envelope(candidates):
                    aliases = {f"M{index:03d}": candidate for index, candidate in enumerate(candidates, 1)}
                    records = "\n".join(f"{alias}: {json.dumps({'kind': c.kind, 'title': c.title, 'content': c.content}, sort_keys=True)}"
                                        for alias, c in aliases.items())
                    system, user = prompts.assistant_context_selection_prompt(case["query"], records)
                    return request_tokens([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                          schema=complementary_selection_model(aliases).model_json_schema()) + 3072

                recorded.context_window_tokens = max(envelope(batch) for batch in batches)
                write(root / f"planning-budget-{case['name']}.json", {
                    "selector_context_window_tokens": recorded.context_window_tokens,
                    "actual_model_context_window_tokens": config.context_window_tokens,
                })
                final = await selector.select_with_trace(case["query"], [c for batch in batches for c in batch])
            else:
                final = await selector.select_with_trace(case["query"], admitted)
            selected = set(final.selected_ids)
            passed = all(len(selected & group) == 1 for group in case["required"])
            passed = passed and len(selected) == len(case["required"])
            passed = passed and not final.error and not any(row["error"] for row in selections)
            record = {"trial": trial, "case": case["name"], "batches": selections,
                      "final": asdict(final), "passed": passed}
            results.append(record)
            write(root / "results.json", results)
            print(json.dumps(record), flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Selection merge contract did not pass every trial")


if __name__ == "__main__":
    asyncio.run(main())
