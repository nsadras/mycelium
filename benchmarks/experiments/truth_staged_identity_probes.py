"""Paired truth preparation with persisted versus current-build identity context."""

import argparse
import asyncio
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimPlacement,
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.config import Config
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.ontology import default_section
from mycelium.snapshots import snapshot_store
from mycelium.store import WikiStore
from mycelium.truth_review import TruthReviewer


def record(cid, text, owner, day, entity_id):
    return {
        "claim_id": cid,
        "text": text,
        "about": [],
        "temporal_status": "current",
        "temporal": [],
        "page_owner": {"entity_id": owner, "title": owner},
        "identity_bindings": [
            asdict(
                ClaimEntityReference(
                    reference_id="r-" + cid,
                    claim_id=cid,
                    role="subject",
                    surface=None,
                    entity_id=entity_id,
                    confidence=0.9,
                    reason="Resolved from the source evidence.",
                    origin="scope",
                    dream_run_id="current",
                    status="active",
                    created_at=day,
                )
            )
        ],
        "citations": [
            {
                "source_id": "s-" + cid,
                "segment_id": "line-" + cid,
                "source_time": day,
                "message_time": None,
                "speaker": "User",
                "text": text,
            }
        ],
    }


def cases():
    yield (
        "first_naming",
        "I am not ready to name the inventory application yet.",
        "The inventory application is now called Cobalt.",
        "inventory",
        "inventory",
        "right_supersedes_left",
    )
    yield (
        "decision_transition",
        "I have not selected a venue for the workshop yet.",
        "I have now selected the town hall as the workshop venue.",
        "workshop",
        "workshop",
        "right_supersedes_left",
    )
    yield (
        "different_applications",
        "I am not ready to name the inventory application yet.",
        "My separate budget application is now called Cobalt.",
        "inventory",
        "budget",
        "no_change",
    )
    yield (
        "compatible_detail",
        "The inventory application is now called Cobalt.",
        "The inventory application stores records locally.",
        "inventory",
        "inventory",
        "no_change",
    )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", action="store_true")
    args = parser.parse_args()
    root = fresh_run_root(
        "truth-staged-identity-pipeline"
        if args.pipeline
        else "truth-staged-identity-contract"
    )
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump(mode="json"))
    (root / "probe.py").write_text(Path(__file__).read_text())
    llm.client = RecordingClient(llm.client, root / "requests")
    artifacts = ArtifactStore(root / "store" / "artifacts")
    reviewer = TruthReviewer(llm, artifacts, config)
    rows = []
    print("OUTPUT", root, flush=True)
    try:
        for trial in range(3):
            for name, old, new, old_id, new_id, expected in cases():
                records = {
                    "a": record("a", old, "you", "2031-05-01", old_id),
                    "b": record("b", new, new_id, "2031-05-08", new_id),
                }
                for arm in ("staged",) if args.pipeline else ("persisted", "staged"):
                    inputs = deepcopy(records)
                    if arm == "persisted":
                        inputs["b"]["identity_bindings"] = []
                    row = {
                        "trial": trial,
                        "case": name,
                        "arm": arm,
                        "status": "running",
                        "records": inputs,
                    }
                    rows.append(row)
                    write(root / "results.json", rows)
                    try:
                        if args.pipeline:
                            row.update(
                                await native_case(
                                    root / f"{trial}-{name}",
                                    llm,
                                    config,
                                    records,
                                    expected,
                                )
                            )
                            write(root / "results.json", rows)
                            print(trial, name, arm, row["passed"], flush=True)
                            continue
                        pairs = sorted(await reviewer._candidate_pairs(["b"], inputs))
                        decisions = await reviewer._compare_pairs(pairs, inputs)
                        decision = decisions.get(("a", "b"))
                        passed = (
                            (decision is None or decision["relation"] == "no_change")
                            if expected == "no_change"
                            else decision is not None
                            and decision["relation"] == expected
                        )
                        row.update(
                            status="complete",
                            pairs=pairs,
                            decision=decision,
                            passed=passed,
                        )
                    except Exception as exc:
                        row.update(
                            status="failed",
                            passed=False,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    write(root / "results.json", rows)
                    print(
                        trial, name, arm, row["passed"], row.get("decision"), flush=True
                    )
    finally:
        artifacts.db.close()
    write(
        root / "completion.json",
        {
            arm: {
                "passed": sum(r["passed"] for r in rows if r["arm"] == arm),
                "total": sum(r["arm"] == arm for r in rows),
            }
            for arm in ("persisted", "staged")
        },
    )


async def native_case(root, llm, config, records, expected):
    artifacts = ArtifactStore(root / "artifacts")
    wiki = WikiStore(root / "wiki")
    try:
        names = {r["page_owner"]["entity_id"] for r in records.values()} | {
            r["identity_bindings"][0]["entity_id"] for r in records.values()
        }
        entities = {
            name: artifacts.create_entity(
                "you" if name == "you" else "project", "You" if name == "you" else name
            )
            for name in sorted(names)
        }
        placements, references = [], {}
        for cid, row in records.items():
            c = row["citations"][0]
            artifacts.save_source(
                SourceDocument(
                    c["source_id"],
                    "agent_conversation",
                    c["source_id"],
                    c["source_time"],
                    c["source_time"],
                    ["User"],
                    [SourceSegment(c["segment_id"], 0, c["text"], "User", "user")],
                )
            )
            artifacts.save_claim(
                MemoryClaim(
                    cid,
                    row["text"],
                    [],
                    [ClaimProvenance(c["source_id"], [c["segment_id"]])],
                    c["source_time"],
                    temporal_status="current",
                )
            )
            owner = entities[row["page_owner"]["entity_id"]]
            section = default_section(owner.entity_type, "unknown", None)
            placement = ClaimPlacement(
                cid,
                owner.entity_id,
                section,
                [],
                "placed",
                "Explicit probe ownership",
                c["source_time"],
                c["source_time"],
                page_sections={owner.entity_id: section},
            )
            placements.append(placement)
            artifacts.save_placement(placement)
            raw = row["identity_bindings"][0]
            references[cid] = ClaimEntityReference(
                **{**raw, "entity_id": entities[raw["entity_id"]].entity_id}
            )
        artifacts.save_entity_reference(references["a"])
        resolver = FactResolver(llm, artifacts, config)
        prior, _ = resolver._direct_projection(
            entities[records["a"]["page_owner"]["entity_id"]],
            artifacts.get_claim("a"),
            placements[0],
        )
        artifacts.save_consolidated_fact(prior)
        result = await resolver.resolve(
            placements,
            affected_entity_ids={e.entity_id for e in entities.values()},
            incoming_claim_ids={"b"},
            dream_run_id="current",
            reference_replacements={"b": [references["b"]]},
        )
        assert not artifacts.list_entity_references(claim_id="b")
        artifacts.replace_automatic_entity_references(
            {"b"}, [references["b"]], dream_run_id="current"
        )
        for proposal in result.proposals:
            artifacts.save_reconsolidation_proposal(proposal)
        for fid in result.deleted_fact_ids:
            artifacts.delete_consolidated_fact(fid)
        for fact in result.facts:
            artifacts.save_consolidated_fact(fact)
        for placement in result.placements:
            artifacts.save_placement(placement)
        PageMaterializer(wiki, artifacts, config).regenerate(
            {e.entity_id for e in entities.values()}
        )
        # Human review still owns canonical replacement; both source claims survive.
        passed = not result.failures and all(
            c.status == "active" for c in artifacts.list_claims()
        )
        passed = passed and (
            not result.proposals
            if expected == "no_change"
            else len(result.proposals) == 1
            and result.proposals[0].proposed_relation == "supersedes"
            and result.proposals[0].incoming_claim_ids == ["b"]
            and result.proposals[0].target_claim_ids == ["a"]
        )
        snapshot = root.with_name(root.name + "-snapshot")
        snapshot_store(root, snapshot)
        return {
            "status": "complete",
            "passed": passed,
            "result": asdict(result),
            "snapshot_path": str(snapshot),
        }
    finally:
        artifacts.db.close()


if __name__ == "__main__":
    asyncio.run(main())
