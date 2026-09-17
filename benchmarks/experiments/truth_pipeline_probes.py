"""Native neutral owner-independent truth review and page publication probes."""

import asyncio
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.truth_scope_probes import CASES
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.artifacts import ArtifactStore, ClaimPlacement, ClaimProvenance, MemoryClaim, SourceDocument, SourceSegment
from mycelium.config import Config
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.store import WikiStore


async def main():
    root = fresh_run_root("truth-pipeline")
    print("OUTPUT", root, flush=True)
    config = Config.from_toml(Path("mycelium.toml"))
    write(root / "config.json", asdict(config))
    qa = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm)
    qa.llm.trace_path = root / "calls.jsonl"
    qa.llm.client = RecordingClient(qa.llm.client, root / "requests")
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(config.llm.url.rstrip("/") + "/api/tags")
        response.raise_for_status()
        write(root / "models.json", response.json())
    results = []
    for trial in range(3):
        for name, left, right, left_owner, right_owner, expected in CASES:
            case_root = root / f"{trial}-{name}"
            artifacts = ArtifactStore(case_root / "artifacts")
            owners = {title: artifacts.create_entity("topic", title) for title in {left_owner, right_owner}}
            placements = []
            for cid, text, title in (("left", left, left_owner), ("right", right, right_owner)):
                source_id, segment_id = f"source-{cid}", f"source-{cid}#1"
                artifacts.save_source(SourceDocument(source_id, "agent_conversation", source_id,
                    "2031-01-01", None, [], [SourceSegment(segment_id, 0, text)]))
                claim = MemoryClaim(cid, text, [], [ClaimProvenance(source_id, [segment_id])],
                                    "2031-01-01", claim_type="unknown", temporal_status="unknown")
                artifacts.save_claim(claim)
                placement = ClaimPlacement(cid, owners[title].entity_id, "why_it_matters", [], "placed",
                                           "Explicit neutral probe ownership", "2031-01-01", "2031-01-01")
                artifacts.save_placement(placement)
                placements.append(placement)
            resolver = FactResolver(qa.llm, artifacts, config)
            if name != "same_batch":
                prior, _ = resolver._direct_projection(owners[left_owner], artifacts.get_claim("left"), placements[0])
                artifacts.save_consolidated_fact(prior)
            started = time.monotonic()
            incoming = {"left", "right"} if name == "same_batch" else {"right"}
            result = await resolver.resolve(placements, affected_entity_ids={e.entity_id for e in owners.values()},
                incoming_claim_ids=incoming, dream_run_id=f"probe-{trial}-{name}")
            for proposal in result.proposals:
                artifacts.save_reconsolidation_proposal(proposal)
            for fid in result.deleted_fact_ids:
                artifacts.delete_consolidated_fact(fid)
            for fact in result.facts:
                artifacts.save_consolidated_fact(fact)
            for placement in result.placements:
                artifacts.save_placement(placement)
            wiki = WikiStore(case_root / "wiki")
            PageMaterializer(wiki, artifacts, config).regenerate({e.entity_id for e in owners.values()})
            before_repeat = len(qa.llm._call_log)
            repeated = await resolver.resolve(placements, affected_entity_ids={e.entity_id for e in owners.values()},
                incoming_claim_ids=incoming, dream_run_id=f"repeat-{trial}-{name}")
            repeat_calls = list(qa.llm._call_log)[before_repeat:]
            if expected == "no_change":
                passed = not result.proposals
            else:
                retained = "left" if expected == "left_supersedes_right" else "right"
                target = "right" if retained == "left" else "left"
                relation = "contradicts" if expected == "contradicts" else "supersedes"
                passed = len(result.proposals) == 1 and result.proposals[0].proposed_relation == relation
                passed = passed and result.proposals[0].incoming_claim_ids == [retained] and result.proposals[0].target_claim_ids == [target]
            record = {"trial": trial, "case": name, "expected": expected, "seconds": time.monotonic()-started,
                      "result": asdict(result), "coverage": artifacts.coverage_report(),
                      "claims": [asdict(c) for c in artifacts.list_claims()],
                      "repeat_calls": repeat_calls, "repeat_result": asdict(repeated),
                      "passed": passed and not result.failures and not repeated.failures
                                and not repeated.proposals and all(c["metadata"].get("cache_hit") for c in repeat_calls)
                                and all(c.status == "active" for c in artifacts.list_claims())}
            results.append(record)
            write(case_root / "result.json", record)
            write(root / "results.json", results)
            print(name, trial, record["passed"], record["seconds"], flush=True)
            artifacts.db.close()
    write(root / "completion.json", {"passed": sum(r["passed"] for r in results), "total": len(results)})
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Native truth review failed a neutral case")


if __name__ == "__main__":
    asyncio.run(main())
