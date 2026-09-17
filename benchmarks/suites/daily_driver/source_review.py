"""Read-only source-to-wiki review packs, independent of lexical scoring."""

import json
from pathlib import Path

from benchmarks.suites.daily_driver.assessment_inputs import (
    assessment_inputs,
    digest,
    json_default,
)
from benchmarks.suites.daily_driver.eval import load_snapshots
from benchmarks.suites.daily_driver.fixture import load_fixture


COLLECTIONS = {
    "sources": "source_id",
    "claims": "claim_id",
    "entities": "entity_id",
    "placements": "claim_id",
    "consolidated_facts": "fact_id",
    "pages": "slug",
}


def _index(rows, key):
    result = {}
    for row in rows:
        identifier = row[key]
        if identifier in result:
            raise ValueError(f"Duplicate {key}: {identifier}")
        result[identifier] = row
    return result


def checkpoint_review(fixture, snapshot, previous=None):
    """Expose every exact evidence candidate and every changed artifact for review.

    Equality identifies changed records, never equivalent human-language meaning.
    A snapshot hash binds any later review to the complete state, including pages.
    """
    changes = {}
    for collection, key in COLLECTIONS.items():
        before = _index((previous or {}).get(collection, []), key)
        after = _index(snapshot.get(collection, []), key)
        changes[collection] = {
            "added": [after[i] for i in sorted(after.keys() - before.keys())],
            "removed": [before[i] for i in sorted(before.keys() - after.keys())],
            "changed": [
                {"id": i, "before": before[i], "after": after[i]}
                for i in sorted(before.keys() & after.keys())
                if before[i] != after[i]
            ],
        }
    return {
        "schema_version": 1,
        "assessment_status": "requires_source_review",
        "checkpoint_id": snapshot["checkpoint_id"],
        "snapshot_digest": digest(snapshot),
        "fixture_digest": digest(fixture),
        "previous_snapshot_digest": digest(previous) if previous is not None else None,
        "previous_checkpoint_id": previous["checkpoint_id"]
        if previous is not None
        else None,
        "claim_inputs": assessment_inputs(fixture, snapshot),
        "entity_references": fixture.get("gold_wiki", {}).get("entities", []),
        "claim_references": fixture.get("gold_claims", {}).get("claims", []),
        "snapshot": snapshot,
        "changes": changes,
    }


def export_source_review(fixture_dir, run_dir, output_dir):
    """Write a new review pack without modifying a run or invoking a model."""
    fixture = load_fixture(Path(fixture_dir))
    snapshots = load_snapshots(Path(run_dir))
    order = [c["id"] for c in fixture["gold_checkpoints"]["checkpoints"]]
    unknown = snapshots.keys() - set(order)
    if unknown:
        raise ValueError(
            f"Run contains checkpoints outside this fixture: {sorted(unknown)}"
        )
    packs = []
    previous = None
    for cid in order:
        if cid not in snapshots:
            continue
        current = snapshots[cid]
        if current["checkpoint_id"] != cid:
            raise ValueError(
                f"Snapshot checkpoint ID does not match its directory: {cid}"
            )
        packs.append(checkpoint_review(fixture, current, previous))
        previous = current
    output_dir = Path(output_dir)
    # Validate all inputs before publishing anything. Never overwrite old reviews.
    output_dir.mkdir(parents=True, exist_ok=False)
    for pack in packs:
        path = output_dir / f"{pack['checkpoint_id']}.json"
        path.write_text(
            json.dumps(pack, indent=2, ensure_ascii=False, default=json_default) + "\n"
        )
    summary = {
        "schema_version": 1,
        "assessment_status": "requires_source_review",
        "run_dir": str(Path(run_dir).resolve()),
        "fixture_digest": digest(fixture),
        "available_checkpoints": [p["checkpoint_id"] for p in packs],
        "missing_checkpoints": [cid for cid in order if cid not in snapshots],
        "output_dir": str(output_dir.resolve()),
    }
    (output_dir / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
