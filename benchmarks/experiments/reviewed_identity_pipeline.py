"""Native routing runs for reviewed identity occurrences and co-mentioned subjects."""

import asyncio
import os
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.identity_review_cases import CASES
from benchmarks.shared.adapters import OllamaQaClient
from mycelium.artifacts import ArtifactStore, ClaimEntityReference, ClaimProvenance, EntityRecord, MemoryClaim, SourceDocument, SourceSegment
from mycelium.config import Config
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation_models import ClaimEvidence


async def main():
    root = fresh_run_root("reviewed-identity-pipeline")
    memory_config = Config.from_toml(Path("mycelium.toml"))
    config = memory_config.llm
    write(root / "config.json", vars(config))
    os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "requests")
    qa = OllamaQaClient(config.model, config.url, llm_config=config)
    qa.llm.trace_path = root / "calls.jsonl"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(config.url.rstrip("/") + "/api/tags")
        response.raise_for_status()
        write(root / "models.json", response.json())
    results = []
    for trial in range(3):
        for name, text, registry, reviews, expected_existing, expected_new_types in CASES:
            artifacts = ArtifactStore(root / f"{trial}-{name}" / "artifacts")
            artifacts.create_entity("you", "You")
            for eid, (kind, title) in registry.items():
                artifacts.save_entity(EntityRecord(eid, kind, title, eid, [], "active", "2031-01-01", "2031-01-01"))
            source = SourceDocument("source", "agent_conversation", "source", "2031-01-01", None, [],
                                    [SourceSegment("source#1", 0, text)])
            claim = MemoryClaim("claim", text, [], [ClaimProvenance("source", ["source#1"])], "2031-01-01")
            artifacts.save_source(source)
            artifacts.save_claim(claim)
            for i, (eid, surface) in enumerate(reviews):
                artifacts.save_entity_reference(ClaimEntityReference(
                    f"review-{i}", claim.claim_id, "identity_subject", surface, eid, 1., "Explicit reviewed identity",
                    "manual", "review", "active", "2031-01-01", identity_decision_id=f"decision-{i}",
                ))
            started = time.monotonic()
            result = await ClaimRouter(qa.llm, artifacts, memory_config).route([ClaimEvidence(claim, source)], dream_run_id="probe")
            plan = artifacts.list_identity_work_units()[0].entity_plan
            existing = {n["entity_id"] for n in plan.get("subjects", []) if n["resolution"] == "existing"}
            new_types = {n["entity_type"] for n in plan.get("subjects", []) if n["resolution"] == "new"}
            passed = existing == expected_existing and new_types >= expected_new_types and not result.failures
            record = {"case": name, "trial": trial, "seconds": time.monotonic()-started, "passed": passed,
                      "result": asdict(result), "plan": plan,
                      "references": [asdict(ref) for ref in artifacts.list_entity_references(claim_id=claim.claim_id)]}
            results.append(record)
            write(root / "results.json", results)
            print(trial, name, passed, result.failures, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Native reviewed identity pipeline failed a neutral case")


if __name__ == "__main__":
    asyncio.run(main())
