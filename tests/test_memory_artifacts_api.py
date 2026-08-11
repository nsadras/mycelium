from datetime import datetime

import pytest
from fastapi import HTTPException

from mycelium.artifacts import (
    ClaimProvenance,
    EpisodeManifest,
    MemoryClaim,
    ReconsolidationProposal,
    SourceDocument,
    SourceSegment,
)
from mycelium.core import Mycelium
from mycelium.models import LogEntry, WikiPage
from server.api import memory


@pytest.fixture
def artifact_memory(tmp_path, monkeypatch):
    mem = Mycelium(store_path=tmp_path / "store")
    entry = LogEntry(
        entry_id="2026-07-22#session-test",
        session_id="session-1",
        timestamp=datetime(2026, 7, 22, 12, 0),
        content="USER: I prefer tea.",
        importance=0.8,
        status="raw",
    )
    mem.log_store.append(entry)
    source = SourceDocument(
        source_id="source-test",
        source_type="agent_conversation",
        session_id="session-1",
        recorded_at="2026-07-22T12:00:00",
        occurred_at=None,
        participants=["user", "assistant"],
        segments=[SourceSegment(
            segment_id="source-test#seg-0001",
            index=0,
            content="I prefer tea.",
            speaker="user",
            role="user",
        )],
        raw_log_entry_id=entry.entry_id,
    )
    episode = EpisodeManifest(
        episode_id="episode-test",
        source_id=source.source_id,
        source_type=source.source_type,
        occurred_at=None,
        participants=source.participants,
        segment_ids=["source-test#seg-0001"],
        claim_ids=["claim-test", "claim-old"],
        extraction_status="complete",
    )
    claim = MemoryClaim(
        claim_id="claim-test",
        text="The user prefers tea.",
        kind="preference",
        about=[{"entity": "user"}],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=["source-test#seg-0001"],
            raw_log_entry_id=entry.entry_id,
            speaker="user",
        )],
        recorded_at="2026-07-22T12:00:00",
        page_slugs=["user-profile"],
        claim_type="preference",
        evidence_modality="speech",
        temporal_status="atemporal",
    )
    old_claim = MemoryClaim(
        claim_id="claim-old",
        text="The user previously preferred coffee.",
        kind="preference",
        about=[{"entity": "user"}],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=["source-test#seg-0001"],
            raw_log_entry_id=entry.entry_id,
            speaker="user",
        )],
        recorded_at="2026-07-21T12:00:00",
        page_slugs=["user-profile"],
        claim_type="preference",
        evidence_modality="speech",
        temporal_status="atemporal",
    )
    mem.artifacts.save_source(source)
    mem.artifacts.save_episode(episode)
    mem.artifacts.save_claim(claim)
    mem.artifacts.save_claim(old_claim)
    mem.wiki.save(WikiPage(
        slug="archived-page",
        title="Archived",
        content="Archived content",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        confidence=0.8,
        importance=0.5,
    ))
    mem.wiki.archive("archived-page")
    mem.artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="recon-test",
        incoming_claim_id="claim-test",
        target_claim_id="claim-old",
        proposed_relation="contradicts",
        explanation="Fixture proposal",
        confidence=0.5,
        dream_run_id="dream-test",
        created_at="2026-07-22T12:00:00",
        affected_page_slugs=["user-profile"],
    ))
    monkeypatch.setattr(memory, "get_mem", lambda: mem)
    monkeypatch.setattr(memory, "load_meta", lambda: {
        "chat-1": {
            "query": "Tea",
            "transcript": [{"role": "user", "content": "Remember tea."}],
            "episode_seq": 2,
            "active_episode": {"id": "chat-1-ep-2", "buffer": [], "turn_count": 0},
            "encoded_episodes": [{"id": "chat-1-ep-1", "reason": "manual"}],
        }
    })
    return mem


