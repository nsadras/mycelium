from pathlib import Path
from typing import List, Optional, Literal, cast
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from mycelium.models import WikiPage, DreamReport
from mycelium.store import WikiStore, LogStore
from mycelium.config import Config
from mycelium.ollama import OllamaClient
from mycelium.encoder import Encoder
from mycelium.budget import count_tokens
from mycelium.context import render_memory_context
from mycelium.session import Session
from mycelium.facts import routing_recall_index
from mycelium.sources import source_contexts_for_pages
from mycelium.page_search import PageSearchIndex
from mycelium.memory_tools import MemoryToolset
from mycelium.short_term import ShortTermMemoryQueue, ShortTermMemoryStatus
from mycelium.artifacts import (
    ArtifactStore,
    SourceSegment,
    query_temporal_record,
    temporal_intervals_overlap,
    temporal_record,
)

class Mycelium:
    def __init__(
        self,
        store_path: str | Path,
        ollama_model: str = 'gemma3:12b',
        ollama_url: str = 'http://localhost:11434',
        context_budget_tokens: int = 32768,
        config_path: str | Path | None = None,
        memory_profile: Literal["user", "none"] = "user",
    ):
        self.store_path = Path(store_path)
        
        if config_path and Path(config_path).exists():
            self.config = Config.from_toml(Path(config_path))
        else:
            self.config = Config.defaults()
            self.config.llm.model = ollama_model
            self.config.llm.url = ollama_url
            self.config.context_budget_tokens = context_budget_tokens

        self._init_store()
            
        self._wiki = WikiStore(self.store_path / "wiki")
        self._log_store = LogStore(self.store_path / "logs")
        self.artifacts = ArtifactStore(self.store_path / "artifacts")
        self._page_search = PageSearchIndex()
        self._ensure_seed_profile(memory_profile)
        self.llm = OllamaClient(
            url=self.config.llm.url,
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
            timeout=self.config.llm.timeout_seconds,
            context_window_tokens=self.config.llm.context_window_tokens,
        )
        self.encoder = Encoder(self.llm, self._log_store, self.config, self.artifacts)
        self.short_term_memory = ShortTermMemoryQueue(
            self.artifacts, self.config.dream
        )
        
        from mycelium.dream import DreamProcess
        self.dream_process = DreamProcess(self.llm, self._wiki, self._log_store, self.config, self.artifacts)

    def _ensure_seed_profile(self, memory_profile: Literal["user", "none"]) -> None:
        if memory_profile == "none":
            return

        try:
            entity = self.artifacts.get_entity("you")
        except FileNotFoundError:
            entity = self.artifacts.create_entity("you", "You")
        slug = entity.slug
        title = "You"
        content = (
            "## Profile\n"
            "\n_No personal facts recorded yet._\n\n"
            "## Memory Map\n"
            "\n_No focused pages yet._\n"
        )
        tags = ["profile", "personalization"]
        summary = "Central repository for user preferences, background, plans, and custom instructions."

        if not self._wiki.exists(slug):
            from mycelium.models import WikiPage
            from datetime import datetime
            
            profile_page = WikiPage(
                slug=slug,
                title=title,
                content=content,
                created=datetime.now(),
                last_updated=datetime.now(),
                version=1,
                confidence=0.8,
                importance=1.0,
                page_type="you",
                tags=tags,
                related=[],
                entity_id=entity.entity_id,
                entity_status=cast(
                    Literal["active", "archived", "merged"], entity.status
                ),
                aliases=entity.aliases,
                sections=[],
            )
            self._wiki.save(profile_page)
            
            # Register in the index if not present
            index_content = self._wiki.get_index()
            if f"[[{slug}]]" not in index_content:
                lines = index_content.splitlines()
                pages_header_idx = -1
                for idx, line in enumerate(lines):
                    if line.strip().startswith("## Pages"):
                        pages_header_idx = idx
                        break
                
                profile_line = f"- [[{slug}]]: {summary}"
                if pages_header_idx != -1:
                    lines.insert(pages_header_idx + 1, profile_line)
                else:
                    lines.append(profile_line)
                self._wiki.save_index("\n".join(lines))

    def _ensure_user_profile(self) -> None:
        self._ensure_seed_profile("user")

    def _init_store(self) -> None:
        self.store_path.mkdir(parents=True, exist_ok=True)
        (self.store_path / "wiki").mkdir(exist_ok=True)
        (self.store_path / "logs").mkdir(exist_ok=True)
        (self.store_path / "artifacts").mkdir(exist_ok=True)
        (self.store_path / "wiki" / "_archive").mkdir(exist_ok=True)
        
        index_path = self.store_path / "wiki" / "_index.md"
        if not index_path.exists():
            with open(index_path, "w", encoding="utf-8") as f:
                f.write("# Wiki Index\n\n_last updated: never_\n\n## Pages\n")

    @property
    def wiki(self) -> WikiStore:
        return self._wiki

    @property
    def log_store(self) -> LogStore:
        return self._log_store

    async def load_context(
        self,
        query: str,
        budget_tokens: Optional[int] = None,
        session_id: Optional[str] = None,
        query_time: datetime | None = None,
    ) -> List[WikiPage]:
        
        budget_tokens = budget_tokens or self.config.context_budget_tokens
        
        pages = self.wiki.list_all()
        loaded_pages: list[WikiPage] = []

        # Short-term claims are queryable immediately but are explicitly kept
        # separate from the canonical wiki until Dream places them.
        recent_results = MemoryToolset(self.artifacts).search(
            query, limit=8, memory_tier="short_term"
        )
        if recent_results:
            lines = [
                "These source-grounded claims are recent and unconsolidated. Treat them as",
                "available episodic memory, not as a polished or conflict-resolved wiki summary.",
                "",
                *[
                    f"- [{item['consolidation_status']}] {item['text']} "
                    f"(claim: {item['claim_id']})"
                    for item in recent_results
                ],
            ]
            content = "\n".join(lines)
            recent_page = WikiPage(
                slug="_short-term-memory",
                title="Recent, unconsolidated memory",
                content=content,
                created=datetime.now().astimezone(),
                last_updated=datetime.now().astimezone(),
                version=1,
                confidence=0.7,
                importance=0.9,
                page_type=None,
                tags=["short-term-memory"],
                entity_id="_short-term-memory",
            )
            if count_tokens(render_memory_context([recent_page])) <= budget_tokens:
                loaded_pages.append(recent_page)

        selection_priorities = {
            hit.slug: rank
            for rank, hit in enumerate(
                self._page_search.search(pages, query, limit=2), start=1
            )
        }

        query_temporal = query_temporal_record(
            query, query_time or datetime.now().astimezone()
        )
        temporal_source_ids: set[str] = set()
        if query_temporal and query_temporal.get("start"):
            for claim in self.artifacts.list_claims(status="active"):
                claim_temporal = temporal_record(claim.facets)
                if claim_temporal is None:
                    continue
                requested_role = query_temporal.get("role")
                if requested_role == "deadline" and claim_temporal.get("role") != "deadline":
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
                        selection_priorities[entity.slug] = 0
                temporal_source_ids.update(
                    provenance.raw_log_entry_id
                    for provenance in claim.provenance
                    if provenance.raw_log_entry_id
                )

        # Explicit page names augment the lexical candidates. Keeping this
        # decision separate from BM25 prevents a named participant from
        # displacing the page that best matches the question's subject.
        import re
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        exclude_words = {"person", "place", "event", "topic", "project", "meeting", "convo", "chat", "page", "new"}

        existing_slugs = {p.slug: p for p in pages}
        selected_slugs = set(selection_priorities)

        for slug, page in existing_slugs.items():
            if slug in selected_slugs or "derived-memory" in page.tags:
                continue
            slug_parts = set(slug.split("-")) - exclude_words
            title_words = set(re.findall(r'\b\w+\b', page.title.lower())) - exclude_words
            if (slug_parts & query_words) or (title_words & query_words):
                selection_priorities[slug] = 8

        selections = sorted(
            ((priority, slug) for slug, priority in selection_priorities.items()),
            key=lambda item: (item[0], item[1]),
        )

        for priority, slug in selections:
            if not self.wiki.exists(slug):
                continue
                
            page = self.wiki.get(slug)
            if count_tokens(
                render_memory_context([*loaded_pages, page])
            ) <= budget_tokens:
                loaded_pages.append(page)

        source_contexts = source_contexts_for_pages(
            loaded_pages,
            self.log_store,
            query,
            preferred_entry_ids=temporal_source_ids,
        )
        for page in loaded_pages:
            source_context = source_contexts.get(page.slug, "")
            if not source_context:
                continue
            page.source_context = source_context
            if count_tokens(render_memory_context(loaded_pages)) > budget_tokens:
                page.source_context = ""
                
        return loaded_pages

    def _routing_index(self) -> str:
        base_index = self.wiki.get_index()
        pages = self.wiki.list_all()
        if not pages:
            return base_index

        metadata_lines = [
            "## Page Metadata",
            *[
                (
                    f"- [[{p.slug}]]: confidence={p.confidence:.2f}; "
                    f"importance={p.importance:.2f}"
                )
                for p in pages
            ],
        ]
        recall_index = routing_recall_index(pages)
        parts = [base_index, "\n".join(metadata_lines)]
        if recall_index:
            parts.append(recall_index)
        return "\n\n".join(parts)

    @asynccontextmanager
    async def session(self, query: str, session_id: Optional[str] = None):
        session_id = session_id or str(uuid.uuid4())
        
        sess = Session(mycelium=self, session_id=session_id, query=query)
        sess.loaded_pages = await self.load_context(query, session_id=session_id)
        
        try:
            yield sess
        finally:
            if sess.transcript:
                transcript_str = "\n".join(
                    f"[{msg['timestamp']}] {msg['role'].upper()}: {msg['content']}"
                    for msg in sess.transcript
                )
                segments = [
                    SourceSegment(
                        segment_id="",
                        index=index,
                        speaker=msg["role"],
                        role=msg["role"],
                        content=msg["content"],
                        timestamp=msg["timestamp"],
                    )
                    for index, msg in enumerate(sess.transcript)
                ]
                await self.encoder.encode_session(
                    transcript_str,
                    session_id,
                    occurred_at=segments[0].timestamp,
                    segments=segments,
                )
            
    def short_term_memory_status(
        self, *, now: datetime | None = None
    ) -> ShortTermMemoryStatus:
        return self.short_term_memory.status(now=now)

    async def dream(
        self, *, dry_run: bool = False, include_deferred: bool = True
    ) -> DreamReport:
        return await self.dream_process.run(
            dry_run=dry_run, include_deferred=include_deferred
        )

    async def dream_if_ready(
        self, *, now: datetime | None = None, dry_run: bool = False
    ) -> DreamReport | None:
        status = self.short_term_memory_status(now=now)
        if not status.ready:
            return None
        return await self.dream_process.run(
            dry_run=dry_run,
            include_deferred=status.include_deferred,
        )
