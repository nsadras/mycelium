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
from mycelium.facts import FactResolutionResult, FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.reconsolidation import ReconsolidationReviewService
from mycelium.store import WikiStore


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
        item.claim_id,
        "you",
        "preferences_working_style",
        [],
        "placed",
        "test",
        item.recorded_at,
        item.recorded_at,
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


@pytest.mark.asyncio
async def test_owner_plan_groups_independent_support(tmp_path):
    artifacts = setup_owner(tmp_path)
    first = claim("first", "The user prefers written updates.", "2026-08-01T12:00:00")
    second = claim("second", "Written updates are preferred.", "2026-08-02T12:00:00")
    placements = [place(artifacts, first), place(artifacts, second)]
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "assignments": {"C001": {"fact_key": "updates"}, "C002": {"fact_key": "updates"}},
        "facts": [{
            "fact_key": "updates",
            "state": "current",
            "section_key": "preferences_working_style",
            "text": "The user prefers written updates.",
            "confidence": 0.95,
            "reason": "Independent support.",
        }],
        "truth_changes": [],
    }

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"first", "second"},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert len(result.facts) == 1
    assert result.facts[0].member_claim_ids == ["first", "second"]
    assert result.proposals == []


@pytest.mark.asyncio
async def test_grouped_project_roles_preserve_each_claims_exact_project_link(tmp_path):
    artifacts = setup_owner(tmp_path)
    person = artifacts.create_entity("person", "Rosa")
    first_project = artifacts.create_entity("project", "Kitchen")
    second_project = artifacts.create_entity("project", "Garden")
    first = claim("first", "Rosa coordinates permits for Kitchen.", "2026-08-01T12:00:00")
    second = claim("second", "Rosa coordinates permits for Garden.", "2026-08-02T12:00:00")
    placements = []
    for item, project in ((first, first_project), (second, second_project)):
        artifacts.save_claim(item)
        placement = ClaimPlacement(
            item.claim_id,
            person.entity_id,
            "shared_projects",
            [project.entity_id],
            "placed",
            "test",
            item.recorded_at,
            item.recorded_at,
            relationship_kind="project_role",
        )
        artifacts.save_placement(placement)
        placements.append(placement)
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "assignments": {
            "C001": {"fact_key": "coordination"},
            "C002": {"fact_key": "coordination"},
        },
        "facts": [{
            "fact_key": "coordination",
            "state": "current",
            "section_key": "shared_projects",
            "text": "Rosa coordinates permits for two projects.",
            "confidence": 0.9,
            "reason": "Related responsibilities.",
        }],
        "truth_changes": [],
    }

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={person.entity_id},
        incoming_claim_ids={first.claim_id, second.claim_id},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    links = {
        placement.claim_id: placement.linked_entity_ids
        for placement in result.placements
    }
    assert links == {
        "first": [first_project.entity_id],
        "second": [second_project.entity_id],
    }


@pytest.mark.asyncio
async def test_truth_change_preserves_accepted_fact_and_withholds_incoming(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers tea.", "2026-08-01T12:00:00")
    new = claim("new", "The user now prefers coffee.", "2026-08-05T12:00:00")
    placements = [place(artifacts, old), place(artifacts, new)]
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "assignments": {"C001": {"fact_key": "old"}, "C002": {"fact_key": "new"}},
        "facts": [
            {"fact_key": "old", "state": "current", "section_key": "preferences_working_style", "text": old.text, "confidence": 0.9, "reason": "Accepted state."},
            {"fact_key": "new", "state": "current", "section_key": "preferences_working_style", "text": new.text, "confidence": 0.9, "reason": "Proposed replacement."},
        ],
        "truth_changes": [{
            "relation": "supersedes",
            "incoming_claim_aliases": ["C002"],
            "target_claim_aliases": ["C001"],
            "explanation": "The newer statement explicitly replaces the old preference.",
            "confidence": 0.92,
        }],
    }

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"new"},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert [item.fact_id for item in result.facts] == [old_fact.fact_id]
    assert len(result.proposals) == 1
    assert result.proposals[0].incoming_claim_ids == ["new"]
    assert result.proposals[0].target_claim_ids == ["old"]
    assert next(item for item in result.placements if item.claim_id == "new").section_key == "needs_review"


@pytest.mark.asyncio
async def test_invalid_plan_fails_closed_and_preserves_prior_fact(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers tea.", "2026-08-01T12:00:00")
    new = claim("new", "The user now prefers coffee.", "2026-08-05T12:00:00")
    placements = [place(artifacts, old), place(artifacts, new)]
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "assignments": {"C001": {"fact_key": "same"}, "C002": {"fact_key": "same"}},
        "facts": [{"fact_key": "same", "state": "current", "section_key": "preferences_working_style", "text": "The user has conflicting drink preferences.", "confidence": 0.5, "reason": "Invalid grouping."}],
        "truth_changes": [{"relation": "supersedes", "incoming_claim_aliases": ["C002"], "target_claim_aliases": ["C001"], "explanation": "Replacement.", "confidence": 0.9}],
    }

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"new"},
        dream_run_id="dream-1",
    )

    assert len(result.failures) == 1
    assert result.facts == [old_fact]
    assert result.deleted_fact_ids == set()
    assert result.proposals == []


@pytest.mark.asyncio
async def test_approve_supersession_mutates_claims_and_reruns_resolver(tmp_path):
    artifacts = setup_owner(tmp_path)
    wiki = WikiStore(tmp_path / "wiki")
    old = claim("old", "The user prefers tea.", "2026-08-01T12:00:00")
    new = claim("new", "The user prefers coffee.", "2026-08-05T12:00:00")
    place(artifacts, old)
    place(artifacts, new)
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    proposal = ReconsolidationProposal(
        proposal_id="recon-1",
        incoming_claim_ids=["new"],
        target_claim_ids=["old"],
        proposed_relation="supersedes",
        explanation="The preference changed.",
        confidence=0.9,
        dream_run_id="dream-1",
        created_at=datetime.now().astimezone().isoformat(),
        affected_entity_ids=["you"],
    )
    artifacts.save_reconsolidation_proposal(proposal)
    new_fact = fact(new)
    resolver = AsyncMock()
    resolver.resolve.return_value = FactResolutionResult(
        facts=[new_fact], deleted_fact_ids={old_fact.fact_id}
    )
    service = ReconsolidationReviewService(
        artifacts,
        PageMaterializer(wiki, artifacts, Config.defaults()),
        resolver,
    )

    result = await service.approve("recon-1", reviewer_note="Confirmed")

    assert result.proposal.status == "applied"
    assert artifacts.get_claim("old").status == "superseded"
    assert artifacts.get_claim("new").links == [{"relation": "supersedes", "target": "old"}]
    assert {item.fact_id for item in artifacts.list_consolidated_facts()} == {"fact-new"}
    resolver.resolve.assert_awaited_once()
