from datetime import datetime
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    ConsolidatedFact,
    MemoryClaim,
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


def staged_fact_responses(
    plan: dict,
    *,
    candidate_fact_aliases: list[str] | None = None,
    incoming_aliases: list[str] | None = None,
) -> list[dict]:
    changes_by_incoming = {
        alias: change
        for change in plan["truth_changes"]
        for alias in change["incoming_claim_aliases"]
    }
    incoming_aliases = incoming_aliases or (
        sorted(changes_by_incoming)
        if changes_by_incoming
        else sorted(plan["assignments"])
    )
    truth_responses = [
        {"decisions": {
            alias: (
                {
                    "disposition": "truth_change",
                    "relation": changes_by_incoming[alias]["relation"],
                    "target_claim_aliases": changes_by_incoming[alias][
                        "target_claim_aliases"
                    ],
                    "durable_field": changes_by_incoming[alias].get(
                        "durable_field", "tested durable field"
                    ),
                    "prior_state": changes_by_incoming[alias].get(
                        "prior_state", "prior state"
                    ),
                    "incoming_state": changes_by_incoming[alias].get(
                        "incoming_state", "incoming state"
                    ),
                    "transition_evidence": changes_by_incoming[alias].get(
                        "transition_evidence", "The test establishes a transition."
                    ),
                    "explanation": changes_by_incoming[alias]["explanation"],
                    "confidence": changes_by_incoming[alias]["confidence"],
                }
                if alias in changes_by_incoming
                else {
                    "disposition": "no_change",
                    "reason": "No accepted truth is changed.",
                    "confidence": 0.9,
                }
            )
        }}
        for alias in incoming_aliases
    ]
    responses = truth_responses + [{
        "facts": [{
            **{key: value for key, value in fact.items() if key != "fact_key"},
            "member_claim_aliases": [alias for alias, assignment in plan["assignments"].items()
                                     if assignment["fact_key"] == fact["fact_key"]],
        } for fact in plan["facts"]],
    }]
    if candidate_fact_aliases is not None:
        responses[0:0] = [
            {"decisions": {f"C{index:03d}": {
                "candidate_fact_ids": candidate_fact_aliases,
                "reason": "The prior fact may express the same durable state.",
            }}}
            for index, _alias in enumerate(incoming_aliases, start=1)
        ]
    return responses


def test_truth_schema_separates_incoming_from_prior_targets():
    schema = fact_truth_output_model(["C002"], ["C001"])

    valid = {"decisions": {"C002": {
        "disposition": "truth_change",
        "relation": "supersedes",
        "target_claim_aliases": ["C001"],
        "durable_field": "preferred drink",
        "prior_state": "tea",
        "incoming_state": "coffee",
        "transition_evidence": "The incoming claim explicitly says now.",
        "explanation": "The incoming evidence explicitly replaces the prior state.",
        "confidence": 0.9,
    }}}
    assert schema.model_validate(valid).decisions.C002.disposition == "truth_change"

    invalid = {"decisions": {"C002": {
        **valid["decisions"]["C002"],
        "target_claim_aliases": ["C002"],
    }}}
    with pytest.raises(ValidationError):
        schema.model_validate(invalid)


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



