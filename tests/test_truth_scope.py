import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from benchmarks.shared.adapters import OllamaQaClient
from mycelium.artifacts import ClaimPlacement, SourceDocument, SourceSegment
from mycelium.config import LLMConfig
from mycelium.facts import FactResolver
from mycelium.truth_contract import TruthComparison, truth_candidates_model, truth_comparison_model
from mycelium.truth_review import TruthReviewer
from tests.memory_helpers import claim, fact, setup_owner


def fixture(tmp_path, *, same_batch=False):
    artifacts = setup_owner(tmp_path)
    entities = {e.entity_id: e for e in (
        artifacts.create_entity("person", "Mara"),
        artifacts.create_entity("project", "Draft"),
    )}
    left = claim("left", "Mara will deliver the draft Friday.", "2031-01-01")
    right = claim("right", "Mara corrected the draft delivery: Monday replaces Friday.", "2031-01-02")
    placements = {}
    for item, owner in ((left, "project-draft"), (right, "person-mara")):
        source_id = item.provenance[0].source_id
        segment_id = item.provenance[0].segment_ids[0]
        artifacts.save_source(SourceDocument(
            source_id, "agent_conversation", source_id, item.recorded_at, item.recorded_at, ["Mara"],
            [SourceSegment(segment_id, 0, item.text, "Mara", "user", item.recorded_at)],
        ))
        artifacts.save_claim(item)
        placement = ClaimPlacement(item.claim_id, entities[owner].entity_id,
                                   "goals_plans" if owner == "person-mara" else "overview", [], "placed", "Test placement",
                                   item.recorded_at, item.recorded_at)
        artifacts.save_placement(placement)
        placements[item.claim_id] = placement
    if not same_batch:
        artifacts.save_consolidated_fact(replace(fact(left), owner_entity_id=entities["project-draft"].entity_id,
                                                  section_key="overview"))
    llm = OllamaQaClient("test", "http://localhost:11434", llm_config=LLMConfig(reasoning_enabled=False)).llm

    async def respond(system, user, schema, **kwargs):
        if kwargs["debug_label"] == "dream-truth-candidates":
            payload = json.loads(user.split("\n", 1)[1])
            return {"decisions": {alias: {
                "candidates": {target: "compare" for target in payload["eligible_candidates"][alias]},
                "reason": "Test-selected comparison",
            } for alias, incoming in payload["incoming"].items()}}
        if kwargs["debug_label"] == "dream-truth-comparison":
            return {"comparisons": {alias: {"scope": "same", "relation": "right_supersedes_left",
                                            "reason": "Explicit replacement"}
                                    for alias in schema.model_fields["comparisons"].annotation.model_fields}}
        raise AssertionError(f"Unexpected call: {kwargs['debug_label']}")

    llm.call_structured = AsyncMock(side_effect=respond)
    return artifacts, llm, placements, entities


def test_truth_pairs_require_complete_accounting_and_same_scope_for_changes():
    schema = truth_comparison_model(["P001", "P002"])
    decision = {"scope": "same", "relation": "contradicts", "reason": "Incompatible values"}
    assert schema.model_validate({"comparisons": {"P001": decision, "P002": decision}})
    with pytest.raises(ValidationError):
        schema.model_validate({"comparisons": {"P001": decision}})
    for scope in ("distinct", "unresolved"):
        with pytest.raises(ValidationError, match="same scope"):
            TruthComparison(scope=scope, relation="right_supersedes_left", reason="Test")


