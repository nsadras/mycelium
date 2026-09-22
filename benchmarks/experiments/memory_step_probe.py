"""Probe one structured answer-or-tool step, without changing production execution."""

import asyncio
import json
from dataclasses import asdict
from typing import Literal, Union

from pydantic import ConfigDict, Field, create_model

from benchmarks.experiments.memory_tool_probes import CASES, evidence
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.memory_tool_contracts import MemorySearchArguments, MemorySourcesArguments
from mycelium.memory_tools import MemoryToolset
from mycelium.operations import (
    EvidenceSegment,
    EvidenceSource,
    EvidenceSourceCitation,
    MemoryEvidence,
)
from mycelium.prompting import render_prompt
from mycelium.evidence_rendering import render_memory_workspace
from types import SimpleNamespace


def step_model(claim_ids, has_looked_up):
    bases = ["supported_memory", "not_a_recall_request"]
    if has_looked_up:
        bases.append("insufficient_memory")
    answer = create_model(
        "Answer",
        __config__=ConfigDict(extra="forbid"),
        kind=(Literal["answer"], ...),
        basis=(Literal.__getitem__(tuple(bases)), ...),
        text=(str, Field(min_length=1, max_length=8000)),
    )
    search = create_model(
        "Search", __base__=MemorySearchArguments, kind=(Literal["memory_search"], ...)
    )
    choices = [answer, search]
    if claim_ids:
        sources = create_model(
            "Sources",
            __base__=MemorySourcesArguments,
            kind=(Literal["memory_sources"], ...),
            claim_ids=(
                list[Literal.__getitem__(tuple(sorted(claim_ids)))],
                Field(min_length=1, max_length=6),
            ),
        )
        choices.append(sources)
    return create_model(
        "MemoryStep",
        __config__=ConfigDict(extra="forbid"),
        evidence_assessment=(str, Field(min_length=1, max_length=600)),
        next_step=(Union.__getitem__(tuple(choices)), Field(discriminator="kind")),
    )


SYSTEM = """Choose one next step for the user's request using the current memory workspace.
First assess which requested details the evidence establishes and which are missing.

Choose memory_sources when an available record is relevant but its statement lacks a needed detail. Pass its exact supporting claim IDs; the tool returns the original cited lines and nearby dialogue. Citation timestamps date the source conversation. They establish an event's time only if a statement or source explicitly makes that connection.
Choose memory_search when available records do not establish the needed information. An empty initial workspace still permits search. Describe the missing information in the query.
Choose answer with supported_memory when the evidence establishes the answer, or not_a_recall_request only when the user is not asking for remembered information. Choose insufficient_memory only after using a memory lookup that does not establish an answer. Do not invent details or treat a pending review as an accepted replacement.

The newest workspace contains all accumulated refreshed evidence and replaces earlier workspaces. Use the remaining lookup budget. Return a concise answer once supported.
"""


async def main():
    root = fresh_run_root("memory-step-contract")
    print("OUTPUT", root, flush=True)
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        memory.llm.trace_path = root / "calls.jsonl"
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        results = []
        for trial in range(3):
            for name, question, initial, expected in CASES:

                async def search(query, **kwargs):
                    return SimpleNamespace(
                        evidence=evidence(
                            "Iona travels to the workshop by tram.", "claim-2"
                        )
                        if name == "search_gap"
                        else MemoryEvidence()
                    )

                def sources(ids, **kwargs):
                    return MemoryEvidence(
                        sources=(
                            EvidenceSource(
                                "source-1",
                                "2031-05-13",
                                citations=(
                                    EvidenceSourceCitation("claim-1", ("segment-1",)),
                                ),
                                segments=(
                                    EvidenceSegment(
                                        "segment-1",
                                        "cited",
                                        "Iona",
                                        "I attended the robotics fair at South Quay Hall."
                                        if name == "source_place"
                                        else "I attended the robotics fair on 2031-05-12.",
                                        0,
                                    ),
                                ),
                            ),
                        )
                    )

                toolset = MemoryToolset(
                    SimpleNamespace(
                        search_evidence=search,
                        source_evidence=sources,
                        refresh_evidence=lambda value, **kwargs: value,
                    ),
                    request=question,
                    initial_evidence=initial,
                )
                steps = []
                for attempt in range(4):
                    schema = step_model(toolset.returned_claim_ids, bool(steps))
                    user = render_prompt(
                        "assistant/memory_request.user.jinja",
                        memory_evidence=render_memory_workspace(
                            toolset.workspace.snapshot, include_request=False
                        ),
                        user_request=question,
                    )
                    response = schema.model_validate(
                        await memory.llm.call_structured(
                            SYSTEM,
                            user,
                            schema,
                            num_predict=2048,
                            debug_label="memory-step-probe",
                        )
                    ).model_dump()
                    steps.append(response)
                    action = dict(response["next_step"])
                    kind = action.pop("kind")
                    if kind == "answer":
                        break
                    await toolset.run(kind, action)
                selected = steps[0]["next_step"]["kind"]
                answer = steps[-1]["next_step"]
                passed = (
                    selected == (expected or "answer") and answer["kind"] == "answer"
                )
                if name == "source_detail":
                    passed = (
                        passed
                        and "12" in answer.get("text", "")
                        and "13" not in answer.get("text", "")
                    )
                if name == "source_place":
                    passed = passed and "South Quay Hall" in answer.get("text", "")
                if name == "unsupported":
                    passed = passed and answer.get("basis") == "insufficient_memory"
                record = {
                    "trial": trial,
                    "case": name,
                    "steps": steps,
                    "passed": passed,
                }
                results.append(record)
                write(root / "results.json", results)
                print(trial, name, passed, json.dumps(steps), flush=True)
        if not all(row["passed"] for row in results):
            raise SystemExit("Structured memory step failed")


if __name__ == "__main__":
    asyncio.run(main())
