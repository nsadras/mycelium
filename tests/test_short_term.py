from datetime import datetime, timedelta, timezone

from mycelium.artifacts import ArtifactStore, ClaimPlacement, ClaimProvenance, MemoryClaim
from mycelium.short_term import ShortTermMemoryQueue


def _claim(claim_id: str, recorded_at: datetime, *, disposition: str = "pending") -> MemoryClaim:
    return MemoryClaim(
        claim_id=claim_id,
        text=f"A durable memory named {claim_id}.",
        about=[{"entity": "Ava", "role": "subject"}],
        provenance=[ClaimProvenance("source-1", ["segment-1"])],
        recorded_at=recorded_at.isoformat(),
        dream_disposition=disposition,
        dream_disposition_at=recorded_at.isoformat() if disposition != "pending" else None,
    )


def test_queue_counts_pending_without_counting_placed_claims(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    now = datetime(2026, 8, 12, 12, tzinfo=timezone.utc)
    queue = ShortTermMemoryQueue(artifacts)
    artifacts.save_claim(_claim("recent", now - timedelta(hours=1)))

    assert queue.status().pending_claims == 1

    artifacts.save_claim(_claim("old", now - timedelta(hours=25)))
    status = queue.status()

    assert status.pending_claims == 2

    entity = artifacts.create_entity("person", "Ava")
    artifacts.save_placement(ClaimPlacement(
        claim_id="recent",
        owner_entity_id=entity.entity_id,
        section_key="current_context",
        linked_entity_ids=[],
        status="placed",
        reason="test",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    ))

    assert queue.status().pending_claims == 1


def test_deferred_claim_remains_available_for_manual_build(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    now = datetime(2026, 8, 12, 12, tzinfo=timezone.utc)
    claim = _claim("deferred", now - timedelta(days=8), disposition="deferred")
    artifacts.save_claim(claim)
    artifacts.save_placement(ClaimPlacement(
        claim_id=claim.claim_id,
        owner_entity_id=None,
        section_key=None,
        linked_entity_ids=[],
        status="deferred",
        reason="More context is required.",
        created_at=claim.recorded_at,
        updated_at=claim.recorded_at,
    ))
    queue = ShortTermMemoryQueue(artifacts)

    status = queue.status()

    assert status.deferred_claims == 1
    assert artifacts.memory_tier(claim.claim_id) == "short_term"
