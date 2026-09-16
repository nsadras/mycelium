"""Explicit semantic decisions for truth pipeline mechanics tests."""

import json
from unittest.mock import AsyncMock

from mycelium.ollama import OllamaClient


def truth_response(user, schema, relations, *, debug_label, **kwargs):
    payload = json.loads(user.split("\n", 1)[1])
    if debug_label == "dream-truth-candidates":
        return {"decisions": {alias: {
            "candidates": {target: "compare" for target in targets},
            "reason": "Compare these fixture claims.",
        } for alias, targets in payload["eligible_candidates"].items()}}
    assert debug_label == "dream-truth-comparison"
    return {"comparisons": {alias: {
        "scope": "same", "relation": relations.get((pair["left"]["claim_id"], pair["right"]["claim_id"]), "no_change"),
        "reason": "Explicit fixture decision.",
    } for alias, pair in payload.items()}}


def truth_llm(relations):
    llm = OllamaClient("http://localhost:11434", "test", reasoning_enabled=False)

    async def respond(system, user, schema, **kwargs):
        return truth_response(user, schema, relations, **kwargs)

    llm.call_structured = AsyncMock(side_effect=respond)
    return llm
