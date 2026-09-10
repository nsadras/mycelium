"""Shared artifact builders for memory tests; no test-module imports."""

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    ConsolidatedFact,
    MemoryClaim,
)


def claim(claim_id: str, text: str, recorded_at: str) -> MemoryClaim:
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        about=[{"entity": "user"}],
        provenance=[ClaimProvenance(
            source_id=f"source-{claim_id}",
            segment_ids=[f"source-{claim_id}#seg-0001"],
            raw_log_entry_id=f"log-{claim_id}",
            speaker="user",
        )],
        recorded_at=recorded_at,
        claim_type="preference",
        predicate="prefers",
        temporal_status="atemporal",
    )


def setup_owner(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.create_entity("you", "You")
    return artifacts


def place(artifacts: ArtifactStore, item: MemoryClaim) -> ClaimPlacement:
    artifacts.save_claim(item)
    placement = ClaimPlacement(
        item.claim_id, "you", "preferences_working_style", [], "placed", "test",
        item.recorded_at, item.recorded_at,
    )
    artifacts.save_placement(placement)
    return placement


def fact(item: MemoryClaim) -> ConsolidatedFact:
    return ConsolidatedFact(
        fact_id=f"fact-{item.claim_id}",
        text=item.text,
        member_claim_ids=[item.claim_id],
        owner_entity_id="you",
        section_key="preferences_working_style",
        state="current",
        linked_entity_ids=[],
        synthesis_origin="claim",
        confidence=item.confidence,
        reason="test",
        created_at=item.recorded_at,
        updated_at=item.recorded_at,
    )
