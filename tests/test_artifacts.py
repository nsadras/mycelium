from tests.extraction_support import time_details
import pytest
from unittest.mock import AsyncMock
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    MemoryClaim,
    ReconsolidationProposal,
    SourceDocument,
    SourceSegment,
    normalize_temporal_facets,
    temporal_intervals_overlap,
)
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.store import LogStore


def test_semantic_envelope_does_not_infer_from_kind_or_prose():
    provenance = [ClaimProvenance("source-1", ["source-1#seg-0001"])]
    unknown = MemoryClaim(
        claim_id="unknown",
        text="Ava bought a book.",
        about=[{"entity": "Ava"}],
        provenance=provenance,
        recorded_at="2024-01-01",
    )
    assert unknown.claim_type == "unknown"
    assert unknown.evidence_modality == "unknown"
    assert unknown.temporal_status == "unknown"


def test_human_readable_source_timestamp_anchors_declared_offset():
    facets = normalize_temporal_facets(time_details('s1', 'yesterday', {'kind':'day_offset','days':-1}),
                                      {'s1': '4:24 pm on 16 March, 2023'})
    assert facets['temporal'][0]['start'] == '2023-03-15'
    assert facets['temporal'][0]['anchor'] == '4:24 pm on 16 March, 2023'


def test_temporal_interval_overlap_is_inclusive():
    query = {"start": "2026-08-17", "end": "2026-08-23"}
    assert temporal_intervals_overlap(
        query, {"start": "2026-08-23", "end": "2026-08-23"}
    )
    assert not temporal_intervals_overlap(
        query, {"start": "2026-08-24", "end": "2026-08-24"}
    )


def test_artifact_store_clear_removes_all_derived_artifacts(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    store.save_source(
        SourceDocument(
            source_id="source-1",
            source_type="agent_conversation",
            session_id="session-1",
            recorded_at="2024-01-01",
            occurred_at=None,
            participants=["user"],
            segments=[SourceSegment("source-1#seg-0001", 0, "Hello")],
        )
    )
    store.save_episode(
        EpisodeManifest(
            episode_id="episode-1",
            source_id="source-1",
            source_type="agent_conversation",
            occurred_at=None,
            participants=["user"],
            segment_ids=["source-1#seg-0001"],
        )
    )
    store.save_claim(
        MemoryClaim(
            claim_id="claim-1",
            text="The user greeted the assistant.",
            about=[{"entity": "user"}],
            provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
            recorded_at="2024-01-01",
            claim_type="interaction",
            evidence_modality="speech",
            temporal_status="past",
        )
    )
    store.save_reconsolidation_proposal(
        ReconsolidationProposal(
            proposal_id="recon-1",
            incoming_claim_ids=["claim-1"],
            target_claim_ids=["claim-2"],
            proposed_relation="contradicts",
            explanation="Test proposal",
            confidence=0.8,
            dream_run_id="dream-1",
            created_at="2024-01-01",
        )
    )
    counts = store.clear()
    assert counts["sources"] == counts["episodes"] == counts["claims"] == 1
    assert store.list_sources() == []
    assert store.list_episodes() == []
    assert store.list_claims() == []
    assert store.list_reconsolidation_proposals() == []






@pytest.mark.asyncio
async def test_ingestion_key_rejects_different_input(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)
    llm.call_structured.side_effect = [{"segments": {"unused": None}}]
    await encoder.capture_session( "First transcript", "session-1", idempotency_key="stable-key"
    )
    with pytest.raises(ValueError, match="different input"):
        await encoder.capture_session( "Different transcript", "session-1", idempotency_key="stable-key"
        )


def test_repository_values_are_independent_and_observe_committed_edits(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    store.db.put("claims", "a", {"text": "Original"})
    first = store.db.get("claims", "a")
    first["text"] = "Caller edit"
    assert store.db.get("claims", "a")["text"] == "Original"
    revision = store.db.revision("claims")
    store.db.put("claims", "a", {"text": "Committed"})
    assert store.db.revision("claims") > revision
    assert store.db.get("claims", "a")["text"] == "Committed"
