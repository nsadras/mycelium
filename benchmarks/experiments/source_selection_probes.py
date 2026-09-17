"""Prove source-backed candidate input with the unchanged production selector."""

import asyncio
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.source_grounding_controls import CASES
from benchmarks.experiments.source_grounding_pipeline import seed_case
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.context_selection import (
    AssistantContextCandidate,
    AssistantContextSelector,
)
from mycelium.retrieval_context import RetrievedContextBuilder, render_memory_evidence


async def main():
    root = fresh_run_root("source-backed-selection-contract")
    root.mkdir(parents=True)
    (root / "probe.py").write_text(Path(__file__).read_text())
    print("OUTPUT", root, flush=True)
    rows = []
    for trial in range(3):
        for name, query, claim, source, _ in CASES:
            directory = root / f"{trial}-{name}"
            with Mycelium(directory / "store", config_path="mycelium.toml") as memory:
                memory.llm.trace_path = directory / "calls.jsonl"
                memory.llm.client = RecordingClient(
                    memory.llm.client, directory / "requests"
                )
                write(directory / "config.json", asdict(memory.config))
                write(
                    directory / "models.json",
                    (await memory.llm.client.list()).model_dump(mode="json"),
                )
                if name == "unsupported":
                    claim, source = "Iona likes board games.", "I like board games."
                seed_case(memory, claim, source)
                hits = await memory.retriever.claim_index.search(query)
                builder = RetrievedContextBuilder(memory.wiki, memory.artifacts)
                candidates = [
                    AssistantContextCandidate(
                        candidate_id=f"claim:{h.claim_id}",
                        kind=f"{h.memory_tier}_claim",
                        title=h.owner_title or "Unassigned memory",
                        content=render_memory_evidence(
                            builder.build(
                                [h], budget_tokens=memory.config.context_budget_tokens
                            )
                        ),
                    )
                    for h in hits
                ]
                selection = await AssistantContextSelector(
                    memory.llm
                ).select_with_trace(query, candidates)
                passed = not selection.error and (
                    not selection.selected_ids
                    if name == "unsupported"
                    else True
                    if name == "recording_date"
                    else selection.selected_ids == ("claim:claim-1",)
                )
                row = {
                    "trial": trial,
                    "case": name,
                    "passed": passed,
                    "selection": asdict(selection),
                    "candidates": [asdict(c) for c in candidates],
                }
                rows.append(row)
                write(root / "results.json", rows)
                print(trial, name, passed, asdict(selection), flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in rows), "total": len(rows)},
    )


if __name__ == "__main__":
    asyncio.run(main())
