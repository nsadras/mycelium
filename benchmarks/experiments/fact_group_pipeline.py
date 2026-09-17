"""Native successive consolidation builds with bounded evidence and prose reuse."""

import argparse
import asyncio
import os
import time
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.fact_group_probes import CASES, INVENTORY
from benchmarks.experiments.probe_support import fresh_run_root, write
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimPlacement,
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-render-reuse", type=Path)
    args = parser.parse_args()
    if args.verify_render_reuse:
        await verify_render_reuse(args.verify_render_reuse)
        return
    root = fresh_run_root("bounded-fact-pipeline")
    print("OUTPUT", root, flush=True)
    os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "requests")
    results = []
    for trial in range(3):
        for name, texts, scopes in CASES:
            case_root = root / f"{trial}-{name}"
            memory = Mycelium(case_root / "store", config_path="mycelium.toml")
            memory.llm.trace_path = root / "calls.jsonl"
            write(root / "config.json", asdict(memory.config))
            write(root / "models.json", (await memory.llm.client.list()).model_dump())
            artifacts = memory.artifacts
            # Keep a final addition for a changed-input build; third build is a restart.
            stages = [texts[:-1], texts[-1:]]
            snapshots, new_calls, failures = [], [], []
            started = time.monotonic()
            for build in range(3):
                if build == 2:
                    memory.close()
                    memory = Mycelium(case_root / "store", config_path="mycelium.toml")
                    memory.llm.trace_path = root / "calls.jsonl"
                    artifacts = memory.artifacts
                incoming = set()
                for text in stages[build] if build < 2 else []:
                    index = len(artifacts.list_claims())
                    cid, sid = f"claim-{index:03d}", f"source-{index:03d}"
                    segment = f"{sid}#1"
                    artifacts.save_source(
                        SourceDocument(
                            sid,
                            "agent_conversation",
                            sid,
                            "2031-05-01",
                            None,
                            ["user"],
                            [SourceSegment(segment, 0, text, "user", "user")],
                        )
                    )
                    artifacts.save_claim(
                        MemoryClaim(
                            cid,
                            text,
                            [],
                            [ClaimProvenance(sid, [segment])],
                            f"2031-05-{build + 1:02d}",
                            claim_type="unknown",
                            temporal_status="unknown",
                        )
                    )
                    artifacts.save_placement(
                        ClaimPlacement(
                            cid,
                            "you",
                            "current_context",
                            [],
                            "placed",
                            "Declared neutral consolidation probe ownership.",
                            "2031-05-01",
                            "2031-05-01",
                            page_sections={"you": "current_context"},
                        )
                    )
                    incoming.add(cid)
                resolver = FactResolver(memory.llm, artifacts, memory.config)
                before = len(memory.llm._call_log)
                result = await resolver.resolve(
                    artifacts.list_placements(),
                    affected_entity_ids={"you"},
                    incoming_claim_ids=incoming,
                    dream_run_id=f"build-{build}",
                )
                for fid in result.deleted_fact_ids:
                    artifacts.delete_consolidated_fact(fid)
                for f in result.facts:
                    artifacts.save_consolidated_fact(f)
                for p in result.placements:
                    artifacts.save_placement(p)
                for p in result.proposals:
                    artifacts.save_reconsolidation_proposal(p)
                PageMaterializer(memory.wiki, artifacts, memory.config).regenerate(
                    {"you"}
                )
                failures.extend(asdict(f) for f in result.failures)
                rows = list(memory.llm._call_log)[before:]
                new_calls.append(
                    [r for r in rows if not r["metadata"].get("cache_hit")]
                )
                snapshots.append(
                    {
                        "build": build,
                        "result": asdict(result),
                        "coverage": artifacts.coverage_report(),
                        "facts": [
                            asdict(f) for f in artifacts.list_consolidated_facts()
                        ],
                        "calls": rows,
                    }
                )
                write(case_root / f"build-{build}.json", snapshots[-1])
            facts = artifacts.list_consolidated_facts()
            represented = [cid for f in facts for cid in f.member_claim_ids]
            passed = not failures and set(represented) == {
                c.claim_id for c in artifacts.list_claims()
            }
            passed = (
                passed
                and len(represented) == len(set(represented))
                and all(len(f.member_claim_ids) <= 12 for f in facts)
            )
            passed = passed and not new_calls[2]
            if scopes is not None:
                passed = passed and all(
                    any(
                        {int(cid.split("-")[1]) for cid in f.member_claim_ids} <= scope
                        for scope in scopes
                    )
                    for f in facts
                )
            if name == "bounded_inventory":
                rendered = " ".join(f.text for f in facts).lower()
                passed = passed and all(item in rendered for item in INVENTORY)
            record = {
                "trial": trial,
                "case": name,
                "seconds": time.monotonic() - started,
                "passed": passed,
                "new_generation_counts": [len(c) for c in new_calls],
                "snapshots": snapshots,
            }
            results.append(record)
            write(root / "results.json", results)
            print(trial, name, passed, record["new_generation_counts"], flush=True)
            memory.close()
    print("OUTPUT", root, flush=True)
    if not all(r["passed"] for r in results):
        raise SystemExit("Native bounded fact consolidation failed")
    await verify_render_reuse(root)


async def verify_render_reuse(root):
    checks = []
    for case_root in sorted(root.glob("*-*/store")):
        memory = Mycelium(case_root, config_path="mycelium.toml")
        memory.llm.trace_path = root / "reuse-calls.jsonl"
        resolver = FactResolver(memory.llm, memory.artifacts, memory.config)
        for fact in memory.artifacts.list_consolidated_facts():
            if len(fact.member_claim_ids) <= 1:
                continue
            owner = memory.artifacts.get_entity(fact.owner_entity_id)
            before = len(memory.llm._call_log)
            text = await resolver._render_group(
                resolver._owner_text(owner),
                [
                    memory.artifacts.get_claim(cid)
                    for cid in reversed(fact.member_claim_ids)
                ],
            )
            calls = list(memory.llm._call_log)[before:]
            checks.append(
                {
                    "store": str(case_root),
                    "fact_id": fact.fact_id,
                    "calls": calls,
                    "passed": text == fact.text
                    and len(calls) == 1
                    and calls[0]["metadata"].get("cache_hit") is True,
                }
            )
        memory.close()
    write(root / "render-reuse.json", checks)
    print(
        "PERSISTED_RENDER_REUSE",
        len(checks),
        all(c["passed"] for c in checks),
        flush=True,
    )
    if not checks or not all(c["passed"] for c in checks):
        raise SystemExit("Persistent group text reuse failed")


if __name__ == "__main__":
    asyncio.run(main())
