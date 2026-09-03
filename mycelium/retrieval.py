"""Read-only retrieval of source-grounded memory for an assistant turn."""

from __future__ import annotations

from datetime import datetime

from mycelium.artifacts import (
    ArtifactStore,
    query_temporal_record,
    temporal_intervals_overlap,
    temporal_record,
)
from mycelium.budget import count_tokens
from mycelium.context import render_memory_context
from mycelium.context_selection import AssistantContextCandidate, AssistantContextSelector
from mycelium.memory_tools import MemoryToolset
from mycelium.models import WikiPage
from mycelium.ollama import OllamaClient
from mycelium.operations import RetrievalRequest, RetrievalResult
from mycelium.page_search import PageSearchIndex
from mycelium.sources import source_contexts_for_pages
from mycelium.store import LogStore, WikiStore


class MemoryRetriever:
    def __init__(
        self,
        llm: OllamaClient,
        wiki: WikiStore,
        logs: LogStore,
        artifacts: ArtifactStore,
        *,
        default_budget_tokens: int,
    ) -> None:
        self.llm = llm
        self.wiki = wiki
        self.logs = logs
        self.artifacts = artifacts
        self.default_budget_tokens = default_budget_tokens
        self.page_search = PageSearchIndex()

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        budget_tokens = request.budget_tokens or self.default_budget_tokens
        pages = self.wiki.list_all()
        loaded_pages: list[WikiPage] = []

        recent_results = MemoryToolset(self.artifacts).search(
            request.query, limit=8, memory_tier="short_term"
        )
        page_candidate_slugs = [
            hit.slug for hit in self.page_search.search(
                pages, request.query, limit=8
            )
        ]

        query_temporal = query_temporal_record(
            request.query, request.query_time or datetime.now().astimezone()
        )
        temporal_source_ids: set[str] = set()
        if query_temporal and query_temporal.get("start"):
            for claim in self.artifacts.list_claims(status="active"):
                claim_temporal = temporal_record(claim.facets)
                if claim_temporal is None:
                    continue
                requested_role = query_temporal.get("role")
                if (
                    requested_role == "deadline"
                    and claim_temporal.get("role") != "deadline"
                ):
                    continue
                if not temporal_intervals_overlap(query_temporal, claim_temporal):
                    continue
                placement = self.artifacts.placement_for_claim(claim.claim_id)
                if placement and placement.owner_entity_id:
                    try:
                        entity = self.artifacts.get_entity(placement.owner_entity_id)
                    except FileNotFoundError:
                        entity = None
                    if entity and self.wiki.exists(entity.slug):
                        if entity.slug not in page_candidate_slugs:
                            page_candidate_slugs.insert(0, entity.slug)
                temporal_source_ids.update(
                    provenance.raw_log_entry_id
                    for provenance in claim.provenance
                    if provenance.raw_log_entry_id
                )

        pages_by_slug = {page.slug: page for page in pages}
        candidates = [
            AssistantContextCandidate(
                candidate_id=f"claim:{item['claim_id']}",
                kind="short_term_claim",
                title=item["claim_id"],
                content=item["text"],
            )
            for item in recent_results
        ]
        candidates.extend(
            AssistantContextCandidate(
                candidate_id=f"page:{slug}",
                kind="wiki_page",
                title=pages_by_slug[slug].title,
                content=render_memory_context([pages_by_slug[slug]]),
            )
            for slug in page_candidate_slugs
            if slug in pages_by_slug
        )
        selected_ids = set(await AssistantContextSelector(self.llm).select(
            request.query, candidates
        ))

        selected_recent = [
            item for item in recent_results
            if f"claim:{item['claim_id']}" in selected_ids
        ]
        if selected_recent:
            lines = [
                "These source-grounded claims are recent and unconsolidated. Treat them as",
                "available episodic memory, not as a polished or conflict-resolved wiki summary.",
                "",
                *[
                    f"- [{item['consolidation_status']}] {item['text']} "
                    f"(claim: {item['claim_id']})"
                    for item in selected_recent
                ],
            ]
            recent_page = WikiPage(
                slug="_short-term-memory",
                title="Recent, unconsolidated memory",
                content="\n".join(lines),
                created=datetime.now().astimezone(),
                last_updated=datetime.now().astimezone(),
                version=1,
                page_type=None,
                tags=["short-term-memory"],
                entity_id="_short-term-memory",
            )
            if count_tokens(render_memory_context([recent_page])) <= budget_tokens:
                loaded_pages.append(recent_page)

        for slug in page_candidate_slugs:
            if f"page:{slug}" not in selected_ids or not self.wiki.exists(slug):
                continue
            page = self.wiki.get(slug)
            if count_tokens(
                render_memory_context([*loaded_pages, page])
            ) <= budget_tokens:
                loaded_pages.append(page)

        source_contexts = source_contexts_for_pages(
            loaded_pages,
            self.logs,
            request.query,
            preferred_entry_ids=temporal_source_ids,
        )
        for page in loaded_pages:
            source_context = source_contexts.get(page.slug, "")
            if not source_context:
                continue
            page.source_context = source_context
            if count_tokens(render_memory_context(loaded_pages)) > budget_tokens:
                page.source_context = ""

        return RetrievalResult(
            pages=tuple(loaded_pages),
            rendered_context=render_memory_context(loaded_pages),
        )
