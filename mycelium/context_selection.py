"""Structured semantic admission for assistant memory context."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from mycelium import prompts
from mycelium.budget import require_request_budget, ContextBudgetError
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import complementary_selection_model


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssistantContextCandidate:
    candidate_id: str
    kind: str
    title: str
    content: str


@dataclass(frozen=True)
class AssistantContextSelection:
    selected_ids: tuple[str, ...]
    decisions: dict[str, dict]
    error: str | None = None
    supported_aspects: tuple[str, ...] = ()
    remaining_gaps: tuple[str, ...] = ()


class AssistantContextSelector:
    """Admit only candidate records that can help with the current request."""

    def __init__(self, llm: OllamaClient) -> None:
        self.llm = llm

    async def select(
        self,
        query: str,
        candidates: list[AssistantContextCandidate],
    ) -> list[str]:
        result = await self.select_with_trace(query, candidates)
        return list(result.selected_ids)

    async def select_with_trace(
        self,
        query: str,
        candidates: list[AssistantContextCandidate],
    ) -> AssistantContextSelection:
        if not candidates:
            return AssistantContextSelection((), {})
        aliases = {
            f"M{index:03d}": candidate
            for index, candidate in enumerate(candidates, start=1)
        }
        rendered_records = []
        for alias, candidate in aliases.items():
            payload = {
                "kind": candidate.kind,
                "title": candidate.title,
                "content": candidate.content,
            }
            rendered_records.append(
                f"{alias}: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
            )
        rendered = "\n".join(rendered_records)
        system, user = prompts.assistant_context_selection_prompt(query, rendered)
        schema = complementary_selection_model(aliases)
        try:
            require_request_budget(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                context_window=self.llm.context_window_tokens, output_tokens=1024,
                schema=schema.model_json_schema(),
            )
        except ContextBudgetError:
            if len(candidates) > 1:
                midpoint = len(candidates) // 2
                left = await self.select_with_trace(query, candidates[:midpoint])
                right = await self.select_with_trace(query, candidates[midpoint:])
                return AssistantContextSelection(
                    (*left.selected_ids, *right.selected_ids),
                    {**left.decisions, **right.decisions},
                    "; ".join(error for error in (left.error, right.error) if error) or None,
                )
            return AssistantContextSelection((), {}, "A complete candidate exceeds the request budget")
        try:
            response = await self.llm.call_structured(
                system,
                user,
                schema,
                num_predict=1024,
                debug_label="assistant-context-selection",
            )
            decision = schema.model_validate(response).model_dump()
        except Exception as exc:
            logger.warning(
                "Assistant context selection failed closed: %s: %s",
                type(exc).__name__,
                exc,
            )
            return AssistantContextSelection(
                (), {}, f"{type(exc).__name__}: {exc}"
            )
        selected = tuple(aliases[alias].candidate_id for alias in decision["selected_ids"])
        return AssistantContextSelection(
            selected,
            {candidate.candidate_id: {"disposition": "include" if alias in decision["selected_ids"] else "exclude"}
             for alias, candidate in aliases.items()},
            supported_aspects=tuple(decision["supported_aspects"]),
            remaining_gaps=tuple(decision["remaining_gaps"]),
        )
