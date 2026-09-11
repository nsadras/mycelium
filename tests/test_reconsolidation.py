import json
from datetime import datetime
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.artifacts import (
    ClaimPlacement,
    ReconsolidationProposal,
    SourceDocument,
    SourceSegment,
)
from mycelium.config import Config
from mycelium.facts import FactResolutionResult, FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.reconsolidation import ReconsolidationReviewService
from mycelium.store import WikiStore
from mycelium.structured_outputs import (
    fact_candidate_selection_output_model,
    fact_truth_output_model,
)
from tests.memory_helpers import claim, fact, place, setup_owner


def test_coverage_distinguishes_review_holdback_from_missing_presentation(tmp_path):
    artifacts = setup_owner(tmp_path)
    items = {key: claim(key, f"Statement {key}.", "2026-08-01T12:00:00")
             for key in ("accepted", "pending", "gap", "unplaced")}
    for key, item in items.items():
        if key == "unplaced":
            artifacts.save_claim(item)
        else:
            place(artifacts, item)
    artifacts.save_consolidated_fact(fact(items["accepted"]))
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="review", incoming_claim_ids=["pending"], target_claim_ids=["accepted"],
        proposed_relation="supersedes", explanation="Awaiting review.", confidence=0.9,
        dream_run_id="test", created_at=items["accepted"].recorded_at,
    ))
    report = artifacts.coverage_report()
    assert report["represented_active_claims"] == 1
    assert report["review_held_claim_ids"] == ["pending"]
    assert report["placed_claims_without_facts"] == ["gap"]
    assert report["active_claims_without_facts"] == ["gap", "pending", "unplaced"]
    assert report["repeated_fact_claim_ids"] == []
    artifacts.save_consolidated_fact(replace(fact(items["accepted"]), fact_id="duplicate"))
    assert artifacts.coverage_report()["repeated_fact_claim_ids"] == ["accepted"]


def test_truth_schema_separates_incoming_from_prior_targets():
    schema = fact_truth_output_model(["C001"])
    valid = {"comparisons":[{"target":"C001","scope":"same","reason":"Same state."}],
             "relation":"supersedes","changed_targets":["C001"],"reason":"The incoming evidence replaces the prior state."}
    assert schema.model_validate(valid).root.relation == "supersedes"
    with pytest.raises(ValidationError):
        schema.model_validate({**valid,"changed_targets":["C002"]})



def test_fact_candidate_schema_requires_exact_claim_and_fact_aliases():
    schema = fact_candidate_selection_output_model(["C001"], ["X001"])
    valid = {"decisions": {"C001": {
        "candidate_fact_ids": ["X001"],
        "reason": "The prior fact may express the same durable state.",
    }}}

    assert schema.model_validate(valid).decisions.C001.candidate_fact_ids == [
        "X001"
    ]
    valid["decisions"]["C001"]["candidate_fact_ids"] = ["X999"]
    with pytest.raises(ValidationError):
        schema.model_validate(valid)


def test_fact_prompt_does_not_expose_recording_time_as_event_evidence(tmp_path):
    artifacts = setup_owner(tmp_path)
    item = claim(
        "timeless",
        "The user prefers written updates.",
        "2026-09-03T12:00:00-07:00",
    )
    placement = place(artifacts, item)
    resolver = FactResolver(AsyncMock(), artifacts)

    rendered = resolver._claims_text(
        {"C001": item},
        {item.claim_id: placement},
        {},
        {"you": artifacts.get_entity("you")},
    )

    assert item.recorded_at not in rendered


