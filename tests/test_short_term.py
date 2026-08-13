from datetime import datetime, timedelta, timezone

from mycelium.artifacts import ArtifactStore, ClaimPlacement, ClaimProvenance, MemoryClaim
from mycelium.config import DreamConfig
from mycelium.short_term import ShortTermMemoryQueue


def _claim(claim_id: str, recorded_at: datetime, *, disposition: str = "pending") -> MemoryClaim:
    return MemoryClaim(
        claim_id=claim_id,
        text=f"A durable memory named {claim_id}.",
        kind="fact",
        about=[{"entity": "Ava", "role": "subject"}],
        provenance=[ClaimProvenance("source-1", ["segment-1"])],
        recorded_at=recorded_at.isoformat(),
        dream_disposition=disposition,
        dream_disposition_at=recorded_at.isoformat() if disposition != "pending" else None,
    )


def test_queue_readiness_uses_size_and_age_without_counting_placed_claims(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    now = datetime(2026, 8, 12, 12, tzinfo=timezone.utc)
    config = DreamConfig(
        queue_claim_threshold=2,
        max_pending_hours=24,
        deferred_revisit_hours=168,
    )
    queue = ShortTermMemoryQueue(artifacts, config)
    artifacts.save_claim(_claim("recent", now - timedelta(hours=1)))

    assert queue.status(now=now).ready is False

    artifacts.save_claim(_claim("old", now - timedelta(hours=25)))
    status = queue.status(now=now)

    assert status.ready is True
    assert status.pending_claims == 2
    assert status.reasons == ["claim_threshold", "max_pending_age"]

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

    assert queue.status(now=now).pending_claims == 1


def test_deferred_claim_becomes_due_for_weekly_reconsideration(tmp_path):
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
    queue = ShortTermMemoryQueue(artifacts, DreamConfig())

    status = queue.status(now=now)

    assert status.ready is True
    assert status.include_deferred is True
    assert status.reasons == ["deferred_review_due"]
    assert artifacts.memory_tier(claim.claim_id) == "short_term"
