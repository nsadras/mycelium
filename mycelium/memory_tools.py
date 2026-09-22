"""Bounded read-only memory tools for an assistant reasoning loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from mycelium.budget import count_tokens
from mycelium.memory_workspace import MemoryWorkspaceAccumulator, merge_memory_evidence
from mycelium.memory_tool_contracts import MemorySearchArguments, MemorySourcesArguments
from mycelium.ollama import ToolExecutionResult
from mycelium.operations import (
    MemoryEvidence,
    MemoryWorkspace,
    MemoryWorkspaceOperation,
    RetrievalError,
)
from mycelium.retrieval import MemoryRetriever
from mycelium.evidence_rendering import render_memory_search_result, render_memory_source_result, render_memory_tool_error, render_memory_workspace, render_memory_evidence
from mycelium.evidence_budget import fit_memory_evidence


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
                "pass its supporting claim IDs. Repeated reads advance through excerpts not already in the workspace."
            ),
            "parameters": MemorySourcesArguments.model_json_schema(),
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
            "parameters": MemorySearchArguments.model_json_schema(),
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
        request: str,
        initial_evidence: MemoryEvidence,
    ) -> None:
        self.retriever = retriever
        self.result_limit = max(1, min(6, result_limit))
        self.search_limit = max(1, search_limit)
        self.remaining_evidence_tokens = max(1, evidence_budget_tokens)
        self.returned_claim_ids = set(initial_evidence.claim_ids)
        self.search_count = 0
        self.workspace = MemoryWorkspaceAccumulator(
            request,
            initial_evidence,
            remaining_searches=self.search_limit,
            remaining_evidence_tokens=self.remaining_evidence_tokens,
        )
        self.workspace_budget_tokens = (
            count_tokens(render_memory_workspace(self.workspace.snapshot))
            + self.remaining_evidence_tokens
        )

    async def run(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> ToolExecutionResult | None:
        """Run a memory tool, or defer non-memory tools to the Ollama client."""
        if tool_name not in MEMORY_TOOL_NAMES:
            return None
        error = None
        try:
            if tool_name == "memory_search":
                parsed = MemorySearchArguments.model_validate(arguments)
                search_result = await self.search(
                    parsed.query, limit=min(parsed.limit, self.result_limit),
                )
                rendered = render_memory_search_result(
                    search_result.evidence,
                    query=search_result.query,
                    remaining_searches=search_result.remaining_searches,
                )
                result_evidence = search_result.evidence
            else:
                parsed = MemorySourcesArguments.model_validate(arguments)
                source_result = self.sources(parsed.claim_ids)
                rendered = render_memory_source_result(
                    source_result.evidence,
                    requested_claim_ids=list(source_result.claim_ids),
                )
                result_evidence = source_result.evidence
        except (TypeError, ValueError, RetrievalError) as exc:
            error = str(exc)
        try:
            self.workspace.evidence = self.retriever.refresh_evidence(
                self.workspace.evidence,
                budget_tokens=self.workspace_budget_tokens,
            )
        except (TypeError, ValueError, RetrievalError) as exc:
            # Never send a stale evidence snapshot after its canonical refresh fails.
            self.workspace.evidence = MemoryEvidence()
            error = f"{error}; workspace refresh failed: {exc}" if error else str(exc)
        if error is not None:
            rendered = render_memory_tool_error(error)
            workspace = self.workspace.record_failure(
                tool_name,
                arguments,
                error,
                remaining_searches=self.search_limit - self.search_count,
                remaining_evidence_tokens=self.remaining_evidence_tokens,
            )
            return self._execution_result(
                rendered, self._fit_workspace(), workspace.operations[-1]
            )
        workspace = self.workspace.record_success(
            tool_name,
            arguments,
            result_evidence,
            remaining_searches=self.search_limit - self.search_count,
            remaining_evidence_tokens=self.remaining_evidence_tokens,
        )
        return self._execution_result(
            rendered, self._fit_workspace(), workspace.operations[-1]
        )

    def _fit_workspace(self) -> MemoryWorkspace:
        """Bound diagnostics before admitting complete evidence, including on failure."""
        workspace = self.workspace.snapshot
        operations = list(workspace.operations)

        def fits(value):
            return (
                count_tokens(render_memory_workspace(value))
                <= self.workspace_budget_tokens
            )

        while len(operations) > 1 and not fits(
            replace(workspace, operations=tuple(operations))
        ):
            operations.pop(0)
        if operations and not fits(replace(workspace, operations=tuple(operations))):
            operations = [
                replace(
                    operations[0],
                    query=None,
                    requested_claim_ids=(),
                    added_record_ids=(),
                    added_source_ids=(),
                    error=None,
                )
            ]
        if not fits(replace(workspace, operations=tuple(operations))):
            operations = []
        workspace = replace(workspace, operations=tuple(operations))
        self.workspace.evidence = fit_memory_evidence(
            self.workspace.evidence,
            lambda trial: fits(replace(workspace, evidence=trial)),
        )
        return replace(workspace, evidence=self.workspace.evidence)

    @staticmethod
    def _execution_result(
        rendered: str, workspace: MemoryWorkspace, operation: MemoryWorkspaceOperation
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            result=rendered,
            model_result=render_memory_workspace(workspace),
            supersession_key="memory_workspace",
            superseded_result=(
                f'<memory-workspace-superseded revision="{workspace.revision}" />'
            ),
            metadata={
                "workspace_revision": workspace.revision,
                "workspace_operation": asdict(operation),
            },
        )

    async def search(
        self, query: str, *, limit: int | None = None
    ) -> MemorySearchToolResult:
        parsed = MemorySearchArguments.model_validate({
            "query": query, "limit": self.result_limit if limit is None else limit,
        })
        query = " ".join(parsed.query.split())
        if self.search_count >= self.search_limit:
            raise ValueError(
                "The memory search limit for this response has been reached."
            )
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
            limit=min(parsed.limit, self.result_limit),
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
        parsed = MemorySourcesArguments.model_validate({"claim_ids": claim_ids})
        permitted = parsed.claim_ids
        if not set(permitted) <= self.returned_claim_ids:
            raise ValueError(
                "memory_sources requires claim IDs already shown in this response"
            )
        if self.remaining_evidence_tokens <= 0:
            raise ValueError("The memory evidence budget has been exhausted.")

        envelope_tokens = count_tokens(
            render_memory_source_result(MemoryEvidence(), requested_claim_ids=permitted)
        )
        evidence_budget = self.remaining_evidence_tokens - envelope_tokens
        if evidence_budget <= 0:
            raise ValueError("The memory evidence budget has been exhausted.")
        evidence = self.retriever.source_evidence(
            permitted, budget_tokens=evidence_budget,
            known_evidence=self.workspace.evidence,
        )
        if not any(source.segments for source in evidence.sources):
            raise ValueError(
                "No additional source excerpts fit the remaining evidence budget."
                if evidence.more_available else
                "No additional source excerpts are available for these claims."
            )
        # Existing interpretation/citations are still carried by the workspace;
        # reading a source should spend the allowance on newly admitted evidence.
        used_tokens = max(0,
            count_tokens(render_memory_evidence(merge_memory_evidence(self.workspace.evidence, evidence)))
            - count_tokens(render_memory_evidence(self.workspace.evidence)))
        self.remaining_evidence_tokens = max(
            0, self.remaining_evidence_tokens - used_tokens
        )
        return MemorySourceToolResult(tuple(permitted), evidence)