def test_truth_input_deduplicates_source_text_and_keeps_claim_citations(tmp_path):
    artifacts = setup_owner(tmp_path)
    first = claim("first", "The user prefers written updates.", "2026-09-09")
    second = claim("second", "The user prefers concise updates.", "2026-09-09")
    second.provenance = list(first.provenance)
    source_id = first.provenance[0].source_id
    segment_id = first.provenance[0].segment_ids[0]
    artifacts.save_source(SourceDocument(
        source_id, "agent_conversation", "s", "2026-09-09", "2026-02-12", ["user"],
        [SourceSegment(segment_id, 0, "Please send short written updates.", "user", "user")],
    ))
    placements = {c.claim_id: place(artifacts, c) for c in (first, second)}
    rendered = FactResolver(AsyncMock(), artifacts)._claims_text(
        {"C001": first, "C002": second}, placements, {}, {},
    )
    payload = json.loads(rendered)
    assert rendered.count("Please send short written updates.") == 1
    assert payload["sources"][source_id]["occurred_at"] == "2026-02-12"
    for alias in ("C001", "C002"):
        assert payload["claims"][alias]["citations"][0]["source_id"] == source_id
        assert payload["claims"][alias]["citations"][0]["segment_id"] == segment_id



@pytest.mark.asyncio
async def test_owner_plan_groups_independent_support(tmp_path):
    artifacts = setup_owner(tmp_path)
    first = claim("first", "The user prefers written updates.", "2026-08-01T12:00:00")
    second = claim("second", "Written updates are preferred.", "2026-08-02T12:00:00")
    placements = [place(artifacts, first), place(artifacts, second)]
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [{
        "facts": [{"prominence": "briefing",
            "member_claim_aliases": ["C001", "C002"],
            "memory_scope": "Preferred update format.",
            "state": "current",
            "section_key": "preferences_working_style",
            "text": "The user prefers written updates.",
        }],
    }]

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
async def test_synthesis_uses_corrected_claim_not_original_source(tmp_path):
    artifacts = setup_owner(tmp_path)
    corrected = claim("corrected", "The user prefers coffee.", "2026-08-01T12:00:00")
    related = claim("related", "The user drinks coffee each morning.", "2026-08-02T12:00:00")
    placements = [place(artifacts, item) for item in (corrected, related)]
    evidence = corrected.provenance[0]
    artifacts.save_source(SourceDocument(
        source_id=evidence.source_id, source_type="agent_conversation", session_id="chat",
        recorded_at=corrected.recorded_at, occurred_at=None, participants=["user"],
        segments=[SourceSegment(evidence.segment_ids[0], 0, "I prefer tea.", "user", "user")],
    ))
    llm = AsyncMock(context_window_tokens=32768)

    async def respond(_system, user, _schema, **kwargs):
        assert kwargs["debug_label"] == "dream-fact-synthesis"
        assert corrected.text in user and related.text in user
        assert "I prefer tea." not in user
        assert corrected.recorded_at not in user
        return {"facts": [{"prominence": "briefing", 'memory_scope': 'The fixture memory.', 'member_claim_aliases': ['C001', 'C002'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': 'The user prefers coffee and drinks it each morning.'}]}

    llm.call_structured.side_effect = respond
    result = await FactResolver(llm, artifacts).resolve(
        placements, affected_entity_ids={"you"},
        incoming_claim_ids={corrected.claim_id, related.claim_id}, dream_run_id="dream-corrected",
    )
    assert result.failures == []
    assert result.facts[0].member_claim_ids == ["corrected", "related"]
    assert artifacts.get_claim("corrected").text == corrected.text


@pytest.mark.asyncio
@pytest.mark.parametrize("manual", [False, True])
async def test_synthesis_receives_only_manual_previous_presentations(tmp_path, manual):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers written updates.", "2026-08-01")
    new = claim("new", "The user prefers concise updates.", "2026-08-02")
    placements = {c.claim_id: place(artifacts, c) for c in (old, new)}
    previous = replace(fact(old), text="Previous presentation wording.", manual_text=manual)
    llm = AsyncMock(context_window_tokens=32768)

    async def respond(_system, user, schema, **kwargs):
        if kwargs["debug_label"] == "dream-fact-candidate-selection":
            return {"decisions": {alias: {
                "candidate_fact_ids": ["X001"], "reason": "Related canonical members."
            } for alias in schema.model_fields["decisions"].annotation.model_fields}}
        assert kwargs["debug_label"] == "dream-fact-synthesis"
        assert old.text in user and new.text in user
        assert (previous.text in user) == manual
        return {"facts": [{"prominence": "briefing", 'memory_scope': "The user's update preference.", 'member_claim_aliases': ['C001', 'C002'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': 'The user prefers concise written updates.'}]}

    llm.call_structured.side_effect = respond
    result = await FactResolver(llm, artifacts)._resolve_owner_step(
        "you", [old, new], placements, [previous], set(), "test",
        {"you": artifacts.get_entity("you")},
    )
    assert result.facts[0].member_claim_ids == ["new", "old"]
    assert result.facts[0].manual_text == manual
    assert result.facts[0].text == (
        previous.text if manual else "The user prefers concise written updates."
    )


@pytest.mark.asyncio
async def test_synthesis_keeps_distinct_claim_groups(tmp_path):
    artifacts = setup_owner(tmp_path)
    first = claim("first", "The user joined a cooking class.", "2026-08-01T12:00:00")
    second = claim("second", "The user began exercising.", "2026-08-02T12:00:00")
    placements = [place(artifacts, first), place(artifacts, second)]
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [{
        "facts": [
            {"prominence": "briefing",
                "member_claim_aliases": ["C001"],
                "memory_scope": "Cooking class.",
                "state": "history",
                "section_key": "preferences_working_style",
                "text": None,
            },
            {"prominence": "briefing",
                "member_claim_aliases": ["C002"],
                "memory_scope": "Exercise.",
                "state": "history",
                "section_key": "preferences_working_style",
                "text": None,
            },
        ],
    }]

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"first", "second"},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert {tuple(item.member_claim_ids) for item in result.facts} == {
        ("first",),
        ("second",),
    }


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
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [{
        "facts": [{"prominence": "briefing",
            "member_claim_aliases": ["C001", "C002"],
            "memory_scope": "Permit coordination responsibilities.",
            "state": "current",
            "section_key": "shared_projects",
            "text": "Rosa coordinates permits for two projects.",
        }],
    }]

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
async def test_truth_change_publishes_both_accounts_for_optional_review(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers tea.", "2026-08-01T12:00:00")
    new = claim("new", "The user now prefers coffee.", "2026-08-05T12:00:00")
    placements = [place(artifacts, old), place(artifacts, new)]
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The prior fact describes the preference being replaced.",
        }}},
        {
            "comparisons": [{"target": "C001", "scope": "same", "reason": "Same preference."}],
            "relation": "supersedes",
            "changed_targets": ["C001"],
            "reason": "The newer statement explicitly replaces the old preference.",
        },
    ]

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"new"},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert old_fact in result.facts
    assert {cid for f in result.facts for cid in f.member_claim_ids} == {"old", "new"}
    assert len(result.proposals) == 1
    assert result.proposals[0].incoming_claim_ids == ["new"]
    assert result.proposals[0].target_claim_ids == ["old"]
    assert any(f.member_claim_ids == ["new"] for f in result.facts)


@pytest.mark.asyncio
async def test_repeated_evidence_joins_and_preserves_the_existing_fact(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim(
        "old", "The user prefers written updates.", "2026-08-01T12:00:00"
    )
    repeated = claim(
        "repeated", "Written updates are preferred.", "2026-08-05T12:00:00"
    )
    placements = [place(artifacts, item) for item in (old, repeated)]
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The prior fact describes the same preference.",
        }}},
        {
            "comparisons": [{"target": "C001", "scope": "same", "reason": "Same preference."}],
            "relation": "no_change",
            "changed_targets": [],
            "reason": "The new claim independently supports the existing state.",
        },
        {"facts": [{"prominence": "briefing",
            "member_claim_aliases": ["C001", "C002"],
            "memory_scope": "Preferred update format.",
            "state": "current",
            "section_key": "preferences_working_style",
            "text": old.text,
        }]},
    ]

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={repeated.claim_id},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert len(result.facts) == 1
    assert result.facts[0].fact_id == old_fact.fact_id
    assert result.facts[0].member_claim_ids == ["old", "repeated"]


