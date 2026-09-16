"""Replay production truth review on an immutable snapshot with independent trials."""

import argparse
import asyncio
from dataclasses import asdict
import hashlib
from pathlib import Path
import sqlite3

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.artifacts import ArtifactStore
from mycelium.config import Config
from mycelium.telemetry import trace_operation
from mycelium.truth_review import TruthReviewer


async def main(args):
    root = fresh_run_root("truth-replay")
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump())
    llm.client = RecordingClient(llm.client, root / "requests")
    original = (args.snapshot / "memory.sqlite3").resolve()
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    write(
        root / "experiment.json",
        {
            "snapshot": str(original),
            "snapshot_sha256": digest,
            "incoming_claim_id": args.incoming_claim_id,
            "expected_target": args.expected_target,
            "concurrent_benchmark": args.concurrent_benchmark,
            "latencies_comparable": not bool(args.concurrent_benchmark),
            "copy_changes": [
                "Remove model decision cache for independent generations",
                "Remove earlier proposals to recompute comparisons",
            ],
        },
    )
    print("OUTPUT", root, flush=True)
    results = []
    for trial in range(args.trials):
        target = root / str(trial) / "store"
        target.mkdir(parents=True)
        source = sqlite3.connect(original.as_uri() + "?mode=ro", uri=True)
        destination = sqlite3.connect(target / "memory.sqlite3")
        try:
            source.backup(destination)
        finally:
            source.close()
            destination.close()
        artifacts = ArtifactStore(target / "artifacts")
        try:
            for kind in ["model-decisions", "reconsolidation-proposals"]:
                for identifier in artifacts.db.ids(kind):
                    artifacts.db.delete(kind, identifier)
            reviewer = TruthReviewer(llm, artifacts)
            candidate_call, compare_call = (
                reviewer._candidate_pairs,
                reviewer._compare_pairs,
            )

            async def candidates(incoming, records):
                write(root / str(trial) / "records.json", records)
                pairs = await candidate_call(incoming, records)
                write(root / str(trial) / "candidates.json", sorted(pairs))
                return pairs

            async def compare(pairs, records):
                decisions = await compare_call(pairs, records)
                write(
                    root / str(trial) / "comparisons.json",
                    [
                        {"pair": pair, **decision}
                        for pair, decision in decisions.items()
                    ],
                )
                return decisions

            reviewer._candidate_pairs, reviewer._compare_pairs = candidates, compare
            with trace_operation("truth_replay", trial=trial):
                result = await reviewer.review(
                    {args.incoming_claim_id},
                    {p.claim_id: p for p in artifacts.list_placements()},
                    {e.entity_id: e for e in artifacts.list_entities()},
                    dream_run_id=f"trial-{trial}",
                )
            passed = not result.errors and any(
                args.incoming_claim_id in p.incoming_claim_ids
                and args.expected_target in p.target_claim_ids
                and p.proposed_relation == "supersedes"
                for p in result.proposals
            )
            record = {"trial": trial, "passed": passed, "result": asdict(result)}
            results.append(record)
            write(root / "results.json", results)
            print(trial, passed, result.errors, flush=True)
        finally:
            artifacts.db.close()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest, (
        "Original snapshot changed"
    )
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in results), "total": len(results)},
    )
    if not all(r["passed"] for r in results):
        raise SystemExit("Truth replay acceptance failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--incoming-claim-id", required=True)
    parser.add_argument("--expected-target", required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--concurrent-benchmark")
    asyncio.run(main(parser.parse_args()))
