from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    ConsolidatedFact,
    MemoryClaim,
    ReconsolidationProposal,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimRoute
from mycelium.materialization import PageMaterializer
from mycelium.reconsolidation import (
    ClaimReconsolidator,
    ReconsolidationReviewService,
    ReviewConflictError,
)
from mycelium.store import WikiStore


def claim(
    claim_id: str,
    text: str,
    *,
    page: str = "user-profile",
    slot: str | None = "favorite_drink",
    recorded_at: str = "2026-08-01T12:00:00",
) -> MemoryClaim:
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        about=[{"entity": "user"}],
        provenance=[ClaimProvenance(
            source_id=f"source-{claim_id}",
            segment_ids=[f"source-{claim_id}#seg-0001"],
            raw_log_entry_id=f"2026-08-01#session-{claim_id}",
            speaker="user",
        )],
        recorded_at=recorded_at,
        slot=slot,
        claim_type="preference",
        predicate="prefers",
    )


def temporal_claim(
    claim_id: str,
    date: str,
    *,
    role: str = "deadline",
    page: str = "project-alpha",
) -> MemoryClaim:
    item = claim(
        claim_id,
        "The user will send the report.",
        page=page,
        slot="report_deadline",
    )
    item.claim_type = "commitment"
    item.predicate = "send_report"
    item.facets = {"temporal": {
        "expression": date,
        "role": role,
        "status": "resolved",
        "certainty": "exact",
        "start": date,
        "end": date,
    }}
    return item


