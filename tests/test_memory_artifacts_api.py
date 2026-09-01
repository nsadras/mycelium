from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from mycelium.artifacts import (
    ClaimProvenance,
    ClaimPlacement,
    ConsolidatedFact,
    EpisodeManifest,
    EntityResolutionDecision,
    IdentityMaturityAssessment,
    MemoryClaim,
    OrganizationProposal,
    ReconsolidationProposal,
    SourceDocument,
    SourceSegment,
)
from mycelium.core import Mycelium
from mycelium.facts import FactResolutionResult
from mycelium.models import LogEntry, WikiPage
from server.api import memory_artifacts, memory_curation
from server.api.memory_contracts import (
    ClaimCorrectionRequest,
    IdentityReviewRequest,
    ProposalReviewRequest,
    SourceRetractionRequest,
)


@pytest.fixture
def artifact_memory(tmp_path, monkeypatch):
    mem = Mycelium(store_path=tmp_path / "store")
    entry = LogEntry(
        entry_id="2026-07-22#session-test",
        session_id="session-1",
        timestamp=datetime(2026, 7, 22, 12, 0),
        content="USER: I prefer tea.",
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
        about=[{"entity": "user"}],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=["source-test#seg-0001"],
            raw_log_entry_id=entry.entry_id,
            speaker="user",
        )],
        recorded_at="2026-07-22T12:00:00",
        claim_type="preference",
        evidence_modality="speech",
        temporal_status="atemporal",
    )
    old_claim = MemoryClaim(
        claim_id="claim-old",
        text="The user previously preferred coffee.",
        about=[{"entity": "user"}],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=["source-test#seg-0001"],
            raw_log_entry_id=entry.entry_id,
            speaker="user",
        )],
        recorded_at="2026-07-21T12:00:00",
        claim_type="preference",
        evidence_modality="speech",
        temporal_status="atemporal",
    )
    mem.artifacts.save_source(source)
    mem.artifacts.save_episode(episode)
    mem.artifacts.save_claim(claim)
    mem.artifacts.save_claim(old_claim)
    for item in (claim, old_claim):
        mem.artifacts.save_placement(ClaimPlacement(
            claim_id=item.claim_id,
            owner_entity_id="you",
            section_key="preferences_working_style",
            linked_entity_ids=[],
            status="placed",
            reason="fixture",
            created_at="2026-07-22T12:00:00",
            updated_at="2026-07-22T12:00:00",
        ))
    stored_fact = ConsolidatedFact(
        fact_id="fact-tea-preference",
        text="The user prefers tea.",
        member_claim_ids=[claim.claim_id],
        owner_entity_id="you",
        section_key="preferences_working_style",
        state="current",
        linked_entity_ids=[],
        synthesis_origin="claim",
        confidence=1.0,
        reason="Direct display of one canonical claim.",
        created_at="2026-07-22T12:00:00",
        updated_at="2026-07-22T12:00:00",
    )
    mem.artifacts.save_consolidated_fact(stored_fact)
    mem.dream_process.fact_resolver.resolve = AsyncMock(
        return_value=FactResolutionResult(facts=[stored_fact])
    )
    mem.wiki.save(WikiPage(
        slug="archived-page",
        title="Archived",
        content="Archived content",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        confidence=0.8,
        page_type="topic",
        entity_id="topic-archived-page",
    ))
    mem.wiki.archive("archived-page")
    mem.artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="recon-test",
        incoming_claim_ids=["claim-test"],
        target_claim_ids=["claim-old"],
        proposed_relation="contradicts",
        explanation="Fixture proposal",
        confidence=0.5,
        dream_run_id="dream-test",
        created_at="2026-07-22T12:00:00",
        affected_entity_ids=["you"],
    ))
    mem.artifacts.save_organization_proposal(OrganizationProposal(
        proposal_id="organization-test",
        proposal_type="assign_claim",
        explanation="Fixture organization proposal",
        confidence=0.7,
        created_at="2026-07-22T12:00:00",
        claim_id="claim-test",
        proposed_owner_entity_id="you",
        proposed_section_key="preferences_working_style",
    ))
    mem.artifacts.save_entity_resolution_decision(EntityResolutionDecision(
        decision_id="identity-review-test",
        decision_type="entity_creation",
        entity_id=None,
        proposed_entity_type="project",
        proposed_title="Tea Journal",
        source_ids=["source-test"],
        supporting_claim_ids=["claim-test"],
        supporting_segment_ids=["source-test#seg-0001"],
        confidence=0.6,
        reason="A continuing Project and incidental context are both plausible.",
        review_state="review_required",
        dream_run_id="dream-test",
        created_at="2026-07-22T12:00:00",
        proposed_scope="independent",
        proposed_page_state="provisional",
    ))
    mem.artifacts.save_identity_maturity_assessment(IdentityMaturityAssessment(
        assessment_id="maturity-test",
        dream_run_id="dream-test",
        identity_key="I001",
        source_node_ids=["N001"],
        proposed_title="Tea Journal",
        proposed_entity_type="project",
        supporting_source_ids=["source-test"],
        supporting_claim_ids=["claim-test"],
        supporting_segment_ids=["source-test#seg-0001"],
        proposal_admission="provisional",
        proposal_basis={},
        proposal_reason="Continuity is not established.",
        proposal_confidence=0.6,
        verifier_verdict="not_required",
        verifier_reason="No explicit prior-history basis was proposed.",
        effective_admission="review_required",
        created_at="2026-07-22T12:00:00",
    ))
    monkeypatch.setattr(memory_artifacts, "get_mem", lambda: mem)
    monkeypatch.setattr(memory_curation, "get_mem", lambda: mem)
    monkeypatch.setattr(memory_artifacts, "load_meta", lambda: {
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
    overview = await memory_artifacts.artifact_overview()
    chat_episodes = await memory_artifacts.list_chat_episode_state()
    sources = await memory_artifacts.list_artifact_sources()
    source = await memory_artifacts.get_artifact_source("source-test")
    episode_summaries = await memory_artifacts.list_artifact_episodes()
    episode = await memory_artifacts.get_artifact_episode("episode-test")
    claim_summaries = await memory_artifacts.list_artifact_claims()
    claim = await memory_artifacts.get_artifact_claim("claim-test")
    dream_run_summaries = await memory_artifacts.list_artifact_dream_runs()
    facts = await memory_artifacts.list_consolidated_facts()
    fact = await memory_artifacts.get_consolidated_fact("fact-tea-preference")
    entity = await memory_artifacts.get_artifact_entity("you")
    proposals = await memory_artifacts.list_reconsolidation_proposals()
    organization_proposals = await memory_artifacts.list_organization_proposals()
    identity_decisions = await memory_artifacts.list_entity_resolution_decisions()
    maturity_assessments = (
        await memory_artifacts.list_identity_maturity_assessments("dream-test")
    )
    files = await memory_artifacts.list_stored_memory_files()
    wiki_index = await memory_artifacts.get_stored_memory_file("index", "_index.md")

    assert overview["coverage"]["accounted_coverage"] == 1.0
    assert identity_decisions[0]["decision_id"] == "identity-review-test"
    assert maturity_assessments[0]["assessment_id"] == "maturity-test"
    assert maturity_assessments[0]["verifier_verdict"] == "not_required"
    assert overview["lifecycle"] == {
        "consolidated_facts": 1,
        "entities": 1,
        "wiki_pages": 1,
    }
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
            "placements_missing_claims": [],
            "placements_missing_entities": [],
            "facts_missing_claims": [],
            "facts_missing_entities": [],
            "placements_with_inactive_entities": [],
            "facts_with_inactive_entities": [],
            "active_references_with_inactive_entities": [],
            "active_scope_with_inactive_entities": [],
            "encounters_with_inactive_entities": [],
            "live_identity_decisions_with_inactive_entities": [],
            "maturity_assessments_with_inactive_entities": [],
            "cohorts_with_inactive_entities": [],
            "entities_missing_pages": [],
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
    assert sources[0]["status"] == "active"
    assert source["segments"][0]["content"] == "I prefer tea."
    assert source["segment_accounting"] == {
        "source-test#seg-0001": "claimed",
    }
    assert episode_summaries[0]["claim_count"] == 2
    assert "claim_ids" not in episode_summaries[0]
    assert episode["claim_ids"] == ["claim-test", "claim-old"]
    assert {item["claim_id"] for item in claim_summaries} == {
        "claim-old", "claim-test",
    }
    assert "provenance" not in claim_summaries[0]
    assert claim["provenance"][0]["segment_ids"] == ["source-test#seg-0001"]
    assert claim["facts"][0]["fact_id"] == "fact-tea-preference"
    assert claim["scope_decisions"] == []
    assert claim["entity_references"] == []
    assert dream_run_summaries == []
    assert facts[0]["fact_id"] == "fact-tea-preference"
    assert facts[0]["member_claim_count"] == 1
    assert "member_claim_ids" not in facts[0]
    assert fact["claims"][0]["claim_id"] == "claim-test"
    assert fact["owner"]["entity_id"] == "you"
    assert entity["facts"][0]["fact_id"] == "fact-tea-preference"
    assert {item["claim_id"] for item in entity["placements"]} == {
        "claim-old", "claim-test",
    }
    assert proposals[0]["proposal_id"] == "recon-test"
    assert organization_proposals[0]["proposal_id"] == "organization-test"
    assert overview["reconsolidation_proposals"] == {"pending": 1}
    assert overview["organization_proposals"] == {"pending": 1}
    assert files["wiki_index"]["filename"] == "_index.md"
    assert "content" not in files["wiki_index"]
    assert files["wiki_index"]["size"] > 0
    assert [item["filename"] for item in files["archived_pages"]] == ["archived-page.md"]
    assert wiki_index["filename"] == "_index.md"
    assert wiki_index["content"]


@pytest.mark.asyncio
async def test_artifact_detail_endpoints_return_404(artifact_memory):
    for loader, artifact_id in (
        (memory_artifacts.get_artifact_source, "source-missing"),
        (memory_artifacts.get_artifact_episode, "episode-missing"),
        (memory_artifacts.get_artifact_claim, "claim-missing"),
        (memory_artifacts.get_consolidated_fact, "fact-missing"),
        (memory_artifacts.get_artifact_entity, "entity-missing"),
        (memory_artifacts.get_artifact_dream_run, "dream-missing"),
        (memory_artifacts.get_reconsolidation_proposal, "recon-missing"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await loader(artifact_id)
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_proposal_endpoint_applies_immediately(artifact_memory):
    response = await memory_curation.reject_reconsolidation_proposal(
        "recon-test",
        ProposalReviewRequest(reviewer_note="Both statements remain relevant."),
    )

    assert response["proposal"]["status"] == "rejected"
    assert response["proposal"]["reviewer_note"] == "Both statements remain relevant."
    assert artifact_memory.artifacts.get_claim("claim-test").status == "active"
    assert artifact_memory.artifacts.get_claim("claim-old").status == "active"


@pytest.mark.asyncio
async def test_review_proposal_endpoint_returns_404(artifact_memory):
    with pytest.raises(HTTPException) as exc_info:
        await memory_curation.approve_reconsolidation_proposal(
            "recon-missing", ProposalReviewRequest()
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_correct_claim_endpoint_creates_replacement_artifacts(artifact_memory):
    artifact_memory.dream_process.fact_resolver.resolve = AsyncMock(
        return_value=FactResolutionResult(deleted_fact_ids={"fact-tea-preference"})
    )

    response = await memory_curation.correct_claim(
        "claim-test",
        ClaimCorrectionRequest(
            text="The user prefers herbal tea.",
            reason="The original claim omitted the kind of tea.",
        ),
    )

    replacement = artifact_memory.artifacts.get_claim(response["claim_ids"][0])
    assert replacement.text == "The user prefers herbal tea."
    assert artifact_memory.artifacts.get_claim("claim-test").status == "superseded"
    assert artifact_memory.artifacts.get_source(
        response["source_ids"][0]
    ).source_type == "manual_correction"


@pytest.mark.asyncio
async def test_retract_source_endpoint_marks_source_and_claims(artifact_memory):
    artifact_memory.dream_process.fact_resolver.resolve = AsyncMock(
        return_value=FactResolutionResult(deleted_fact_ids={"fact-tea-preference"})
    )

    response = await memory_curation.retract_source(
        "source-test",
        SourceRetractionRequest(reason="The imported chat was not authentic."),
    )

    assert set(response["claim_ids"]) == {"claim-test", "claim-old"}
    assert artifact_memory.artifacts.get_source("source-test").status == "retracted"
    assert artifact_memory.artifacts.get_claim("claim-test").status == "retracted"


@pytest.mark.asyncio
async def test_identity_review_approves_reopens_and_reroutes(
    artifact_memory, monkeypatch
):
    reroute = AsyncMock(return_value={"failures": [], "pages_created": 0})
    monkeypatch.setattr(memory_curation, "run_dream_process", reroute)

    response = await memory_curation.review_identity_decision(
        "identity-review-test",
        "approve",
        IdentityReviewRequest(reviewer_note="This is a continuing project."),
    )

    decision = response["decision"]
    assert decision["review_state"] == "accepted"
    assert decision["entity_id"] == "project-tea-journal"
    assert artifact_memory.artifacts.get_claim(
        "claim-test"
    ).dream_disposition == "pending"
    references = artifact_memory.artifacts.list_entity_references(
        claim_id="claim-test", status="active"
    )
    assert any(
        item.role == "identity_subject"
        and item.entity_id == "project-tea-journal"
        and item.origin == "manual"
        for item in references
    )
    reroute.assert_awaited_once()
