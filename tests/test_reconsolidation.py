from datetime import datetime
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
    responses = truth_responses + [
        {"assignments": plan["assignments"]},
        {"facts": {
            item["fact_key"]: {
                key: value for key, value in item.items() if key != "fact_key"
            }
            for item in plan["facts"]
        }},
        {"decisions": {
            item["fact_key"]: {
                "verdict": "supported",
                "reason": "The presentation is self-contained and source-grounded.",
            }
            for item in plan["facts"]
        }},
    ]
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
            "explanation": "The new color replaces the old color.",
            "confidence": 0.95,
        }}},
        {"decisions": {"C003": {
            "disposition": "no_change",
            "reason": "The changed target was already claimed by an earlier decision.",
            "confidence": 0.95,
        }}},
        {"assignments": {
            "C001": {"fact_key": "F001"},
            "C002": {"fact_key": "F002"},
            "C003": {"fact_key": "F002"},
        }},
        {"facts": {
            "F001": {
                "state": "current",
                "section_key": "preferences_working_style",
                "text": old.text,
                "confidence": 0.9,
                "reason": "Accepted prior state.",
            },
            "F002": {
                "state": "current",
                "section_key": "preferences_working_style",
                "text": "The user's bicycle is green.",
                "confidence": 0.9,
                "reason": "Proposed replacement with independent support.",
            },
        }},
        {"decisions": {
            key: {
                "verdict": "supported",
                "reason": "The presentation is source-grounded.",
            }
            for key in ("F001", "F002")
        }},
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
        {"assignments": {
            "C001": {"fact_key": "F001"},
            "C002": {"fact_key": "F002"},
        }},
        {"facts": {
            "F001": {
                "state": "current",
                "section_key": "preferences_working_style",
                "text": old.text,
                "confidence": 0.9,
                "reason": "Existing preference.",
            },
            "F002": {
                "state": "current",
                "section_key": "preferences_working_style",
                "text": new.text,
                "confidence": 0.9,
                "reason": "Independent incoming preference.",
            },
        }},
        {"decisions": {
            key: {
                "verdict": "supported",
                "reason": "The presentation is self-contained and source-grounded.",
            }
            for key in ("F001", "F002")
        }},
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
    grouping_prompt = llm.call_structured.await_args_list[2].args[1]
    assert unrelated.text not in grouping_prompt


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
            "disposition": "truth_change",
            "relation": "supersedes",
            "target_claim_aliases": ["C001"],
            "explanation": "Replacement.",
            "confidence": 0.9,
        }}},
        {"assignments": {"C001": {"fact_key": "F001"}, "C002": {"fact_key": "F001"}}},
    ]

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
async def test_fact_presentations_are_rendered_in_bounded_batches(tmp_path):
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
    assignments = {
        f"C{index:03d}": {"fact_key": f"F{index:03d}"}
        for index in range(1, 14)
    }

    def rendered(start: int, end: int) -> dict:
        return {"facts": {
            f"F{index:03d}": {
                "state": "current",
                "section_key": "preferences_working_style",
                "text": claims[index - 1].text,
                "confidence": 0.9,
                "reason": "One fixed source-grounded claim group.",
            }
            for index in range(start, end)
        }}

    def quality(start: int, end: int) -> dict:
        return {"decisions": {
            f"F{index:03d}": {
                "verdict": "supported",
                "reason": "The presentation is self-contained and source-grounded.",
            }
            for index in range(start, end)
        }}

    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"decisions": {alias: {
                    "disposition": "no_change",
                    "reason": "No accepted truth is changed.",
                    "confidence": 0.9,
        }}}
        for alias in assignments
    ] + [
        {"assignments": assignments},
        rendered(1, 13),
        quality(1, 13),
        rendered(13, 14),
        quality(13, 14),
    ]

    result = await FactResolver(llm, artifacts).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={item.claim_id for item in claims},
        dream_run_id="dream-1",
    )

    assert result.failures == []
    assert len(result.facts) == 13
    assert llm.call_structured.await_count == 18


@pytest.mark.asyncio
async def test_unsupported_fact_is_repaired_and_verified_once(tmp_path):
    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"decisions": {"F001": {
            "verdict": "unsupported",
            "reason": "The object of the conversational reference is unresolved.",
        }}},
        {"facts": {"F001": {
            "state": "current",
            "section_key": "goals_plans",
            "text": "Jolene wants to try surfing and is looking for a lesson.",
            "confidence": 0.95,
            "reason": "The member claim supplies the explicit activity.",
        }}},
        {"decisions": {"F001": {
            "verdict": "supported",
            "reason": "The repaired fact is self-contained and fully entailed.",
        }}},
    ]
    resolver = FactResolver(llm, ArtifactStore(tmp_path / "artifacts"))

    result = await resolver._verify_and_repair_facts(
        "id=person-jolene; type=person; title=Jolene",
        "[F001] members=[\"C001\"]\n[C001] Jolene wants to try surfing and is looking for a lesson.",
        {"F001": {
            "state": "current",
            "section_key": "goals_plans",
            "text": "Jolene wants to try it.",
            "confidence": 0.8,
            "reason": "Initial rendering.",
        }},
    )

    assert result["F001"]["text"] == (
        "Jolene wants to try surfing and is looking for a lesson."
    )
    assert llm.call_structured.await_count == 3


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
