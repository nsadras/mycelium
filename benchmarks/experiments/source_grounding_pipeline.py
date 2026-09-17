"""Real retrieval and paired QA on source-grounding controls.

Stores contain declared claims, including deliberately incomplete interpretations.
This tests retrieval/answering independently of extraction quality. Source review
is required; execution completion is not a semantic pass.
"""

import asyncio
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.source_grounding_controls import CASES
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.memory_tools import MemoryToolset
from mycelium.operations import RetrievalRequest
from mycelium.snapshots import snapshot_store
from mycelium.telemetry import trace_operation


def seed_case(memory, claim, text):
    if not text:
        return
    memory.artifacts.save_source(
        SourceDocument(
            "source-1",
            "meeting_transcript",
            "session-1",
            "2031-05-13",
            "2031-05-13",
            ["Iona"],
            [SourceSegment("segment-1", 0, text, "Iona", "participant")],
        )
    )
    memory.artifacts.save_claim(
        MemoryClaim(
            "claim-1",
            claim or "Iona takes the tram to the workshop.",
            [],
            [ClaimProvenance("source-1", ["segment-1"])],
            "2031-05-13",
        )
    )


async def main():
    root = fresh_run_root("source-grounding-pipeline")
    root.mkdir(parents=True)
    print("OUTPUT", root, flush=True)
    (root / "probe.py").write_text(Path(__file__).read_text())
    rows = []
    for trial in range(3):
        for name, question, claim, text, reference in CASES:
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
                seed_case(memory, claim, text)
                qa = OllamaQaClient(
                    memory.config.llm.model,
                    memory.config.llm.url,
                    llm_config=memory.config.llm,
                )
                qa.llm = memory.llm
                row = {
                    "case": name,
                    "trial": trial,
                    "question": question,
                    "reference": reference,
                    "status": "running",
                    "assessment_status": "requires_source_review",
                }
                rows.append(row)
                write(root / "results.json", rows)
                try:
                    started = perf_counter()
                    with trace_operation("grounding_retrieval", trial=trial, case=name):
                        retrieved = await memory.retrieve_context(
                            RetrievalRequest(question)
                        )
                    row.update(
                        retrieval_seconds=perf_counter() - started,
                        retrieval=asdict(retrieved),
                        answers={},
                    )
                    for arm in ("claims_only", "cited_sources"):
                        evidence = (
                            retrieved.evidence
                            if arm == "cited_sources"
                            else replace(retrieved.evidence, sources=())
                        )
                        toolset = MemoryToolset(
                            memory.retriever,
                            request=question,
                            initial_evidence=evidence,
                        )
                        with trace_operation(
                            "grounding_answer", trial=trial, case=name, arm=arm
                        ):
                            answer = await qa.answer_with_memory_tools(
                                question, toolset
                            )
                        row["answers"][arm] = asdict(answer)
                        write(root / "results.json", rows)
                    row["status"] = "complete"
                except Exception as exc:
                    row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                snapshot_store(memory.store_path, directory / "snapshot_store")
                write(root / "results.json", rows)
                print(
                    trial,
                    name,
                    row["status"],
                    {k: v["output"] for k, v in row.get("answers", {}).items()},
                    flush=True,
                )
    write(
        root / "completion.json",
        {
            "status": "complete"
            if all(r["status"] == "complete" for r in rows)
            else "incomplete",
            "cases": len(rows),
            "assessment_status": "requires_source_review",
        },
    )


if __name__ == "__main__":
    asyncio.run(main())
