from dataclasses import replace
from types import SimpleNamespace

import pytest

from benchmarks.suites.daily_driver.run import _approve_proposal, _retract_source
from mycelium.artifacts import ClaimProvenance, ReconsolidationProposal
from tests.test_claim_lifecycle import NOW, add_claim, add_source, setup_service


def memory_and_fixture(tmp_path):
    artifacts, wiki, service = setup_service(tmp_path)
    memory = SimpleNamespace(artifacts=artifacts, consolidator=SimpleNamespace(
        materializer=service.materializer, views=service.views))
    for source_id, label in [("old", "old-evidence"), ("new", "new-evidence"), ("other", "other-evidence")]:
        add_source(artifacts, source_id)
        source = artifacts.get_source(source_id)
        source.metadata["fixture_source_id"] = f"fixture-{source_id}"
        source.segments[0].metadata["fixture_segment_id"] = label
        artifacts.save_source(source)
    for cid, sid in [("old-1", "old"), ("old-2", "old"), ("new", "new"), ("other", "other")]:
        add_claim(artifacts, cid, [ClaimProvenance(sid, [f"{sid}#seg-0001"])], with_fact=True)
    proposal = ReconsolidationProposal(
        proposal_id="proposal", incoming_claim_ids=["new"], target_claim_ids=["old-1", "old-2"],
        proposed_relation="supersedes", explanation="Explicit change", confidence=1.0,
        dream_run_id="test", created_at=NOW, affected_entity_ids=["you"],
    )
    artifacts.save_reconsolidation_proposal(proposal)
    fixture = {"gold_checkpoints": {"checkpoints": [{"reconciliation": [{
        "id": "change", "incoming_claim": "gold-new", "target_claim": "gold-old", "relation": "supersedes",
    }]}]}, "gold_claims": {"claims": [
        {"id": "gold-new", "evidence": ["new-evidence"]},
        {"id": "gold-old", "evidence": ["old-evidence"]},
    ]}}
    return memory, wiki, fixture, proposal


@pytest.mark.asyncio
async def test_daily_approval_awaits_production_review_for_all_proposal_members(tmp_path):
    memory, _, fixture, _ = memory_and_fixture(tmp_path)
    result = await _approve_proposal(memory, fixture, "change")
    assert result["proposal"]["status"] == "applied"
    assert result["proposal"]["target_claim_ids"] == ["old-1", "old-2"]
    assert all(memory.artifacts.get_claim(cid).status == "superseded" for cid in ["old-1", "old-2"])
    assert memory.artifacts.get_claim("new").status == "active"
    assert memory.artifacts.get_claim("other").status == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"target_claim_ids": ["old-1", "other"]},
    {"incoming_claim_ids": ["new", "other"]},
    {"proposed_relation": "contradicts"},
])
async def test_daily_approval_cannot_authorize_unmatched_members_or_relation(tmp_path, change):
    memory, _, fixture, proposal = memory_and_fixture(tmp_path)
    memory.artifacts.save_reconsolidation_proposal(replace(proposal, **change))
    with pytest.raises(RuntimeError, match="found 0"):
        await _approve_proposal(memory, fixture, "change")
    assert memory.artifacts.get_claim("old-1").status == "active"
    assert memory.artifacts.get_reconsolidation_proposal("proposal").status == "pending"


@pytest.mark.asyncio
async def test_daily_approval_reports_ambiguous_proposals_without_mutation(tmp_path):
    memory, _, fixture, proposal = memory_and_fixture(tmp_path)
    memory.artifacts.save_reconsolidation_proposal(replace(proposal, proposal_id="second"))
    with pytest.raises(RuntimeError, match="found 2"):
        await _approve_proposal(memory, fixture, "change")
    assert memory.artifacts.get_claim("old-1").status == "active"


@pytest.mark.asyncio
async def test_daily_retraction_uses_exact_source_binding_and_production_lifecycle(tmp_path):
    memory, wiki, _, _ = memory_and_fixture(tmp_path)
    # Retraction invalidates the pending proposal and preserves independently supported claims.
    result = await _retract_source(memory, "fixture-old")
    assert result["source_ids"] == ["old"]
    assert result["claim_ids"] == ["old-1", "old-2"]
    assert memory.artifacts.get_source("old").status == "retracted"
    assert memory.artifacts.get_claim("new").status == "active"
    assert memory.artifacts.get_claim("other").status == "active"
    assert memory.artifacts.facts_for_claim("old-1")  # Hidden views remain inspectable.
    assert all("old-1" not in item.get("claim_ids", []) for page in memory.consolidator.materializer.wiki.list_all() for section in page.sections for item in section["items"])
    assert memory.artifacts.get_reconsolidation_proposal("proposal").status == "stale"
    assert wiki.get("you") is not None


@pytest.mark.asyncio
async def test_daily_retraction_rejects_missing_or_ambiguous_source_binding(tmp_path):
    memory, _, _, _ = memory_and_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="found 0"):
        await _retract_source(memory, "missing")
    source = memory.artifacts.get_source("other")
    source.metadata["fixture_source_id"] = "fixture-old"
    memory.artifacts.save_source(source)
    with pytest.raises(RuntimeError, match="found 2"):
        await _retract_source(memory, "fixture-old")
    assert memory.artifacts.get_source("old").status == "active"
