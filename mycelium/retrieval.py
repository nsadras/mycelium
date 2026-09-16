"""Claim-first retrieval orchestration for an assistant turn."""

from __future__ import annotations

from mycelium.artifacts import ArtifactStore
from mycelium.budget import count_tokens
from mycelium.search_query import SearchQueryOutput
from mycelium.prompting import render_prompt
from mycelium.claim_index import LanceClaimIndex
from mycelium.context_selection import (
    AssistantContextCandidate,
    AssistantContextSelector,
)
from mycelium.ollama import OllamaClient
from mycelium.operations import (
    MemoryEvidence,
    RetrievalRequest,
    RetrievalResult,
    RetrievalError,
)
from mycelium.retrieval_context import RetrievedContextBuilder, render_memory_evidence
from mycelium.store import WikiStore
from mycelium.database import UnitOfWork
from mycelium.lifecycle_transaction import LifecycleTransaction


class MemoryRetriever:
    def __init__(
        self,
        llm: OllamaClient,
        wiki: WikiStore,
        artifacts: ArtifactStore,
        *,
        default_budget_tokens: int,
        claim_index: LanceClaimIndex,
        initial_result_limit: int = 5,
    ) -> None:
        self.llm = llm
        self.artifacts = artifacts
        self.default_budget_tokens = default_budget_tokens
        self.claim_index = claim_index
        self.initial_result_limit = initial_result_limit
        self.context_builder = RetrievedContextBuilder(wiki, artifacts)

    async def _search_query(self, query: str) -> str:
        # EmbeddingGemma has a smaller context than the chat model. Preserve the
        # original request for admission; formulate bounded search text when needed.
        if count_tokens(query) <= 1024:
            return query
        response = await self.llm.call_structured(
            render_prompt("assistant/search_query.system.jinja"),
            query,
            SearchQueryOutput,
            num_predict=512,
            debug_label="retrieval-query",
        )
        return SearchQueryOutput.model_validate(response).query

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        LifecycleTransaction(
            self.artifacts.root, self.context_builder.wiki.wiki_dir
        ).recover()
        budget_tokens = (
            request.budget_tokens
            if request.budget_tokens is not None
            else self.default_budget_tokens
        )
        try:
            search_query = await self._search_query(request.query)
        except Exception as exc:
            raise RetrievalError("query", str(exc)) from exc
        for attempt in range(2):
            try:
                hits = await self.claim_index.search(search_query)
            except Exception as exc:
                raise RetrievalError("search", str(exc)) from exc
            unit = UnitOfWork(self.artifacts.db)
            artifacts = ArtifactStore(self.artifacts.root, db=unit)
            builder = RetrievedContextBuilder(
                WikiStore(self.context_builder.wiki.wiki_dir, db=unit), artifacts
            )
            try:
                hits = [
                    current
                    for hit in hits
                    if (current := builder.current_hit(hit)) is not None
                ]
                candidates = [
                    AssistantContextCandidate(
                        candidate_id=f"claim:{hit.claim_id}",
                        kind=f"{hit.memory_tier}_claim",
                        title=hit.owner_title or "Unassigned memory",
                        content=builder.admission_content(hit),
                    )
                    for hit in hits
                ]
                selection = await AssistantContextSelector(self.llm).select_with_trace(
                    request.query, candidates
                )
                if selection.error:
                    raise RetrievalError("admission", selection.error)
                try:
                    unit.validate_reads()
                except ValueError as exc:
                    if attempt == 1:
                        raise RetrievalError("concurrent_update", str(exc)) from exc
                    continue
                break
            finally:
                unit.close()
        # No await after validation: rendering sees one event-loop-consistent state.
        builder = RetrievedContextBuilder(self.context_builder.wiki, self.artifacts)
        hits_by_id = {hit.claim_id: hit for hit in hits}
        admitted_hits = [
            hits_by_id[value.removeprefix("claim:")] for value in selection.selected_ids
        ]
        selected_hits = builder.distinct_hits(admitted_hits, self.initial_result_limit)
        evidence = builder.build(
            selected_hits,
            budget_tokens=budget_tokens,
            more_available=len(admitted_hits) > len(selected_hits),
        )
        rendered = render_memory_evidence(evidence)
        trace = {
            "strategy": "lancedb_hybrid_claims_then_model_admission",
            "search_query": search_query,
            "embedding_model": self.claim_index.embedder.model,
            "candidate_limit": self.claim_index.candidate_limit,
            "candidates": [
                {
                    "rank": rank,
                    "claim_id": hit.claim_id,
                    "memory_tier": hit.memory_tier,
                    "owner_entity_id": hit.owner_entity_id,
                    "score": hit.score,
                    "decision": selection.decisions.get(f"claim:{hit.claim_id}"),
                }
                for rank, hit in enumerate(hits, start=1)
            ],
            "selected_claim_ids": [hit.claim_id for hit in selected_hits],
            "admitted_claim_ids": [hit.claim_id for hit in admitted_hits],
            "rendered_claim_ids": [
                hit.claim_id
                for hit in selected_hits
                if hit.claim_id in evidence.claim_ids
            ],
            "selection_error": selection.error,
            "supported_aspects": list(selection.supported_aspects),
            "remaining_gaps": list(selection.remaining_gaps),
        }
        return RetrievalResult(
            builder.page_references(evidence), evidence, rendered, trace
        )

    async def search_evidence(
        self,
        query: str,
        *,
        limit: int,
        budget_tokens: int,
        exclude_claim_ids: set[str] | None = None,
    ) -> RetrievalResult:
        """Return additional ranked evidence without a separate model gate."""
        LifecycleTransaction(
            self.artifacts.root, self.context_builder.wiki.wiki_dir
        ).recover()
        builder = RetrievedContextBuilder(self.context_builder.wiki, self.artifacts)
        excluded = exclude_claim_ids or set()
        try:
            hits = await self.claim_index.search(
                await self._search_query(query), limit=limit + len(excluded)
            )
        except Exception as exc:
            raise RetrievalError("search", str(exc)) from exc
        available_hits = [
            current
            for hit in hits
            if hit.claim_id not in excluded
            and (current := builder.current_hit(hit)) is not None
        ]
        selected_hits = builder.distinct_hits(available_hits, limit)
        evidence = builder.build(
            selected_hits,
            budget_tokens=budget_tokens,
            more_available=len(available_hits) > len(selected_hits),
        )
        return RetrievalResult(
            builder.page_references(evidence),
            evidence,
            render_memory_evidence(evidence),
            {
                "strategy": "agent_memory_search",
                "query": query,
                "candidate_claim_ids": [hit.claim_id for hit in hits],
                "returned_claim_ids": [
                    hit.claim_id
                    for hit in selected_hits
                    if hit.claim_id in evidence.claim_ids
                ],
            },
        )

    def source_evidence(
        self, claim_ids: list[str], *, budget_tokens: int
    ) -> MemoryEvidence:
        return RetrievedContextBuilder(
            self.context_builder.wiki, self.artifacts
        ).source_evidence(claim_ids, budget_tokens=budget_tokens)

    def refresh_evidence(
        self, evidence: MemoryEvidence, *, budget_tokens: int
    ) -> MemoryEvidence:
        """Rebase a workspace on current canonical state before a tool result."""
        from dataclasses import replace

        builder = RetrievedContextBuilder(self.context_builder.wiki, self.artifacts)
        hits = []
        claim_ids = dict.fromkeys(
            [
                *evidence.claim_ids,
                *(
                    citation.claim_id
                    for source in evidence.sources
                    for citation in source.citations
                ),
            ]
        )
        for claim_id in claim_ids:
            try:
                claim = self.artifacts.get_claim(claim_id)
            except FileNotFoundError:
                continue
            if claim.status not in {"active", "superseded"}:
                continue
            from mycelium.claim_index import ClaimSearchHit

            hits.append(
                ClaimSearchHit(
                    claim_id, claim.text, claim.status, None, None, None, None, None
                )
            )
        records = builder.build(hits, budget_tokens=budget_tokens)
        from mycelium.retrieval_context import fit_memory_evidence

        return fit_memory_evidence(
            replace(
                records,
                sources=builder.refresh_sources(evidence.sources),
                more_available=evidence.more_available or records.more_available,
            ),
            lambda trial: count_tokens(render_memory_evidence(trial)) <= budget_tokens,
        )
