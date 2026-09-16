from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.context_selection import (
    AssistantContextCandidate,
    AssistantContextSelector,
)
from mycelium.structured_outputs import complementary_selection_model


def test_context_selection_schema_preserves_order_and_rejects_invalid_ids():
    schema = complementary_selection_model(["M001", "M002"])
    valid = {"selected_ids": ["M002", "M001"], "supported_aspects": [], "remaining_gaps": []}
    assert schema.model_validate(valid).selected_ids == ["M002", "M001"]
    for invalid in (["M003"], ["M001", "M001"]):
        with pytest.raises(ValidationError):
            schema.model_validate({**valid, "selected_ids": invalid})


@pytest.mark.asyncio
async def test_context_selector_can_abstain_from_every_candidate():
    llm = AsyncMock()
    llm.context_window_tokens = 32768
    llm.call_structured.return_value = {"selected_ids": [], "supported_aspects": [], "remaining_gaps": ["No support"]}
    candidates = [
        AssistantContextCandidate("page:first", "wiki_page", "First", "One"),
        AssistantContextCandidate("page:second", "wiki_page", "Second", "Two"),
    ]

    assert await AssistantContextSelector(llm).select("Unrelated", candidates) == []


@pytest.mark.asyncio
async def test_context_selector_fails_closed_on_invalid_model_output():
    llm = AsyncMock()
    llm.context_window_tokens = 32768
    llm.call_structured.return_value = {"decisions": {}}

    selected = await AssistantContextSelector(llm).select(
        "Question",
        [AssistantContextCandidate("page:first", "wiki_page", "First", "One")],
    )

    assert selected == []


@pytest.mark.asyncio
async def test_admission_rejects_winners_that_cannot_be_compared_together():
    from mycelium.context_selection import AssistantContextCandidate, AssistantContextSelector
    llm = AsyncMock()
    llm.context_window_tokens = 11000
    seen = []
    async def select(system, user, schema, **kwargs):
        seen.append(user)
        from typing import get_args
        aliases = get_args(get_args(schema.model_fields["selected_ids"].annotation)[0])
        return {"selected_ids": list(aliases), "supported_aspects": [], "remaining_gaps": []}
    llm.call_structured.side_effect = select
    candidates = [AssistantContextCandidate(str(i), "claim", "Record", "material " * 1500 + f"TAIL-{i}")
                  for i in range(6)]
    result = await AssistantContextSelector(llm).select_with_trace("Retrieve these records", candidates)
    assert result.selected_ids == ()
    assert "budget" in result.error
    assert len(seen) > 1
    for i in range(6):
        assert sum(f"TAIL-{i}" in prompt for prompt in seen) == 1


@pytest.mark.asyncio
async def test_global_selection_overrides_chunk_order_and_restores_diagnostics():
    llm = AsyncMock()
    llm.context_window_tokens = 10000
    llm.call_structured.side_effect = [
        {"selected_ids": ["M001", "M002"], "supported_aspects": ["Left"], "remaining_gaps": ["Other details"]},
        {"selected_ids": ["M001", "M002"], "supported_aspects": ["Right"], "remaining_gaps": ["Other details"]},
        {"selected_ids": ["M003", "M002"], "supported_aspects": ["Combined support"], "remaining_gaps": []},
    ]
    candidates = [AssistantContextCandidate(str(i), "claim", "Record", "material " * 1200 + f"TAIL-{i}")
                  for i in range(6)]
    result = await AssistantContextSelector(llm).select_with_trace("Retrieve these records", candidates)
    assert llm.call_structured.await_count == 3
    assert result.error is None
    assert result.selected_ids == ("3", "1")
    assert result.supported_aspects == ("Combined support",)
    assert result.remaining_gaps == ()
    assert result.decisions == {str(i): {"disposition": "include" if i in {1, 3} else "exclude"}
                                for i in range(6)}
    final_prompt = llm.call_structured.call_args.args[1]
    assert all(f"TAIL-{i}" in final_prompt for i in (0, 1, 3, 4))
    assert all(f"TAIL-{i}" not in final_prompt for i in (2, 5))


@pytest.mark.asyncio
async def test_failed_chunk_cannot_admit_successful_chunk_evidence():
    llm = AsyncMock()
    llm.context_window_tokens = 10000
    llm.call_structured.side_effect = [ValueError("Invalid selection")]
    candidates = [AssistantContextCandidate(str(i), "claim", "Record", "material " * 1200)
                  for i in range(6)]
    result = await AssistantContextSelector(llm).select_with_trace("Retrieve these records", candidates)
    assert result.selected_ids == ()
    assert "Invalid selection" in result.error
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_empty_chunks_preserve_gaps_without_a_merge_call():
    llm = AsyncMock()
    llm.context_window_tokens = 10000
    llm.call_structured.side_effect = [
        {"selected_ids": [], "supported_aspects": [], "remaining_gaps": ["Missing date"]},
        {"selected_ids": [], "supported_aspects": [], "remaining_gaps": ["Missing place"]},
    ]
    candidates = [AssistantContextCandidate(str(i), "claim", "Record", "material " * 1200)
                  for i in range(6)]
    result = await AssistantContextSelector(llm).select_with_trace("Retrieve these records", candidates)
    assert result.error is None
    assert result.selected_ids == ()
    assert result.remaining_gaps == ("Missing date", "Missing place")
    assert all(row["disposition"] == "exclude" for row in result.decisions.values())
    assert llm.call_structured.await_count == 2
