"""Prove explicit agent-conversation authorship without assigning other people's actions to the user."""

import argparse
import asyncio
import itertools
from dataclasses import asdict

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.telemetry import trace_operation


CASES = [
    (
        "self",
        ["I prefer written progress reports."],
        ["The user prefers written progress reports."],
        {"C001"},
        set(),
    ),
    (
        "reported_other",
        ["Morgan Vale is a cabinetmaker. Morgan will deliver the cabinet."],
        ["Morgan Vale is a cabinetmaker who will deliver the cabinet."],
        set(),
        {"C001"},
    ),
    (
        "mixed",
        [
            "Morgan Vale is a cabinetmaker who repairs my furniture.",
            "I prefer repairing furniture to replacing it.",
        ],
        [
            "Morgan Vale is a cabinetmaker who repairs the user's furniture.",
            "The user prefers repairing furniture to replacing it.",
        ],
        {"C001", "C002"},
        set(),
    ),
]


async def main(args):
    root = fresh_run_root("agent-user-role-contract")
    print("OUTPUT", root, flush=True)
    results = []
    for trial in range(args.trials):
        for profile, (
            name,
            raw,
            texts,
            require_author,
            forbid_author,
        ) in itertools.product(args.profiles, CASES):
            case = root / f"{trial}-{profile}-{name}"
            with Mycelium(
                case / "store", config_path="mycelium.toml", memory_profile=profile
            ) as memory:
                memory.llm.trace_path = case / "calls.jsonl"
                write(case / "config.json", asdict(memory.config))
                write(
                    case / "models.json", (await memory.llm.client.list()).model_dump()
                )
                memory.llm.client = RecordingClient(
                    memory.llm.client, case / "requests"
                )
                source = SourceDocument(
                    "source",
                    "agent_conversation",
                    "source",
                    "2031-05-06",
                    "2031-05-06",
                    ["Rae"],
                    [
                        SourceSegment(f"S{i:03d}", i, text, "Rae", "user")
                        for i, text in enumerate(raw, 1)
                    ]
                    + [
                        SourceSegment(
                            "assistant",
                            len(raw) + 1,
                            "I can offer suggestions.",
                            "Assistant",
                            "assistant",
                        )
                    ],
                )
                memory.artifacts.save_source(source)
                claims = [
                    MemoryClaim(
                        f"C{i:03d}",
                        text,
                        [],
                        [ClaimProvenance("source", [f"S{i:03d}"])],
                        "2031-05-06",
                    )
                    for i, text in enumerate(texts, 1)
                ]
                for claim in claims:
                    memory.artifacts.save_claim(claim)
                router = ClaimRouter(memory.llm, memory.artifacts, memory.config)
                with trace_operation("agent_user_role_probe", trial=trial, case=name):
                    result = await router.route(
                        [ClaimEvidence(c, source) for c in claims]
                    )
                selected = {r.claim_id: set(r.page_sections) for r in result.routes}
                described = {
                    r.claim_id: set(r.described_entity_ids) for r in result.routes
                }
                work_unit = memory.artifacts.list_identity_work_units()[0]
                plan = work_unit.entity_plan
                author_ids = {
                    node.get("entity_id")
                    or work_unit.allocated_entity_ids.get(f"n{index:03d}")
                    for index, node in enumerate(plan.get("subjects", []), 1)
                    if "P001" in node["supporting_evidence"]
                } - {None}
                record = {
                    "trial": trial,
                    "profile": profile,
                    "author_ids": sorted(author_ids),
                    "case": name,
                    "result": asdict(result),
                    "plan": plan,
                    "page_coverage": selected,
                    "passed": not result.failures
                    and len(author_ids) == 1
                    and (
                        (author_ids == {"you"})
                        if profile == "user"
                        else "you" not in author_ids
                    )
                    and all(
                        author_ids <= described.get(cid, set())
                        and (
                            profile != "user" or author_ids <= selected.get(cid, set())
                        )
                        for cid in require_author
                    )
                    and all(
                        not author_ids.intersection(described.get(cid, ()))
                        and described.get(cid)
                        for cid in forbid_author
                    )
                    and (
                        name == "self"
                        or bool(described.get("C001", set()) - author_ids)
                    ),
                }
                write(case / "result.json", record)
                results.append(record)
                write(root / "results.json", results)
                print(trial, profile, name, record["passed"], selected, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in results), "total": len(results)},
    )
    if not all(r["passed"] for r in results):
        raise SystemExit("Agent user role contract failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--profiles", nargs="+", choices=["user", "none"], default=["user", "none"]
    )
    asyncio.run(main(parser.parse_args()))
