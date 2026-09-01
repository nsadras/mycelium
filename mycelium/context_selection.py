"""Structured semantic admission for assistant memory context."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from mycelium import prompts
from mycelium.budget import truncate_text_tokens
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import assistant_context_selection_output_model


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantContextCandidate:
    candidate_id: str
    kind: str
    title: str
    content: str


class AssistantContextSelector:
    """Admit only candidate records that can help with the current request."""

    def __init__(self, llm: OllamaClient) -> None:
        self.llm = llm

    async def select(
        self,
        query: str,
        candidates: list[AssistantContextCandidate],
    ) -> list[str]:
        if not candidates:
            return []
        aliases = {
            f"M{index:03d}": candidate
            for index, candidate in enumerate(candidates, start=1)
        }
        rendered = "\n".join(
            f"{alias}: {json.dumps({
                'kind': candidate.kind,
                'title': candidate.title,
                'content': truncate_text_tokens(candidate.content, 1200),
            }, ensure_ascii=False, sort_keys=True)}"
            for alias, candidate in aliases.items()
        )
        system, user = prompts.assistant_context_selection_prompt(query, rendered)
        schema = assistant_context_selection_output_model(aliases)
        try:
            response = await self.llm.call_structured(
                system,
                user,
                schema,
                num_predict=2048,
                debug_label="assistant-context-selection",
            )
            decisions = schema.model_validate(response).model_dump()["decisions"]
        except Exception as exc:
            logger.warning(
                "Assistant context selection failed closed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return []
        return [
            candidate.candidate_id
            for alias, candidate in aliases.items()
            if decisions[alias]["disposition"] == "include"
        ]