@pytest.mark.asyncio
async def test_truth_changes_are_decided_sequentially_and_cannot_compete(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user's bicycle is blue.", "2026-08-01T12:00:00")
    first = claim(
        "first", "The user's bicycle is now green.", "2026-08-05T12:00:00"
    )
    support = claim(
        "support", "The user repainted the bicycle green.", "2026-08-06T12:00:00"
    )
    placements = [place(artifacts, item) for item in (old, first, support)]
    artifacts.save_consolidated_fact(fact(old))
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The fact may be the prior bicycle state.",
        }, "C002": {
            "candidate_fact_ids": ["X001"],
            "reason": "The fact may be the prior bicycle state.",
        }}},
        {'comparisons': [{'target': 'C001', 'scope': 'same', 'reason': 'The fixture evidence establishes this scope.'}], 'relation': 'supersedes', 'changed_targets': ['C001'], 'reason': 'The new color replaces the old color.'},
        {"facts": [{"prominence": "briefing", 'memory_scope': 'The fixture memory.', 'member_claim_aliases': ['C003'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': None}]},
    ]

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"first", "support"},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert len(result.proposals) == 1
    assert result.proposals[0].incoming_claim_ids == ["first"]
    truth_calls = [
        call for call in llm.call_structured.await_args_list
        if call.kwargs.get("debug_label") == "dream-fact-truth"
    ]
    assert len(truth_calls) == 1


@pytest.mark.asyncio
async def test_incremental_resolution_preserves_unselected_fact_exactly(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers tea.", "2026-08-01T12:00:00")
    unrelated = claim(
        "project", "The user maintains Project North.", "2026-08-02T12:00:00"
    )
    new = claim("new", "The user prefers coffee.", "2026-08-05T12:00:00")
    placements = [place(artifacts, item) for item in (old, unrelated, new)]
    old_fact = fact(old)
    unrelated_fact = fact(unrelated)
    artifacts.save_consolidated_fact(old_fact)
    artifacts.save_consolidated_fact(unrelated_fact)
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The prior preference may express the same durable state.",
        }}},
        {'comparisons': [{'target': 'C001', 'scope': 'same', 'reason': 'The fixture evidence establishes this scope.'}], 'relation': 'no_change', 'changed_targets': [], 'reason': 'The evidence does not explicitly replace the prior preference.'},
        {"facts": [{"prominence": "briefing", 'memory_scope': 'The fixture memory.', 'member_claim_aliases': ['C001'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': None}, {"prominence": "briefing", 'memory_scope': 'The fixture memory.', 'member_claim_aliases': ['C002'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': None}]},
    ]

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"new"},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    preserved = next(
        item for item in result.facts if item.fact_id == unrelated_fact.fact_id
    )
    assert preserved == unrelated_fact


