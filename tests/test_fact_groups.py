
from mycelium.config import Config
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.fact_groups import MAX_GROUP_MEMBERS, fact_groups_model
from mycelium.facts import FactResolver
from tests.memory_helpers import claim, fact, place, setup_owner


def group(*ids):
    return {
        "member_claim_aliases": list(ids),
        "memory_scope": "A memory scope.",
        "section_key": "current_context",
        "state": "current",
        "prominence": "briefing",
    }


@pytest.mark.parametrize("members", [["C1"], ["C1", "C1"], ["C1", "C3"]])
def test_group_contract_requires_exact_complete_partition(members):
    schema = fact_groups_model(["C1", "C2"], ["current_context"])
    with pytest.raises(ValidationError):
        schema.model_validate({"groups": [group(*members)]})
    schema.model_validate({"groups": [group("C1"), group("C2")]})


def test_group_contract_bounds_members_and_scopes_section_ids():
    ids = [f"C{i}" for i in range(MAX_GROUP_MEMBERS + 1)]
    schema = fact_groups_model(ids, ["current_context"])
    with pytest.raises(ValidationError):
        schema.model_validate({"groups": [group(*ids)]})
    valid = {"groups": [group(*ids[:-1]), group(ids[-1])]}
    schema.model_validate(valid)
    valid["groups"][0]["section_key"] = "invented"
    with pytest.raises(ValidationError):
        schema.model_validate(valid)


@pytest.mark.asyncio
async def test_manual_fact_keeps_exact_membership_and_new_evidence_is_visible(
    tmp_path, no_truth_changes
):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers written updates.", "2031-05-01")
    new = claim("new", "The user prefers concise updates.", "2031-05-02")
    placements = [place(artifacts, c) for c in [old, new]]
    previous = replace(fact(old), text="My preferred update format.", manual_text=True)
    artifacts.save_consolidated_fact(previous)
    llm = AsyncMock(context_window_tokens=32768)

    async def respond(_system, user, _schema, **kwargs):
        assert kwargs["debug_label"] == "dream-fact-grouping"
        assert old.text not in user and previous.text not in user
        assert new.text in user
        # Re-grouping must not move accepted content into a workflow section
        # after the earlier routing stage has already selected a content section.
        for reserved in ("needs_review", "memory_map"):
            assert f"{reserved}:" not in user
            with pytest.raises(ValidationError):
                _schema.model_validate(
                    {"groups": [{**group("C001"), "section_key": reserved}]}
                )
        return {"groups": [group("C001")]}

    llm.call_structured.side_effect = respond
    result = await FactResolver(llm, artifacts, Config()).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids={"new"},
        dream_run_id="test",
    )
    assert not result.failures
    assert previous in result.facts
    assert len(result.facts) == 2
    assert next(f for f in result.facts if f != previous).member_claim_ids == ["new"]
    assert next(f for f in result.facts if f != previous).text == new.text


@pytest.mark.asyncio
async def test_manual_fact_loses_protection_when_member_is_retracted(
    tmp_path, no_truth_changes
):
    artifacts = setup_owner(tmp_path)
    old = claim("old", "The user prefers written updates.", "2031-05-01")
    other = claim("other", "The user prefers concise updates.", "2031-05-02")
    placements = [place(artifacts, c) for c in [old, other]]
    previous = replace(
        fact(old),
        member_claim_ids=["old", "other"],
        text="Manual combined presentation.",
        manual_text=True,
    )
    artifacts.save_consolidated_fact(previous)
    artifacts.save_claim(replace(old, status="retracted"))
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.return_value = {"groups": [group("C001")]}
    result = await FactResolver(llm, artifacts, Config()).resolve(
        placements,
        affected_entity_ids={"you"},
        incoming_claim_ids=set(),
        dream_run_id="test",
    )
    assert not result.failures
    assert previous.fact_id in result.deleted_fact_ids
    assert len(result.facts) == 1
    assert result.facts[0].member_claim_ids == ["other"]
    assert result.facts[0].text == other.text and not result.facts[0].manual_text


@pytest.mark.asyncio
async def test_group_render_request_is_stable_under_member_order_and_ignores_other_claims(
    tmp_path,
):
    artifacts = setup_owner(tmp_path)
    first = claim("a", "The class is on Wednesdays.", "2031-05-01")
    second = claim("b", "The user attends the class.", "2031-05-02")
    unrelated = claim("c", "The user has a bicycle.", "2031-05-02")
    for c in [first, second, unrelated]:
        place(artifacts, c)
    llm = AsyncMock(context_window_tokens=32768)
    llm.call_structured.return_value = {
        "text": "The user attends the class on Wednesdays."
    }
    resolver = FactResolver(llm, artifacts, Config())
    await resolver._render_group("You", [first, second])
    await resolver._render_group("You", [second, first])
    requests = llm.call_structured.await_args_list
    assert requests[0] == requests[1]
    assert unrelated.text not in requests[0].args[1]
    import json

    records = json.loads(requests[0].args[1].split("CANONICAL STORED CLAIMS\n", 1)[1])
    assert isinstance(records, list)
    assert [record["text"] for record in records] == [first.text, second.text]
    assert all("temporal" in record and "source_times" in record for record in records)
    assert await resolver._render_group("You", [first]) == first.text
    assert llm.call_structured.await_count == 2


def test_singleton_projection_preserves_routing_section(tmp_path):
    artifacts = setup_owner(tmp_path)
    item = claim("a", "The user prefers written updates.", "2031-05-01")
    placement = replace(
        place(artifacts, item),
        section_key="priorities_plans",
        page_sections={"you": "priorities_plans"},
    )
    projection, updated = FactResolver._direct_projection(
        artifacts.get_entity("you"), item, placement
    )
    assert projection.section_key == updated.page_sections["you"] == "priorities_plans"
