"""Direct native tool-schema proof using production assistant prompts and workspaces."""

import argparse
import asyncio
import copy
import os
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from benchmarks.experiments.probe_support import RecordingClient, fresh_run_root, write
from mycelium import Mycelium
from mycelium.memory_tool_contracts import MEMORY_TOOL_ARGUMENTS
from mycelium.memory_tools import MEMORY_TOOL_DEFINITIONS, MemoryToolset
from mycelium.operations import (
    EvidenceCitation,
    EvidenceRecord,
    EvidenceSegment,
    EvidenceSource,
    EvidenceSourceCitation,
    MemoryEvidence,
)
from mycelium.prompting import render_prompt
from mycelium.retrieval_context import render_memory_workspace


def evidence(text, cid):
    return MemoryEvidence(
        records=(
            EvidenceRecord(
                cid,
                "claim",
                text,
                None,
                None,
                claim_ids=(cid,),
                citations=(
                    EvidenceCitation(cid, "source-1", ("segment-1",), "2031-05-13"),
                ),
            ),
        )
    )


CASES = [
    (
        "source_detail",
        "On what day did Iona attend the robotics fair?",
        evidence("Iona attended the robotics fair.", "claim-1"),
        "memory_sources",
    ),
    (
        "search_gap",
        "How does Iona travel to the workshop?",
        MemoryEvidence(),
        "memory_search",
    ),
    (
        "source_place",
        "In which hall did Iona attend the robotics fair?",
        evidence("Iona attended the robotics fair.", "claim-1"),
        "memory_sources",
    ),
    (
        "unsupported",
        "What is Iona's passport number?",
        MemoryEvidence(),
        "memory_search",
    ),
    (
        "already_supported",
        "How does Iona travel to the workshop?",
        evidence("Iona travels to the workshop by tram.", "claim-2"),
        None,
    ),
]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", choices=["current", "strict"], default="strict")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--explicit-actions", action="store_true")
    args = parser.parse_args()
    root = fresh_run_root("memory-tool-contracts")
    print("OUTPUT", root, flush=True)
    os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "requests")
    memory = Mycelium(root / "store", config_path="mycelium.toml")
    memory.llm.trace_path = root / "calls.jsonl"
    memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
    write(root / "config.json", asdict(memory.config))
    write(root / "models.json", (await memory.llm.client.list()).model_dump())
    definitions = copy.deepcopy(MEMORY_TOOL_DEFINITIONS)
    if args.schema == "strict":
        for tool in definitions:
            fn = tool["function"]
            fn["parameters"] = MEMORY_TOOL_ARGUMENTS[fn["name"]].model_json_schema()
    write(root / "tool-definitions.json", definitions)
    results = []
    for trial in range(args.trials):
        for name, question, initial, expected in CASES:
            if args.explicit_actions and expected:
                question = (
                    f"Call memory_sources with claim_ids containing claim-1 to answer: {question}"
                    if expected == "memory_sources"
                    else f"Use memory_search to look up: {question}"
                )

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

            retriever = SimpleNamespace(
                search_evidence=search,
                source_evidence=sources,
                refresh_evidence=lambda value, **kwargs: value,
            )
            toolset = MemoryToolset(
                retriever, request=question, initial_evidence=initial
            )
            calls = []

            async def run(tool_name, arguments):
                record = {"name": tool_name, "arguments": arguments}
                calls.append(record)
                try:
                    parsed = MEMORY_TOOL_ARGUMENTS[tool_name].model_validate(arguments)
                    if (
                        tool_name == "memory_sources"
                        and not set(parsed.claim_ids) <= toolset.returned_claim_ids
                    ):
                        raise ValueError("Source inspection requires shown claim IDs")
                    record["valid"] = True
                except Exception as exc:
                    record["valid"] = False
                    record["error"] = str(exc)
                    raise
                return await toolset.run(tool_name, parsed.model_dump())

            system = render_prompt(
                "assistant/memory_agent.system.jinja",
                response_instructions=render_prompt(
                    "benchmarks/concise_answer.instructions.jinja"
                ),
            )
            if args.prompt_file:
                from jinja2 import Environment, StrictUndefined

                system = (
                    Environment(undefined=StrictUndefined)
                    .from_string(args.prompt_file.read_text())
                    .render(
                        response_instructions=render_prompt(
                            "benchmarks/concise_answer.instructions.jinja"
                        )
                    )
                )
            user = render_prompt(
                "assistant/memory_request.user.jinja",
                memory_evidence=render_memory_workspace(
                    toolset.workspace.snapshot, include_request=False
                ),
                user_request=question,
            )
            response = await memory.llm.call_messages(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tool_rounds=toolset.search_limit,
                num_ctx=memory.llm.context_window_tokens,
                think=True,
                tool_definitions=definitions,
                tool_runner=run,
                replaceable_context_message_index=1,
                replacement_context_content=render_prompt(
                    "assistant/current_request.user.jinja", user_request=question
                ),
            )
            record = {
                "case": name,
                "trial": trial,
                "calls": calls,
                "response": asdict(response),
                "passed": (
                    not calls
                    if expected is None
                    else bool(calls)
                    and calls[0]["name"] == expected
                    and all(c["valid"] for c in calls)
                ),
            }
            results.append(record)
            write(root / "results.json", results)
            print(trial, name, record["passed"], response.content, flush=True)
    memory.close()
    if not all(r["passed"] for r in results):
        raise SystemExit("Native tool contract probe failed")


if __name__ == "__main__":
    asyncio.run(main())