@pytest.mark.asyncio
async def test_invalid_plan_fails_closed_and_preserves_prior_fact(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers tea.", "2026-08-01T12:00:00")
    new = claim("new", "The user now prefers coffee.", "2026-08-05T12:00:00")
    placements = [place(artifacts, old), place(artifacts, new)]
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The prior fact may express the same durable state.",
        }}},
        {'comparisons': [{'target': 'C001', 'scope': 'same', 'reason': 'The fixture evidence establishes this scope.'}], 'relation': 'no_change', 'changed_targets': [], 'reason': 'No change proposed by this test decision.'},
        {"facts": [{"prominence": "briefing", 'memory_scope': 'The fixture memory.', 'member_claim_aliases': ['C002'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': None}]},
    ]

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"new"},
        dream_run_id="dream-1",
    )

    assert len(result.failures) == 1
    assert "exactly one display group" in result.failures[0].reason
    assert result.facts == [old_fact]
    assert result.deleted_fact_ids == set()
    assert result.proposals == []


@pytest.mark.asyncio
async def test_pending_review_cannot_swallow_an_unrelated_new_claim(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user's bicycle is blue.", "2026-08-01T12:00:00")
    pending = claim("pending", "The user's bicycle is now green.", "2026-08-02T12:00:00")
    other = claim("other", "The user joined a choir.", "2026-08-03T12:00:00")
    placements = [place(artifacts, item) for item in (old, pending, other)]
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="review-color", incoming_claim_ids=[pending.claim_id],
        target_claim_ids=[old.claim_id], proposed_relation="supersedes",
        explanation="An explicit color replacement awaits review.", confidence=0.9,
        dream_run_id="earlier", created_at=old.recorded_at, affected_entity_ids=["you"],
    ))
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = [
        {"decisions": {alias: {"candidate_fact_ids": ["X001"], "reason": "Candidate for review."}}}
        for alias in ("C001",)
    ] + [
        {'comparisons': [{'target': 'C001', 'scope': 'distinct', 'reason': 'The fixture evidence establishes this scope.'}], 'relation': 'no_change', 'changed_targets': [], 'reason': 'No new proposal.'}
        for alias in ("C002",)
    ] + [{"facts": [{"prominence": "briefing", 'memory_scope': 'The fixture memory.', 'member_claim_aliases': ['C002'], 'text': None, 'state': 'current', 'section_key': 'preferences_working_style'}]}]

    result = await FactResolver(llm, artifacts).resolve(
        placements, affected_entity_ids={"you"}, incoming_claim_ids={"pending", "other"},
        dream_run_id="next",
    )

    assert not result.failures
    assert old_fact in result.facts
    assert {cid for item in result.facts for cid in item.member_claim_ids} == {"old", "other", "pending"}
    assert not result.proposals
    synthesis = llm.call_structured.await_args_list[-1]
    assert synthesis.kwargs["debug_label"] == "dream-fact-synthesis"
    assert old.text not in synthesis.args[1]
    assert pending.text not in synthesis.args[1]
    assert other.text in synthesis.args[1]


