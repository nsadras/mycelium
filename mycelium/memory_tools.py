"""Bounded read-only memory tools for an assistant reasoning loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mycelium.budget import count_tokens
from mycelium.operations import MemoryEvidence
from mycelium.retrieval import MemoryRetriever
from mycelium.retrieval_context import (
    render_memory_search_result,
    render_memory_source_result,
    render_memory_tool_error,
)


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


@dataclass(frozen=True)
class MemorySearchToolResult:
    query: str
    evidence: MemoryEvidence
    remaining_searches: int


@dataclass(frozen=True)
class MemorySourceToolResult:
    claim_ids: tuple[str, ...]
    evidence: MemoryEvidence


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
                return render_memory_search_result(
                    result.evidence,
                    query=result.query,
                    remaining_searches=result.remaining_searches,
                )
            else:
                result = self.sources(_string_list(arguments.get("claim_ids"), limit=6))
                return render_memory_source_result(
                    result.evidence,
                    requested_claim_ids=list(result.claim_ids),
                )
        except (TypeError, ValueError) as exc:
            return render_memory_tool_error(str(exc))

    async def search(
        self, query: str, *, limit: int | None = None
    ) -> MemorySearchToolResult:
        query = " ".join(query.split()).strip()
        if not query:
            raise ValueError("memory_search requires a nonempty query")
        if self.search_count >= self.search_limit:
            raise ValueError("The memory search limit for this response has been reached.")
        if self.remaining_evidence_tokens <= 0:
            raise ValueError("The memory evidence budget has been exhausted.")

        remaining_searches = self.search_limit - (self.search_count + 1)
        envelope_tokens = count_tokens(
            render_memory_search_result(
                MemoryEvidence(),
                query=query,
                remaining_searches=remaining_searches,
            )
        )
        evidence_budget = self.remaining_evidence_tokens - envelope_tokens
        if evidence_budget <= 0:
            raise ValueError("The memory evidence budget has been exhausted.")
        self.search_count += 1
        result = await self.retriever.search_evidence(
            query,
            limit=limit or self.result_limit,
            budget_tokens=evidence_budget,
            exclude_claim_ids=set(self.returned_claim_ids),
        )
        returned_ids = list(result.evidence.claim_ids)
        self.returned_claim_ids.update(returned_ids)
        rendered_result = render_memory_search_result(
            result.evidence,
            query=query,
            remaining_searches=remaining_searches,
        )
        used_tokens = count_tokens(rendered_result)
        self.remaining_evidence_tokens = max(
            0, self.remaining_evidence_tokens - used_tokens
        )
        return MemorySearchToolResult(
            query=query,
            evidence=result.evidence,
            remaining_searches=remaining_searches,
        )

    def sources(self, claim_ids: list[str]) -> MemorySourceToolResult:
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
            raise ValueError("The memory evidence budget has been exhausted.")

        envelope_tokens = count_tokens(
            render_memory_source_result(
                MemoryEvidence(), requested_claim_ids=permitted
            )
        )
        evidence_budget = self.remaining_evidence_tokens - envelope_tokens
        if evidence_budget <= 0:
            raise ValueError("The memory evidence budget has been exhausted.")
        evidence = self.retriever.source_evidence(
            permitted, budget_tokens=evidence_budget
        )
        rendered_evidence = render_memory_source_result(
            evidence, requested_claim_ids=permitted
        )
        used_tokens = count_tokens(rendered_evidence)
        self.remaining_evidence_tokens = max(
            0, self.remaining_evidence_tokens - used_tokens
        )
        return MemorySourceToolResult(tuple(permitted), evidence)


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    return max(low, min(high, parsed))


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [rendered for item in value[:limit] if (rendered := str(item).strip())]