def test_reconsolidation_candidates_do_not_mix_deadline_and_event_time(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    incoming = temporal_claim("incoming", "2026-08-20", page="")
    old_deadline = temporal_claim("old-deadline", "2026-08-15")
    event = temporal_claim("event", "2026-08-20", role="event_time")
    reconsolidator = ClaimReconsolidator(AsyncMock(), artifacts)

    candidates = reconsolidator._candidates(
        incoming, "project-alpha", [event, old_deadline]
    )

    assert [candidate.claim_id for candidate in candidates] == ["old-deadline"]


@pytest.mark.asyncio
async def test_contradiction_creates_durable_review_proposal(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    target = claim("old", "The user prefers tea.")
    incoming = claim(
        "new", "The user dislikes tea.", page="", recorded_at="2026-08-05T12:00:00"
    )
    artifacts.save_claim(target)
    artifacts.save_claim(incoming)
    llm = AsyncMock()
    llm.call_structured.return_value = {"decisions": [{
        "incoming_alias": "N001",
        "relation": "contradicts",
        "target_alias": "E001",
        "explanation": "The preferences conflict.",
        "confidence": 0.91,
    }]}

    result = await ClaimReconsolidator(llm, artifacts).analyze(
        [ClaimRoute("new", "you", "preferences_working_style", (), "2026-08-05#session-new", "test")],
        current_claim_ids={"new"},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert len(result.proposals) == 1
    assert result.proposals[0].target_claim_id == "old"
    assert result.proposals[0].proposed_relation == "contradicts"
    assert artifacts.get_claim("old").status == "active"
    assert artifacts.get_claim("new").status == "active"


@pytest.mark.asyncio
async def test_support_is_safe_automatic_relation(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.save_claim(claim("old", "The user prefers tea."))
    artifacts.save_claim(claim("new", "Tea is the user's preferred drink.", page=""))
    llm = AsyncMock()
    llm.call_structured.return_value = {"decisions": [{
        "incoming_alias": "N001",
        "relation": "supports",
        "target_alias": "E001",
        "explanation": "Independent support.",
        "confidence": 0.88,
    }]}

    result = await ClaimReconsolidator(llm, artifacts).analyze(
        [ClaimRoute("new", "you", "preferences_working_style", (), "log-new", "test")],
        current_claim_ids={"new"},
        dream_run_id="dream-1",
    )

    assert [(item.incoming_claim_id, item.target_claim_id) for item in result.supporting_relations] == [("new", "old")]
    assert result.proposals == []


def review_setup(tmp_path, relation: str):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    target = claim("old", "The user prefers tea.")
    incoming = claim("new", "The user prefers coffee.")
    artifacts.save_claim(target)
    artifacts.save_claim(incoming)
    artifacts.create_entity("you", "You")
    for item in (target, incoming):
        artifacts.save_placement(ClaimPlacement(
            item.claim_id, "you", "preferences_working_style", [], "placed", "test",
            "2026-08-01T12:00:00", "2026-08-01T12:00:00",
        ))
        artifacts.save_consolidated_fact(ConsolidatedFact(
            fact_id=f"fact-{item.claim_id}", text=item.text,
            member_claim_ids=[item.claim_id], owner_entity_id="you",
            section_key="preferences_working_style", linked_entity_ids=[],
            synthesis_origin="claim", confidence=item.confidence,
            reason="test", created_at="2026-08-01T12:00:00",
            updated_at="2026-08-01T12:00:00",
        ))
    materializer = PageMaterializer(wiki, artifacts, Config.defaults())
    materializer.regenerate({"you"})
    proposal = ReconsolidationProposal(
        proposal_id="recon-1",
        incoming_claim_id="new",
        target_claim_id="old",
        proposed_relation=relation,
        explanation="The newer preference may replace the old one.",
        confidence=0.9,
        dream_run_id="dream-1",
        created_at=datetime.now().astimezone().isoformat(),
        affected_entity_ids=["you"],
    )
    artifacts.save_reconsolidation_proposal(proposal)
    materializer.regenerate({"you"})
    return artifacts, wiki, ReconsolidationReviewService(artifacts, materializer)


def test_approve_supersession_updates_claims_and_projection(tmp_path):
    artifacts, wiki, service = review_setup(tmp_path, "supersedes")
    assert "pending reconciliation" in wiki.get("you").content

    result = service.approve("recon-1", reviewer_note="Confirmed by user")

    assert result.proposal.status == "applied"
    assert artifacts.get_claim("old").status == "superseded"
    assert artifacts.get_claim("new").links == [{"relation": "supersedes", "target": "old"}]
    assert {fact.fact_id for fact in artifacts.list_consolidated_facts()} == {"fact-new"}
    page = wiki.get("you")
    assert "prefers coffee" in page.content
    assert "prefers tea" not in page.content
    assert "pending reconciliation" not in page.content
    assert service.approve("recon-1").proposal.status == "applied"


def test_approve_supersession_splits_remaining_members_from_grouped_fact(tmp_path):
    artifacts, wiki, service = review_setup(tmp_path, "supersedes")
    other = claim("other", "The user prefers herbal tea.")
    artifacts.save_claim(other)
    artifacts.save_placement(ClaimPlacement(
        other.claim_id, "you", "preferences_working_style", [], "placed", "test",
        "2026-08-01T12:00:00", "2026-08-01T12:00:00",
    ))
    artifacts.delete_consolidated_fact("fact-old")
    artifacts.save_consolidated_fact(ConsolidatedFact(
        fact_id="grouped-old-and-other",
        text="The user prefers tea, especially herbal tea.",
        member_claim_ids=["old", "other"],
        owner_entity_id="you",
        section_key="preferences_working_style",
        linked_entity_ids=[],
        synthesis_origin="model",
        confidence=0.8,
        reason="test grouping",
        created_at="2026-08-01T12:00:00",
        updated_at="2026-08-01T12:00:00",
    ))
    service.materializer.regenerate({"you"})

    service.approve("recon-1")

    facts = artifacts.list_consolidated_facts()
    assert "grouped-old-and-other" not in {fact.fact_id for fact in facts}
    assert any(fact.member_claim_ids == ["other"] for fact in facts)
    assert all("old" not in fact.member_claim_ids for fact in facts)
    page = wiki.get("you").content
    assert "prefers herbal tea" in page
    assert "prefers tea, especially herbal tea" not in page


def test_approve_deadline_supersession_reprojects_only_new_due_date(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    old = temporal_claim("old", "2026-08-15")
    incoming = temporal_claim("incoming", "2026-08-20")
    artifacts.save_claim(old)
    artifacts.save_claim(incoming)
    project = artifacts.create_entity("project", "Project Alpha")
    for item in (old, incoming):
        artifacts.save_placement(ClaimPlacement(
            item.claim_id, project.entity_id, "next_steps_deadlines", [], "placed", "test",
            "2026-08-01T12:00:00", "2026-08-01T12:00:00",
        ))
        due = item.facets["temporal"]["start"]
        artifacts.save_consolidated_fact(ConsolidatedFact(
            fact_id=f"fact-{item.claim_id}",
            text=f"The user will send the report. (deadline: {due})",
            member_claim_ids=[item.claim_id], owner_entity_id=project.entity_id,
            section_key="next_steps_deadlines", linked_entity_ids=[],
            synthesis_origin="claim", confidence=item.confidence,
            reason="test", created_at="2026-08-01T12:00:00",
            updated_at="2026-08-01T12:00:00",
        ))
    materializer = PageMaterializer(wiki, artifacts, Config.defaults())
    materializer.regenerate({project.entity_id})
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="deadline-change",
        incoming_claim_id="incoming",
        target_claim_id="old",
        proposed_relation="supersedes",
        explanation="The deadline moved.",
        confidence=0.95,
        dream_run_id="dream-1",
        created_at=datetime.now().astimezone().isoformat(),
        affected_entity_ids=[project.entity_id],
    ))
    service = ReconsolidationReviewService(artifacts, materializer)

    service.approve("deadline-change")

    content = wiki.get("project-alpha").content
    assert "deadline: 2026-08-20" in content
    assert "deadline: 2026-08-15" not in content
    assert artifacts.get_claim("old").status == "superseded"
    assert {fact.fact_id for fact in artifacts.list_consolidated_facts()} == {
        "fact-incoming"
    }


def test_reject_leaves_claims_active_and_removes_pending_annotation(tmp_path):
    artifacts, wiki, service = review_setup(tmp_path, "contradicts")

    result = service.reject("recon-1")

    assert result.proposal.status == "rejected"
    assert artifacts.get_claim("old").status == "active"
    assert artifacts.get_claim("new").status == "active"
    assert "pending reconciliation" not in wiki.get("you").content
    with pytest.raises(ReviewConflictError):
        service.approve("recon-1")