@pytest.mark.asyncio
async def test_pending_review_alone_does_not_trigger_more_model_work(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user's bicycle is blue.", "2026-08-01T12:00:00")
    pending = claim("pending", "The user's bicycle is now green.", "2026-08-02T12:00:00")
    for item in (old, pending):
        place(artifacts, item)
    old_fact = fact(old)
    artifacts.save_consolidated_fact(old_fact)
    artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="review", incoming_claim_ids=["pending"], target_claim_ids=["old"],
        proposed_relation="supersedes", explanation="Awaiting review.", confidence=0.9,
        dream_run_id="earlier", created_at=old.recorded_at, affected_entity_ids=["you"],
    ))
    llm = AsyncMock(context_window_tokens=32768)
    resolver = FactResolver(llm, artifacts)
    result = await resolver.resolve(
        [], affected_entity_ids={"you"}, incoming_claim_ids=set(), dream_run_id="next",
    )
    llm.call_structured.assert_not_awaited()
    assert old_fact in result.facts
    assert any(f.member_claim_ids == ["pending"] for f in result.facts)
    assert not result.failures
    assert not result.proposals
    assert not result.deleted_fact_ids
    proposal = artifacts.get_reconsolidation_proposal("review")
    proposal.status = "rejected"
    artifacts.save_reconsolidation_proposal(proposal)
    resolver._resolve_owner_step = AsyncMock(return_value=FactResolutionResult(facts=[old_fact, fact(pending)]))
    await resolver.resolve([], affected_entity_ids={"you"}, incoming_claim_ids=set(), dream_run_id="reviewed")
    assert {c.claim_id for c in resolver._resolve_owner_step.await_args.args[1]} == {"old", "pending"}