def test_candidate_contract_excludes_self_and_requires_every_eligible_decision():
    schema = truth_candidates_model({"C1": ["X2", "X3"], "C2": ["X1", "X3"]})
    response = {"decisions": {
        "C1": {"candidates": {"X2": "compare", "X3": "unrelated"}, "reason": "Test"},
        "C2": {"candidates": {"X1": "compare", "X3": "uncertain"}, "reason": "Test"},
    }}
    schema.model_validate(response)
    response["decisions"]["C1"]["candidates"]["X1"] = "compare"
    with pytest.raises(ValidationError):
        schema.model_validate(response)
    del response["decisions"]["C1"]["candidates"]["X1"]
    del response["decisions"]["C2"]["candidates"]["X3"]
    with pytest.raises(ValidationError):
        schema.model_validate(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("same_batch", [False, True])
async def test_truth_comparison_crosses_owners_and_incoming_batch_boundaries(tmp_path, same_batch):
    artifacts, llm, placements, entities = fixture(tmp_path, same_batch=same_batch)
    incoming = {"left", "right"} if same_batch else {"right"}
    result = await TruthReviewer(llm, artifacts).review(incoming, placements, entities, dream_run_id="test")
    assert not result.errors
    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert proposal.incoming_claim_ids == ["right"]
    assert proposal.target_claim_ids == ["left"]
    assert proposal.proposed_relation == "supersedes"
    assert set(proposal.affected_entity_ids) == {e.entity_id for e in entities.values()}
    assert artifacts.get_claim("left").status == "active"
    comparisons = [call for call in llm.call_structured.call_args_list
                   if call.kwargs["debug_label"] == "dream-truth-comparison"]
    assert len(comparisons) == 1  # A same-batch pair is compared once, not in both directions.
    artifacts.save_reconsolidation_proposal(proposal)
    llm.call_structured.reset_mock()
    repeated = await TruthReviewer(llm, artifacts).review(incoming, placements, entities, dream_run_id="again")
    assert repeated.proposals == []
    assert all(call.kwargs["debug_label"] != "dream-truth-comparison" for call in llm.call_structured.call_args_list)


@pytest.mark.asyncio
async def test_corrupt_provenance_is_explicit_and_blocks_new_review(tmp_path):
    artifacts, llm, placements, entities = fixture(tmp_path)
    source = artifacts.get_source("source-left")
    source.segments = []
    artifacts.save_source(source)
    result = await TruthReviewer(llm, artifacts).review({"right"}, placements, entities, dream_run_id="test")
    assert result.failure_claim_ids == {"right"}
    assert result.errors and result.proposals == []
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_fact_resolution_runs_global_truth_before_single_owner_projection(tmp_path):
    artifacts, llm, placements, entities = fixture(tmp_path)
    result = await FactResolver(llm, artifacts).resolve(
        [placements["right"]], affected_entity_ids={entities["person-mara"].entity_id},
        incoming_claim_ids={"right"}, dream_run_id="test",
    )
    assert not result.failures
    assert len(result.proposals) == 1
    assert {cid for item in result.facts for cid in item.member_claim_ids} >= {"right"}
    assert artifacts.get_claim("left").status == "active"


@pytest.mark.asyncio
async def test_failed_global_review_keeps_prior_facts_and_additions_retryable(tmp_path):
    artifacts, llm, placements, entities = fixture(tmp_path)
    llm.call_structured.side_effect = ValueError("Injected invalid decision")
    prior = artifacts.list_consolidated_facts()
    result = await FactResolver(llm, artifacts).resolve(list(placements.values()),
        affected_entity_ids=set(entities), incoming_claim_ids={"right"}, dream_run_id="test")
    assert result.facts == prior
    assert not result.proposals and not result.deleted_fact_ids and not result.placements
    assert result.failures[0].partial and result.failures[0].claim_ids == ["right"]
    assert artifacts.get_claim("left").status == "active"


@pytest.mark.asyncio
async def test_global_truth_review_includes_unplaced_claims(tmp_path):
    artifacts, llm, placements, entities = fixture(tmp_path)
    placements["right"] = replace(placements["right"], owner_entity_id=None, section_key=None,
                                  status="deferred")
    artifacts.save_placement(placements["right"])
    result = await FactResolver(llm, artifacts).resolve([], affected_entity_ids=set(),
        incoming_claim_ids={"right"}, dream_run_id="test")
    assert not result.failures and len(result.proposals) == 1
    assert result.proposals[0].affected_entity_ids == ["project-draft"]
    assert artifacts.placement_for_claim("right").status == "deferred"


@pytest.mark.asyncio
@pytest.mark.parametrize("persisted", [False, True])
async def test_source_only_statements_cannot_trigger_or_influence_truth_review(tmp_path, persisted):
    artifacts, llm, placements, entities = fixture(tmp_path)
    excluded = artifacts.get_claim("left")
    if persisted:
        excluded.dream_disposition = "excluded_source_policy"
        artifacts.save_claim(excluded)
    exclusions = frozenset() if persisted else frozenset({"left"})
    # Broken provenance in excluded source history must not block canonical work.
    source = artifacts.get_source("source-left")
    source.segments = []
    artifacts.save_source(source)
    for incoming in ({"left"}, {"right"}, {"left", "right"}):
        result = await TruthReviewer(llm, artifacts).review(
            incoming, placements, entities, dream_run_id="test", excluded_claim_ids=exclusions)
        assert not result.errors and not result.proposals
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_fact_resolution_passes_current_build_exclusions_to_truth_review(tmp_path):
    artifacts, llm, placements, entities = fixture(tmp_path)
    # Keep only the admitted destination. The excluded active claim has not yet
    # received the source-only disposition that Dream commits at the end.
    result = await FactResolver(llm, artifacts).resolve(
        [placements["right"]], affected_entity_ids={"person-mara"},
        incoming_claim_ids={"left", "right"}, dream_run_id="test",
        excluded_claim_ids=frozenset({"left"}),
    )
    assert not result.proposals and not result.failures
    assert {cid for fact in result.facts for cid in fact.member_claim_ids} == {"right"}
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_approval_invalidates_overlapping_reviews_atomically(tmp_path):
    from mycelium.artifacts import ReconsolidationProposal
    from mycelium.config import Config
    from mycelium.materialization import PageMaterializer
    from mycelium.reconsolidation import ReconsolidationReviewService, ReviewConflictError
    from mycelium.store import WikiStore
    artifacts, llm, placements, entities = fixture(tmp_path)
    result = await FactResolver(llm, artifacts).resolve(list(placements.values()),
        affected_entity_ids=set(entities), incoming_claim_ids={"right"}, dream_run_id="test")
    proposal = result.proposals[0]
    artifacts.save_reconsolidation_proposal(proposal)
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="other-review", incoming_claim_ids=["right"], target_claim_ids=["left"],
        proposed_relation="contradicts", explanation="Competing review", confidence=.9,
        dream_run_id="test", created_at="2031-01-02", affected_entity_ids=list(entities),
    ))
    for item in result.facts:
        artifacts.save_consolidated_fact(item)
    service = ReconsolidationReviewService(artifacts,
        PageMaterializer(WikiStore(tmp_path / "wiki"), artifacts, Config.defaults()), FactResolver(llm, artifacts))
    await service.approve(proposal.proposal_id)
    assert artifacts.get_claim("left").status == "superseded"
    assert artifacts.get_reconsolidation_proposal("other-review").status == "stale"
    assert not artifacts.list_reconsolidation_proposals(status="pending")
    assert {cid for f in artifacts.list_consolidated_facts() for cid in f.member_claim_ids} == {"right"}
    with pytest.raises(ReviewConflictError, match="stale"):
        await service.approve("other-review")