@pytest.mark.asyncio
async def test_artifact_inspection_endpoints_expose_complete_store(artifact_memory):
    overview = await memory.artifact_overview()
    chat_episodes = await memory.list_chat_episode_state()
    sources = await memory.list_artifact_sources()
    source = await memory.get_artifact_source("source-test")
    episodes = await memory.list_artifact_episodes()
    episode = await memory.get_artifact_episode("episode-test")
    claims = await memory.list_artifact_claims()
    claim = await memory.get_artifact_claim("claim-test")
    dream_runs = await memory.list_artifact_dream_runs()
    proposals = await memory.list_reconsolidation_proposals()
    files = await memory.list_stored_memory_files()

    assert overview["coverage"]["accounted_coverage"] == 1.0
    assert overview["projection"] == {
        "page_assignments": 2,
        "assigned_claims": 2,
        "multi_page_claims": 0,
        "average_pages_per_claim": 1.0,
        "max_pages_per_claim": 1,
    }
    assert overview["dream_audit"] == {
        "runs": 0,
        "claim_dispositions": {"pending": 2},
    }
    assert overview["integrity"] == {
        "healthy": True,
        "issues": {
            "sources_without_episode": [],
            "episodes_missing_source": [],
            "episodes_missing_claims": [],
            "claims_missing_episode": [],
            "claims_missing_provenance": [],
            "claims_missing_source": [],
            "claims_missing_segments": [],
            "claims_missing_pages": [],
                "sources_missing_raw_log": [],
                "proposals_missing_claims": [],
                "pages_unclassified": [],
            },
    }
    assert chat_episodes == [{
        "session_id": "chat-1",
        "query": "Tea",
        "transcript_turns": 1,
        "episode_seq": 2,
        "active_episode": {"id": "chat-1-ep-2", "buffer": [], "turn_count": 0},
        "encoded_episodes": [{"id": "chat-1-ep-1", "reason": "manual"}],
    }]
    assert sources[0]["segment_count"] == 1
    assert source["segments"][0]["content"] == "I prefer tea."
    assert episodes == [episode]
    assert episode["claim_ids"] == ["claim-test", "claim-old"]
    assert {item["claim_id"] for item in claims} == {"claim-old", "claim-test"}
    assert claim["provenance"][0]["segment_ids"] == ["source-test#seg-0001"]
    assert dream_runs == []
    assert proposals[0]["proposal_id"] == "recon-test"
    assert overview["reconsolidation_proposals"] == {"pending": 1}
    assert files["wiki_index"]["filename"] == "_index.md"
    assert [item["filename"] for item in files["archived_pages"]] == ["archived-page.md"]


@pytest.mark.asyncio
async def test_artifact_detail_endpoints_return_404(artifact_memory):
    for loader, artifact_id in (
        (memory.get_artifact_source, "source-missing"),
        (memory.get_artifact_episode, "episode-missing"),
        (memory.get_artifact_claim, "claim-missing"),
        (memory.get_artifact_dream_run, "dream-missing"),
        (memory.get_reconsolidation_proposal, "recon-missing"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await loader(artifact_id)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_proposal_endpoint_applies_immediately(artifact_memory):
    response = await memory.reject_reconsolidation_proposal(
        "recon-test",
        memory.ProposalReviewRequest(reviewer_note="Both statements remain relevant."),
    )

    assert response["proposal"]["status"] == "rejected"
    assert response["proposal"]["reviewer_note"] == "Both statements remain relevant."
    assert artifact_memory.artifacts.get_claim("claim-test").status == "active"
    assert artifact_memory.artifacts.get_claim("claim-old").status == "active"


@pytest.mark.asyncio
async def test_review_proposal_endpoint_returns_404(artifact_memory):
    with pytest.raises(HTTPException) as exc_info:
        await memory.approve_reconsolidation_proposal(
            "recon-missing", memory.ProposalReviewRequest()
        )

    assert exc_info.value.status_code == 404