@pytest.mark.asyncio
async def test_owner_plan_groups_independent_support(tmp_path):
    artifacts = setup_owner(tmp_path)
    first = claim("first", "The user prefers written updates.", "2026-08-01T12:00:00")
    second = claim("second", "Written updates are preferred.", "2026-08-02T12:00:00")
    placements = [place(artifacts, first), place(artifacts, second)]
    llm = AsyncMock()
    llm.call_structured.side_effect = staged_fact_responses({
        "assignments": {"C001": {"fact_key": "F001"}, "C002": {"fact_key": "F001"}},
        "facts": [{
            "fact_key": "F001",
            "state": "current",
            "section_key": "preferences_working_style",
            "text": "The user prefers written updates.",
            "confidence": 0.95,
            "reason": "Independent support.",
        }],
        "truth_changes": [],
    })

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
    llm = AsyncMock()

    async def respond(_system, user, _schema, **kwargs):
        if kwargs["debug_label"] == "dream-fact-truth":
            return {"decisions": {alias: {"disposition": "no_change", "confidence": 0.9,
                                         "reason": "No prior state is changed."}
                                  for alias in _schema.model_fields["decisions"].annotation.model_fields}}
        assert kwargs["debug_label"] == "dream-fact-synthesis"
        assert corrected.text in user and related.text in user
        assert "I prefer tea." not in user
        assert corrected.recorded_at not in user
        return {"facts": [{"member_claim_aliases": ["C001", "C002"], "state": "current",
                           "section_key": "preferences_working_style",
                           "text": "The user prefers coffee and drinks it each morning.",
                           "confidence": 0.9, "reason": "Compatible canonical statements."}]}

    llm.call_structured.side_effect = respond
    result = await FactResolver(llm, artifacts).resolve(
        placements, affected_entity_ids={"you"},
        incoming_claim_ids={corrected.claim_id, related.claim_id}, dream_run_id="dream-corrected",
    )
    assert result.failures == []
    assert result.facts[0].member_claim_ids == ["corrected", "related"]
    assert artifacts.get_claim("corrected").text == corrected.text


