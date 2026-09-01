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
            "confidence": 0.9,
            "reason": "This record directly answers the request.",
        },
        "M002": {
            "disposition": "exclude",
            "confidence": 0.9,
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
    llm.call_structured.return_value = {"decisions": {
        "M001": {
            "disposition": "exclude",
            "confidence": 1.0,
            "reason": "The record is unrelated.",
        },
        "M002": {
            "disposition": "exclude",
            "confidence": 1.0,
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
    llm.call_structured.return_value = {"decisions": {}}

    selected = await AssistantContextSelector(llm).select(
        "Question",
        [AssistantContextCandidate("page:first", "wiki_page", "First", "One")],
    )

    assert selected == []
