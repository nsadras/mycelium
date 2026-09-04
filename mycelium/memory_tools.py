"""Bounded read-only memory tools for an assistant reasoning loop."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from mycelium.budget import count_tokens
from mycelium.retrieval import MemoryRetriever


MEMORY_TOOL_NAMES = frozenset({"memory_search", "memory_sources"})

MEMORY_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "memory_sources",
            "description": (
                "Retrieve the exact cited source lines and nearby dialogue underlying claim IDs "
                "shown in the initial evidence or memory_search results. Use this to inspect an "
                "existing relevant or potentially related record when original wording, "
                "attribution, chronology, or relationships could affect the response. For a fact, "
                "pass its supporting claim IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 6,
                    },
                },
                "required": ["claim_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": (
                "Search long-term memory for additional structured claim or fact records. Use this "
                "to discover records when the evidence currently available does not point to the "
                "missing information. Previously returned claims are omitted so distinct queries "
                "can explore other aspects."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A focused description of the memory to find.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 6,
                        "description": "Maximum number of new memory records to return.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


class MemoryToolset:
    """Execute one request's bounded, cumulative memory exploration."""

    def __init__(
        self,
        retriever: MemoryRetriever,
        *,
        result_limit: int = 6,
        search_limit: int = 3,
        evidence_budget_tokens: int = 6000,
        initial_claim_ids: list[str] | tuple[str, ...] = (),
    ) -> None:
        self.retriever = retriever
        self.result_limit = max(1, min(6, result_limit))
        self.search_limit = max(1, search_limit)
        self.remaining_evidence_tokens = max(1, evidence_budget_tokens)
        self.returned_claim_ids = set(initial_claim_ids)
        self.search_count = 0

    async def run(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        """Run a memory tool, or defer non-memory tools to the Ollama client."""
        if tool_name not in MEMORY_TOOL_NAMES:
            return None
        try:
            if tool_name == "memory_search":
                result = await self.search(
                    str(arguments.get("query") or ""),
                    limit=_bounded_int(
                        arguments.get("limit"),
                        default=self.result_limit,
                        low=1,
                        high=self.result_limit,
                    ),
                )
            else:
                result = self.sources(_string_list(arguments.get("claim_ids"), limit=6))
            return json.dumps(result, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    async def search(self, query: str, *, limit: int | None = None) -> dict[str, Any]:
        query = " ".join(query.split()).strip()
        if not query:
            raise ValueError("memory_search requires a nonempty query")
        if self.search_count >= self.search_limit:
            return {
                "error": "The memory search limit for this response has been reached.",
                "search_limit": self.search_limit,
            }
        if self.remaining_evidence_tokens <= 0:
            return {"error": "The memory evidence budget has been exhausted."}

        self.search_count += 1
        result = await self.retriever.search_evidence(
            query,
            limit=limit or self.result_limit,
            budget_tokens=self.remaining_evidence_tokens,
            exclude_claim_ids=set(self.returned_claim_ids),
        )
        returned_ids = list(result.evidence.claim_ids)
        self.returned_claim_ids.update(returned_ids)
        used_tokens = count_tokens(result.rendered_context)
        self.remaining_evidence_tokens = max(
            0, self.remaining_evidence_tokens - used_tokens
        )
        return {
            "query": query,
            "claim_ids": returned_ids,
            "memory_evidence": asdict(result.evidence),
            "remaining_searches": self.search_limit - self.search_count,
            "remaining_evidence_tokens": self.remaining_evidence_tokens,
        }

    def sources(self, claim_ids: list[str]) -> dict[str, Any]:
        if not claim_ids:
            raise ValueError("memory_sources requires at least one claim ID")
        permitted = [
            claim_id
            for claim_id in dict.fromkeys(claim_ids)
            if claim_id in self.returned_claim_ids
        ]
        if not permitted:
            raise ValueError(
                "memory_sources requires claim IDs already shown in this response"
            )
        if self.remaining_evidence_tokens <= 0:
            return {"error": "The memory evidence budget has been exhausted."}

        evidence = self.retriever.source_evidence(
            permitted, budget_tokens=self.remaining_evidence_tokens
        )
        rendered_evidence = json.dumps(asdict(evidence), ensure_ascii=False)
        used_tokens = count_tokens(rendered_evidence)
        self.remaining_evidence_tokens = max(
            0, self.remaining_evidence_tokens - used_tokens
        )
        return {
            "claim_ids": permitted,
            "memory_evidence": asdict(evidence),
            "remaining_evidence_tokens": self.remaining_evidence_tokens,
        }


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    return max(low, min(high, parsed))


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [rendered for item in value[:limit] if (rendered := str(item).strip())]
