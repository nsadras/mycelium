from pathlib import Path
from typing import List, Optional, Literal
import uuid

from mycelium.models import WikiPage, DreamReport
from mycelium.store import WikiStore, LogStore
from mycelium.config import Config
from mycelium.ollama import OllamaClient
from mycelium.encoder import Encoder
from mycelium.budget import ContextBudget
from mycelium.session import Session
from mycelium import prompts
from mycelium.facts import page_recall_context, routing_recall_index
from mycelium.sources import source_contexts_for_pages
from mycelium.structured_outputs import RoutingOutput
from mycelium.artifacts import ArtifactStore

class Mycelium:
    def __init__(
        self,
        store_path: str | Path,
        ollama_model: str = 'gemma3:12b',
        ollama_url: str = 'http://localhost:11434',
        context_budget_tokens: int = 32768,
        lability_threshold: float = 0.35,
        conflict_policy: Literal['fork', 'override', 'merge'] = 'override',
        config_path: str | Path | None = None,
        memory_profile: Literal["user", "none"] = "user",
        evidence_mode: Literal["raw", "claims", "hybrid"] | None = None,
    ):
        self.store_path = Path(store_path)
        
        if config_path and Path(config_path).exists():
            self.config = Config.from_toml(Path(config_path))
        else:
            self.config = Config.defaults()
            self.config.llm.model = ollama_model
            self.config.llm.url = ollama_url
            self.config.context_budget_tokens = context_budget_tokens
            self.config.reconsolidation.lability_threshold = lability_threshold
            self.config.dream.conflict_policy = conflict_policy

        if evidence_mode is not None:
            self.config.dream.evidence_mode = evidence_mode

        self._init_store()
            
        self._wiki = WikiStore(self.store_path / "wiki")
        self._log_store = LogStore(self.store_path / "logs")
        self.artifacts = ArtifactStore(self.store_path / "artifacts")
        self._ensure_seed_profile(memory_profile)
        self.llm = OllamaClient(
            url=self.config.llm.url,
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
            timeout=self.config.llm.timeout_seconds,
            context_window_tokens=self.config.llm.context_window_tokens,
        )
        from mycelium.reconsolidation import ReconsolidationEngine
        self.reconsolidation_engine = ReconsolidationEngine(self.llm, self._wiki, self.config)
        self.encoder = Encoder(self.llm, self._log_store, self.config, self.artifacts)
        
        from mycelium.dream import DreamProcess
        self.dream_process = DreamProcess(self.llm, self._wiki, self._log_store, self.config, self.artifacts)

    def _ensure_seed_profile(self, memory_profile: Literal["user", "none"]) -> None:
        if memory_profile == "none":
            return

        slug = "user-profile"
        title = "User Profile"
        content = (
            "Central repository for user preferences, background, plans, and custom instructions.\n\n"
            "## Key Facts\n"
            "- The page tracks durable user-specific details and preferences.\n\n"
            "## Event Timeline\n"
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
                tags=tags,
                related=[]
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
        (self.store_path / "labile").mkdir(exist_ok=True)
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
        reconsolidate: bool = True,
        session_id: Optional[str] = None
    ) -> List[WikiPage]:
        
        budget_tokens = budget_tokens or self.config.context_budget_tokens
        budget = ContextBudget(budget_tokens)
        
        if not self.wiki.list_all():
            return []

        index_content = self._routing_index()
        budget.consume(index_content)
        
        if budget.remaining() <= 0:
            return []
            
        system, user = prompts.routing_prompt(index_content, query, budget.remaining())
        response = await self.llm.call_structured(system, user, RoutingOutput)
        if not isinstance(response, list):
            response = [response] if isinstance(response, dict) else []
            
        selections = []
        for item in response:
            if isinstance(item, dict) and "page" in item:
                priority = int(item.get("priority", 5))
                page_slug = item["page"].strip()
                if page_slug.startswith("[[") and page_slug.endswith("]]"):
                    page_slug = page_slug[2:-2]
                page_slug = page_slug.replace(".md", "").strip().lower()
                selections.append((priority, page_slug))
                
        # Entity-aware fallback: if a known entity/page matches the query, load it
        import re
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        exclude_words = {"person", "place", "event", "topic", "project", "meeting", "convo", "chat", "page", "new"}
        
        existing_slugs = {p.slug: p for p in self.wiki.list_all()}
        selected_slugs = {slug for _, slug in selections}
        
        for slug, p in existing_slugs.items():
            if slug in selected_slugs:
                continue
            # Derived timeline/detail/archive pages should be selected explicitly
            # by the router. Loading every child merely because its parent entity
            # appears in the query recreates the original monolithic context.
            if "derived-memory" in p.tags:
                continue
            slug_parts = set(slug.split("-")) - exclude_words
            title_words = set(re.findall(r'\b\w+\b', p.title.lower())) - exclude_words
            
            # Match if slug parts or title words are in the query
            if (slug_parts & query_words) or (title_words & query_words):
                selections.append((8, slug))

        selections.sort(key=lambda x: x[0])
        
        loaded_pages = []
        for priority, slug in selections:
            if not self.wiki.exists(slug):
                continue
                
            page = self.wiki.get(slug)
            recall_context = page_recall_context(page)
            recall_block = f"{recall_context}\n\n" if recall_context else ""
            content = (
                f"=== MEMORY: {page.title} "
                f"(confidence: {page.confidence:.2f}, v{page.version}) ===\n"
                f"{recall_block}{page.content}\n=== END MEMORY ==="
            )
            
            if budget.fits(content):
                budget.consume(content)
                if reconsolidate and self.config.reconsolidation.check_on_load:
                    error = await self.reconsolidation_engine.check(page, query)
                    if error.discrepancy_score > self.config.reconsolidation.lability_threshold:
                        page.was_flagged = True
                        page.discrepancy_score = error.discrepancy_score
                        page.discrepancy_explanation = error.explanation
                        if session_id:
                            await self.reconsolidation_engine.flag_labile(page, session_id)
                            await self.reconsolidation_engine.accumulate_signal(page.slug, session_id, error)
                            
                loaded_pages.append(page)

        source_contexts = source_contexts_for_pages(loaded_pages, self.log_store, query)
        for page in loaded_pages:
            source_context = source_contexts.get(page.slug, "")
            if source_context and budget.fits(source_context):
                budget.consume(source_context)
                page.source_context = source_context
                
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

    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def session(self, query: str, session_id: Optional[str] = None):
        session_id = session_id or str(uuid.uuid4())
        
        sess = Session(mycelium=self, session_id=session_id, query=query)
        sess.loaded_pages = await self.load_context(query, session_id=session_id)
        
        try:
            yield sess
        finally:
            if sess.transcript:
                transcript_str = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in sess.transcript])
                await self.encoder.encode_session(transcript_str, session_id)
            
            await self.reconsolidation_engine.resolve_labile_pages(session_id)
            
    async def dream(self, **kwargs) -> DreamReport:
        kwargs.setdefault('conflict_policy', self.config.dream.conflict_policy)
        return await self.dream_process.run(**kwargs)

    async def compact(self, slugs: list[str] | None = None, **kwargs) -> DreamReport:
        """Run a compaction pass that fully rewrites wiki pages to deduplicate and reorganize."""
        return await self.dream_process.compact(slugs=slugs, **kwargs)