@pytest.mark.asyncio
async def test_synthesis_keeps_distinct_claim_groups(tmp_path):
    artifacts = setup_owner(tmp_path)
    first = claim("first", "The user joined a cooking class.", "2026-08-01T12:00:00")
    second = claim("second", "The user began exercising.", "2026-08-02T12:00:00")
    placements = [place(artifacts, first), place(artifacts, second)]
    llm = AsyncMock()
    llm.call_structured.side_effect = staged_fact_responses({
        "assignments": {
            "C001": {"fact_key": "F001"},
            "C002": {"fact_key": "F002"},
        },
        "facts": [
            {
                "fact_key": "F001",
                "state": "history",
                "section_key": "preferences_working_style",
                "text": first.text,
                "confidence": 0.9,
                "reason": "One source-grounded memory.",
            },
            {
                "fact_key": "F002",
                "state": "history",
                "section_key": "preferences_working_style",
                "text": second.text,
                "confidence": 0.9,
                "reason": "A distinct source-grounded memory.",
            },
        ],
        "truth_changes": [],
    })

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
    llm = AsyncMock()
    llm.call_structured.side_effect = staged_fact_responses({
        "assignments": {
            "C001": {"fact_key": "F001"},
            "C002": {"fact_key": "F001"},
        },
        "facts": [{
            "fact_key": "F001",
            "state": "current",
            "section_key": "shared_projects",
            "text": "Rosa coordinates permits for two projects.",
            "confidence": 0.9,
            "reason": "Related responsibilities.",
        }],
        "truth_changes": [],
    })

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
    llm.call_structured.side_effect = staged_fact_responses({
        "assignments": {"C001": {"fact_key": "F001"}, "C002": {"fact_key": "F002"}},
        "facts": [
            {"fact_key": "F001", "state": "current", "section_key": "preferences_working_style", "text": old.text, "confidence": 0.9, "reason": "Accepted state."},
            {"fact_key": "F002", "state": "current", "section_key": "preferences_working_style", "text": new.text, "confidence": 0.9, "reason": "Proposed replacement."},
        ],
        "truth_changes": [{
            "relation": "supersedes",
            "incoming_claim_aliases": ["C002"],
            "target_claim_aliases": ["C001"],
            "durable_field": "bicycle color",
            "prior_state": "blue",
            "incoming_state": "green",
            "transition_evidence": "The incoming claim explicitly says now.",
            "explanation": "The newer statement explicitly replaces the old preference.",
            "confidence": 0.92,
        }],
    }, candidate_fact_aliases=["X001"], incoming_aliases=["C002"])

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
    llm = AsyncMock()
    llm.call_structured.side_effect = staged_fact_responses({
        "assignments": {
            "C001": {"fact_key": "F001"},
            "C002": {"fact_key": "F001"},
        },
        "facts": [{
            "fact_key": "F001",
            "state": "current",
            "section_key": "preferences_working_style",
            "text": old.text,
            "confidence": 0.95,
            "reason": "The new claim independently supports the existing state.",
        }],
        "truth_changes": [],
    }, candidate_fact_aliases=["X001"], incoming_aliases=["C002"])

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
    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The fact may be the prior bicycle state.",
        }}},
        {"decisions": {"C002": {
            "candidate_fact_ids": ["X001"],
            "reason": "The fact may be the prior bicycle state.",
        }}},
        {"decisions": {"C002": {
            "disposition": "truth_change",
            "relation": "supersedes",
            "target_claim_aliases": ["C001"],
            "durable_field": "preferred drink",
            "prior_state": "tea",
            "incoming_state": "coffee",
            "transition_evidence": "The incoming claim explicitly replaces the preference.",
            "explanation": "The new color replaces the old color.",
            "confidence": 0.95,
        }}},
        {"decisions": {"C003": {
            "disposition": "no_change",
            "reason": "The changed target was already claimed by an earlier decision.",
            "confidence": 0.95,
        }}},
        {"facts": [{
                "member_claim_aliases": ["C003"],
                "state": "current",
                "section_key": "preferences_working_style",
                "text": support.text,
                "confidence": 0.9,
                "reason": "Independent event; review-held state is outside presentation input.",
        }]},
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
    assert len(truth_calls) == 2


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
    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The prior preference may express the same durable state.",
        }}},
        {"decisions": {"C002": {
            "disposition": "no_change",
            "reason": "The evidence does not explicitly replace the prior preference.",
            "confidence": 0.8,
        }}},
        {"facts": [{
            "member_claim_aliases": ["C001"],
            "state": "current",
            "section_key": "preferences_working_style",
            "text": old.text,
            "confidence": 0.9,
            "reason": "Existing preference.",
        }, {
                "member_claim_aliases": ["C002"],
                "state": "current",
                "section_key": "preferences_working_style",
                "text": new.text,
                "confidence": 0.9,
                "reason": "Independent incoming preference.",
        }]},
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
    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"decisions": {"C001": {
            "candidate_fact_ids": ["X001"],
            "reason": "The prior fact may express the same durable state.",
        }}},
        {"decisions": {"C002": {
            "disposition": "no_change",
            "reason": "No change proposed by this test decision.",
            "confidence": 0.9,
        }}},
        {"facts": [{"member_claim_aliases": ["C002"],
                    "state": "current", "section_key": "preferences_working_style",
                    "text": new.text, "confidence": 0.9,
                    "reason": "Invalidly omit the existing claim."}]},
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
    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"decisions": {alias: {"candidate_fact_ids": ["X001"], "reason": "Candidate for review."}}}
        for alias in ("C001", "C002")
    ] + [
        {"decisions": {alias: {"disposition": "no_change", "reason": "No new proposal.", "confidence": 0.9}}}
        for alias in ("C002", "C003")
    ] + [{"facts": [{
        "member_claim_aliases": ["C003"], "text": other.text, "state": "current",
        "section_key": "preferences_working_style", "confidence": 0.9, "reason": "Separate activity.",
    }]}]

    result = await FactResolver(llm, artifacts).resolve(
        placements, affected_entity_ids={"you"}, incoming_claim_ids={"pending", "other"},
        dream_run_id="next",
    )

    assert not result.failures
    assert old_fact in result.facts
    assert {cid for item in result.facts for cid in item.member_claim_ids} == {"old", "other"}
    assert not result.proposals
    synthesis = llm.call_structured.await_args_list[-1]
    assert synthesis.kwargs["debug_label"] == "dream-fact-synthesis"
    assert old.text not in synthesis.args[1]
    assert pending.text not in synthesis.args[1]
    assert other.text in synthesis.args[1]


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
                 for i in range(1, 14)]
    placements = [place(artifacts, item) for item in additions]
    if change_placement:
        placements.append(replace(artifacts.placement_for_claim(old.claim_id), section_key="identity"))
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
    llm = AsyncMock()
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
            return {"facts": [{
                "member_claim_aliases": [f"C{index:03d}"],
                "state": "current", "section_key": "preferences_working_style",
                "text": item.text, "confidence": 0.9, "reason": "Distinct memory.",
            } for index, item in enumerate(batch, 1)]}
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