@pytest.mark.asyncio
@pytest.mark.parametrize("has_history,change_placement", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("failed_batch", [0, 1])
async def test_failed_addition_batch_preserves_other_batches(tmp_path, has_history, change_placement, failed_batch):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user grows herbs.", "2026-07-01T12:00:00")
    if has_history:
        place(artifacts, old)
        artifacts.save_consolidated_fact(fact(old))
    additions = [claim(f"new-{i}", f"Statement {i}.", f"2026-08-{i:02d}T12:00:00")
                 for i in range(1, 30)]
    placements = [place(artifacts, item) for item in additions]
    if change_placement:
        placements.append(replace(artifacts.placement_for_claim(old.claim_id),
                                  section_key="current_context", page_sections={"you": "current_context"}))
    resolver = FactResolver(AsyncMock(), artifacts)
    batches = []

    async def step(owner_id, claims, placements, existing, incoming_ids, *args, **kwargs):
        represented = {cid for f in existing for cid in f.member_claim_ids}
        new = [c for c in claims if c.claim_id not in represented]
        batches.append({c.claim_id for c in new})
        if len(batches) - 1 == failed_batch:
            raise ValueError("Injected invalid model output")
        return FactResolutionResult(facts=[*existing, *(fact(c) for c in new)],
                                    placements=[placements[c.claim_id] for c in new])

    resolver._resolve_owner_step = AsyncMock(side_effect=step)
    result = await resolver.resolve(
        placements, affected_entity_ids={"you"}, incoming_claim_ids={c.claim_id for c in additions},
        dream_run_id="batch-test",
    )
    assert len(result.failures) == 1
    if change_placement:
        assert not result.failures[0].partial
        assert result.failed_owner_ids == {"you"}
        assert result.facts == [fact(old)]
        assert not result.placements
        assert not result.deleted_fact_ids
        return
    assert result.failures[0].partial
    assert set(result.failures[0].claim_ids) == batches[failed_batch]
    assert not result.failed_owner_ids
    assert not result.deleted_fact_ids
    expected = {c.claim_id for c in additions} - batches[failed_batch]
    if has_history:
        expected.add(old.claim_id)
        assert fact(old) in result.facts
    assert {cid for f in result.facts for cid in f.member_claim_ids} == expected
    limit = resolver._MAX_ADDITIONS_WITH_HISTORY if has_history else resolver._MAX_UNREPRESENTED_PER_GROUPING
    assert all(len(batch) <= limit for batch in batches)
    first_success = 1 if failed_batch == 0 else 0
    assert all(len(batch) <= resolver._MAX_ADDITIONS_WITH_HISTORY for batch in batches[first_success + 1:])
    assert set.union(*batches) == {c.claim_id for c in additions}


@pytest.mark.asyncio
async def test_large_new_claim_sets_are_grouped_incrementally(tmp_path):
    artifacts = setup_owner(tmp_path)
    claims = [
        claim(
            f"claim-{index:02d}",
            f"The user records distinct preference {index}.",
            f"2026-08-{index:02d}T12:00:00",
        )
        for index in range(1, 14)
    ]
    placements = [place(artifacts, item) for item in claims]
    llm = AsyncMock(context_window_tokens=32768)
    call_counts = {"truth": 0, "synthesis": 0}

    async def respond(_system, _user, _schema, **kwargs):
        label = kwargs["debug_label"]
        if label == "dream-fact-candidate-selection":
            return {"decisions": {"C001": {
                "candidate_fact_ids": [],
                "reason": "The incoming memory is independent.",
            }}}
        if label == "dream-fact-truth":
            call_counts["truth"] += 1
            alias = (
                f"C{call_counts['truth']:03d}"
                if call_counts["truth"] <= 12
                else "C001"
            )
            return {"decisions": {alias: {
                "disposition": "no_change",
                "reason": "No accepted truth is changed.",
                "confidence": 0.9,
            }}}
        if label == "dream-fact-synthesis":
            call_counts["synthesis"] += 1
            batch = claims[:12] if call_counts["synthesis"] == 1 else claims[12:]
            return {"facts": [{"prominence": "briefing", 'memory_scope': 'The fixture memory.', 'member_claim_aliases': [f'C{index:03d}'], 'state': 'current', 'section_key': 'preferences_working_style', 'text': None} for index, item in enumerate(batch, 1)]}
        raise AssertionError(f"Unexpected model call: {label}")

    llm.call_structured.side_effect = respond

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={item.claim_id for item in claims},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert len(result.facts) == 13
    synthesis_calls = [
        call for call in llm.call_structured.await_args_list
        if call.kwargs.get("debug_label") == "dream-fact-synthesis"
    ]
    assert len(synthesis_calls) == 2


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
    from tests.lifecycle_support import lifecycle_response
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.side_effect = lifecycle_response
    resolver = FactResolver(llm, artifacts)
    service = ReconsolidationReviewService(
        artifacts,
        PageMaterializer(wiki, artifacts, Config.defaults()),
        resolver,
    )

    result = await service.approve("recon-1", reviewer_note="Confirmed")

    assert result.proposal.status == "applied"
    assert artifacts.get_claim("old").status == "superseded"
    assert artifacts.get_claim("new").links == [{"relation": "supersedes", "target": "old"}]
    assert {cid for item in artifacts.list_consolidated_facts() for cid in item.member_claim_ids} == {"new"}
    llm.call_structured.assert_awaited()


def test_claim_evidence_carries_only_cited_occurrence_anchors(tmp_path):
    artifacts = setup_owner(tmp_path)
    item = claim("dated", "An event happened last Saturday.", "2026-09-08T18:00:00Z")
    placement = place(artifacts, item)
    source_id = item.provenance[0].source_id
    cited_id = item.provenance[0].segment_ids[0]
    artifacts.save_source(SourceDocument(source_id, "agent_conversation", "s", item.recorded_at,
        "2026-02-12", ["user"], [SourceSegment(cited_id, 0, item.text, timestamp="2026-02-12T10:00:00Z"),
                                 SourceSegment("uncited", 1, "Unrelated text.", timestamp="2025-01-01")]))
    resolver = FactResolver(AsyncMock(), artifacts)
    rendered = resolver._claims_text({"C001": item}, {item.claim_id: placement}, {}, {})
    assert "2026-02-12T10:00:00Z" in rendered
    assert item.recorded_at not in rendered
    assert "2025-01-01" not in rendered
    assert resolver._source_times(item) == [{"source_id": source_id, "occurred_at": "2026-02-12",
                                           "segments": [{"segment_id": cited_id, "timestamp": "2026-02-12T10:00:00Z"}]}]


@pytest.mark.asyncio
async def test_candidate_selection_receives_canonical_members_and_source_times(tmp_path):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user's workshop is on Tuesday.", "2026-09-08")
    new = claim("new", "The user's workshop has eight seats.", "2026-09-09")
    placements = {c.claim_id: place(artifacts, c) for c in (old, new)}
    source_id = old.provenance[0].source_id
    artifacts.save_source(SourceDocument(source_id, "agent_conversation", "s", "2026-09-08",
        "2026-02-12", [], [SourceSegment(old.provenance[0].segment_ids[0], 0, "Original source words.",
                                         timestamp="2026-02-12T10:00:00Z")]))
    existing = fact(old)
    existing.text = "An over-broad display sentence that omits the schedule."
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.return_value = {"decisions": {"C001": {"candidate_fact_ids": ["X001"], "reason": "Same workshop."}}}
    selected = await FactResolver(llm, artifacts)._select_prior_facts(
        [new], placements, [existing], {"you": artifacts.get_entity("you")})
    user = llm.call_structured.call_args.args[1]
    assert old.text in user and "2026-02-12T10:00:00Z" in user
    assert "Original source words." not in user
    assert selected == {new.claim_id: {existing.fact_id}}
