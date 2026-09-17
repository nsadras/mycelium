"""Compare initial claims, cited sources and an evidence oracle for memory QA.

The controlled retriever returns the same inspectable evidence in every arm.
This isolates answer/tool behavior, not real retrieval recall. Answers require
source audit; execution completion is not a semantic pass.
"""

import argparse
import asyncio
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.memory_tools import MemoryToolset
from mycelium.operations import (
    EvidenceCitation,
    EvidenceRecord,
    EvidenceSegment,
    EvidenceSource,
    EvidenceSourceCitation,
    MemoryEvidence,
)
from mycelium.telemetry import trace_operation


CASES = [
    (
        "date",
        "On what date did Iona attend the robotics fair?",
        "Iona attended the robotics fair.",
        "I attended the robotics fair on 2031-05-12.",
        "2031-05-12",
    ),
    (
        "place",
        "In which hall did Iona attend the robotics fair?",
        "Iona attended the robotics fair.",
        "I attended the robotics fair at South Quay Hall.",
        "South Quay Hall",
    ),
    (
        "recording_date",
        "On what date did Iona attend the robotics fair?",
        "Iona attended the robotics fair.",
        "I attended the robotics fair. I have not said which day it was.",
        "Unknown",
    ),
    (
        "condition",
        "Is delivery on June 8 guaranteed?",
        "Iona expects delivery on June 8.",
        "Delivery is planned for June 8, but only if the permit is approved first.",
        "No; delivery depends on prior permit approval.",
    ),
    (
        "different_person",
        "On what date did Iona attend the robotics fair?",
        "Iona attended the robotics fair.",
        "Rae attended the robotics fair on May 12. I attended on May 14.",
        "May 14",
    ),
    (
        "negation",
        "How does Iona get to the workshop?",
        "Iona discussed cycling to the workshop.",
        "I do not cycle to the workshop. I take the tram.",
        "By tram; not by bicycle.",
    ),
    (
        "search_gap",
        "How does Iona get to the workshop?",
        None,
        "I take the tram to the workshop.",
        "By tram.",
    ),
    ("unsupported", "What is Iona's passport number?", None, None, "Unknown"),
    (
        "sufficient_claim",
        "How does Iona get to the workshop?",
        "Iona takes the tram to the workshop.",
        "I take the tram to the workshop.",
        "By tram.",
    ),
]


def evidence(claim, source):
    record = EvidenceRecord(
        "claim-1",
        "claim",
        claim or "Iona takes the tram to the workshop.",
        None,
        None,
        claim_ids=("claim-1",),
        citations=(
            EvidenceCitation("claim-1", "source-1", ("segment-1",), "2031-05-13"),
        ),
    )
    sources = (
        ()
        if source is None
        else (
            EvidenceSource(
                "source-1",
                "2031-05-13",
                citations=(EvidenceSourceCitation("claim-1", ("segment-1",)),),
                segments=(EvidenceSegment("segment-1", "cited", "Iona", source),),
            ),
        )
    )
    initial = MemoryEvidence(records=(record,) if claim is not None else ())
    discovered = MemoryEvidence(records=(record,) if source else (), sources=())
    return initial, discovered, MemoryEvidence(sources=sources)


async def main(args):
    root = fresh_run_root("source-grounding-controls")
    print("OUTPUT", root, flush=True)
    config = Config.from_toml(Path("mycelium.toml"))
    qa = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm)
    qa.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await qa.llm.client.list()).model_dump(mode="json"))
    (root / "probe.py").write_text(Path(__file__).read_text())
    qa.llm.client = RecordingClient(qa.llm.client, root / "requests")
    results = []
    for trial in range(args.trials):
        for name, question, claim, source, reference in CASES:
            initial, discovered, cited = evidence(claim, source)
            for arm in ("claims_only", "cited_sources", "oracle_sources"):
                supplied = initial
                if arm == "cited_sources" and initial.records:
                    supplied = replace(initial, sources=cited.sources)
                if arm == "oracle_sources":
                    supplied = replace(initial, sources=cited.sources)

                async def search(query, **kwargs):
                    return SimpleNamespace(evidence=discovered)

                retriever = SimpleNamespace(
                    search_evidence=search,
                    source_evidence=lambda ids, **kwargs: cited,
                    refresh_evidence=lambda value, **kwargs: value,
                )
                tools = MemoryToolset(
                    retriever, request=question, initial_evidence=supplied
                )
                row = {
                    "trial": trial,
                    "case": name,
                    "arm": arm,
                    "status": "running",
                    "question": question,
                    "reference": reference,
                    "initial_evidence": asdict(supplied),
                    "assessment_status": "requires_source_review",
                }
                results.append(row)
                write(root / "results.json", results)
                try:
                    with trace_operation(
                        "grounding_control", trial=trial, case=name, arm=arm
                    ):
                        answer = await qa.answer_with_memory_tools(question, tools)
                    row.update(status="complete", answer=asdict(answer))
                except Exception as exc:
                    row.update(status="failed", error=f"{type(exc).__name__}: {exc}")
                write(root / "results.json", results)
                print(
                    trial,
                    name,
                    arm,
                    row["status"],
                    row.get("answer", {}).get("output"),
                    flush=True,
                )
    write(
        root / "completion.json",
        {
            "status": "complete"
            if all(r["status"] == "complete" for r in results)
            else "incomplete",
            "assessment_status": "requires_source_review",
            "answers": len(results),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    asyncio.run(main(parser.parse_args()))
