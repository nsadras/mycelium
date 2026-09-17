"""Configured-model truth search, review proposals, and fixed-batch scale costs."""

import argparse
import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.truth_candidate_inputs import controls, record
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimEntityReference,
    ClaimPlacement,
    ClaimProvenance,
    EntityRecord,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.snapshots import snapshot_store
from mycelium.truth_review import TruthReviewer


async def main(scale=False):
    root = fresh_run_root(
        "truth-candidate-scale" if scale else "truth-candidate-pipeline"
    )
    print("OUTPUT", root, flush=True)
    root.mkdir(parents=True)
    (root / "probe.py").write_text(Path(__file__).read_text())
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        memory.llm.trace_path = root / "calls.jsonl"
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        reviewer = TruthReviewer(memory.llm, memory.artifacts, memory.config)
        if scale:
            results = []
            for size in (100, 1000, 10000):
                records = {
                    f"c{i:05d}": record(
                        f"c{i:05d}",
                        f"Archive item {i} is stored in cabinet {i % 97}.",
                        f"cabinet-{i % 97}",
                        surface=f"cabinet {i % 97}",
                    )
                    for i in range(size)
                }
                incoming = sorted(records)[-4:]
                for temperature in ("cold_or_growing", "warm"):
                    started = time.perf_counter()
                    pools = await reviewer._candidate_pools(
                        incoming, records, frozenset()
                    )
                    row = dict(
                        history_count=size,
                        incoming_count=len(incoming),
                        temperature=temperature,
                        seconds=time.perf_counter() - started,
                        eligible_pairs=sum(map(len, pools.values())),
                    )
                    assert row["eligible_pairs"] <= len(incoming) * 48
                    results.append(row)
                    write(root / "results.json", results)
                    write(
                        root / f"search-{size}-{temperature}.json",
                        reviewer.candidate_trace,
                    )
                    print(json.dumps(row), flush=True)
            return

        records, incoming, annotations = controls()
        write(
            root / "inputs.json",
            dict(records=records, incoming=incoming, annotations=annotations),
        )
        artifacts = memory.artifacts
        owner = artifacts.create_entity("project", "Restoration")
        identity_names = {
            ref["entity_id"]: ref["surface"]
            for row in records.values()
            for ref in row["identity_bindings"]
        }
        for eid, name in identity_names.items():
            artifacts.save_entity(
                EntityRecord(
                    eid,
                    "person" if eid not in {"inventory", "concert"} else "project",
                    name,
                    eid,
                    [],
                    "active",
                    "2031-05-06",
                    "2031-05-06",
                )
            )
        placements = {}
        for cid, row in records.items():
            citation = row["citations"][0]
            source = SourceDocument(
                citation["source_id"],
                "document",
                cid,
                "2031-05-06",
                citation["source_time"],
                [],
                [
                    SourceSegment(
                        citation["segment_id"], 0, citation["text"], citation["speaker"]
                    )
                ],
            )
            artifacts.save_source(source)
            artifacts.save_claim(
                MemoryClaim(
                    cid,
                    row["text"],
                    [],
                    [ClaimProvenance(source.source_id, [citation["segment_id"]])],
                    "2031-05-06",
                )
            )
            for ref in row["identity_bindings"]:
                artifacts.save_entity_reference(
                    ClaimEntityReference(
                        "ref-" + cid,
                        cid,
                        ref["role"],
                        ref["surface"],
                        ref["entity_id"],
                        ref["confidence"],
                        ref["reason"],
                        ref["origin"],
                        "seed",
                        "active",
                        "2031-05-06",
                    )
                )
            if cid.startswith("reschedule"):
                placements[cid] = ClaimPlacement(
                    cid,
                    "you" if cid in incoming else owner.entity_id,
                    "preferences_working_style" if cid in incoming else "overview",
                    [],
                    "placed",
                    "Separate views of the same evidence-backed subject",
                    "2031-05-06",
                    "2031-05-06",
                )
                artifacts.save_placement(placements[cid])
        before = [asdict(c) for c in artifacts.list_claims()]
        result = await reviewer.review(
            set(incoming),
            placements,
            {e.entity_id: e for e in artifacts.list_entities()},
            dream_run_id="native",
        )
        write(root / "result.json", asdict(result))
        write(root / "search.json", reviewer.candidate_trace)
        for proposal in result.proposals:
            assert proposal.status == "pending"
            artifacts.save_reconsolidation_proposal(proposal)
        assert before == [asdict(c) for c in artifacts.list_claims()]
        outcomes = []
        for annotation in annotations:
            pair = {annotation["left"], annotation["right"]}
            found = [
                asdict(p)
                for p in result.proposals
                if pair <= set(p.incoming_claim_ids + p.target_claim_ids)
            ]
            outcomes.append({**annotation, "proposals": found})
        write(root / "outcomes.json", outcomes)
        snapshot_store(memory.store_path, root / "snapshot")
        print(
            json.dumps(
                {
                    "errors": result.errors,
                    "proposals": len(result.proposals),
                    "annotated_proposal_counts": [
                        (r["case"], len(r["proposals"])) for r in outcomes
                    ],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", action="store_true")
    asyncio.run(main(parser.parse_args().scale))
