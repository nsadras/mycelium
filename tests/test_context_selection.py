from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium.context_selection import (
    AssistantContextCandidate,
    AssistantContextSelector,
)
from mycelium.structured_outputs import assistant_context_selection_output_model


def test_context_selection_schema_requires_every_exact_candidate():
    schema = assistant_context_selection_output_model(["M001", "M002"])
    valid = {"decisions": {
        "M001": {
            "disposition": "include",
            "reason": "This record directly answers the request.",
        },
        "M002": {
            "disposition": "exclude",
            "reason": "This record does not help answer the request.",
        },
    }}

    assert schema.model_validate(valid).decisions.M001.disposition == "include"
    del valid["decisions"]["M002"]
    with pytest.raises(ValidationError):
        schema.model_validate(valid)


@pytest.mark.asyncio
async def test_context_selector_can_abstain_from_every_candidate():
    llm = AsyncMock()
    llm.context_window_tokens = 32768
    llm.call_structured.return_value = {"decisions": {
        "M001": {
            "disposition": "exclude",
            "reason": "The record is unrelated.",
        },
        "M002": {
            "disposition": "exclude",
            "reason": "The record is also unrelated.",
        },
    }}
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
async def test_admission_batches_complete_records_without_truncating_tail():
    from mycelium.context_selection import AssistantContextCandidate, AssistantContextSelector
    llm = AsyncMock()
    llm.context_window_tokens = 11000
    seen = []
    async def select(system, user, schema, **kwargs):
        seen.append(user)
        aliases = schema.model_fields["decisions"].annotation.model_fields
        return {"decisions": {alias: {"disposition": "include",
                                      "reason": "Supported candidate."} for alias in aliases}}
    llm.call_structured.side_effect = select
    candidates = [AssistantContextCandidate(str(i), "claim", "Record", "material " * 1500 + f"TAIL-{i}")
                  for i in range(10)]
    result = await AssistantContextSelector(llm).select_with_trace("Retrieve these records", candidates)
    assert set(result.selected_ids) == {str(i) for i in range(10)}
    assert result.error is None
    assert len(seen) > 1
    for i in range(10):
        assert sum(f"TAIL-{i}" in prompt for prompt in seen) == 1
