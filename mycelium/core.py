from pathlib import Path
from typing import Optional, Literal, cast
import uuid
from contextlib import asynccontextmanager

from mycelium.store import WikiStore, LogStore
from mycelium.config import Config
from mycelium.ollama import OllamaClient
from mycelium.encoder import Encoder
from mycelium.session import Session
from mycelium.short_term import ShortTermMemoryQueue, ShortTermMemoryStatus
from mycelium.operations import (
    ConsolidationRequest,
    ConsolidationResult,
    RetrievalRequest,
    RetrievalResult,
    SourceInput,
    IngestionResult,
)
from mycelium.pipeline import MemoryPipeline
from mycelium.retrieval import MemoryRetriever
from mycelium.claim_index import LanceClaimIndex, OllamaEmbedder
from mycelium.artifacts import (
    ArtifactStore,
    SourceSegment,
)


class Mycelium:
    def __init__(
        self,
        store_path: str | Path,
        ollama_model: str = "gemma3:12b",
        ollama_url: str = "http://localhost:11434",
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
        self._ensure_seed_profile(memory_profile)
        self.llm = OllamaClient(
            url=self.config.llm.url,
            model=self.config.llm.model,
            temperature=self.config.llm.temperature,
            timeout=self.config.llm.timeout_seconds,
            context_window_tokens=self.config.llm.context_window_tokens,
        )
        self.encoder = Encoder(self.llm, self._log_store, self.config, self.artifacts)
        self.short_term_memory = ShortTermMemoryQueue(self.artifacts)

        from mycelium.dream import ConsolidationProcess

        self.consolidator = ConsolidationProcess(
            self.llm, self._wiki, self._log_store, self.config, self.artifacts
        )
        self.retriever = MemoryRetriever(
            self.llm,
            self._wiki,
            self.artifacts,
            default_budget_tokens=self.config.context_budget_tokens,
            initial_result_limit=self.config.retrieval.initial_result_limit,
            claim_index=LanceClaimIndex(
                self.store_path / "indexes" / "lancedb",
                self.artifacts,
                OllamaEmbedder(
                    self.config.llm.url,
                    self.config.retrieval.embedding_model,
                    timeout=self.config.llm.timeout_seconds,
                ),
                candidate_limit=self.config.retrieval.candidate_limit,
            ),
        )
        self.pipeline = MemoryPipeline(
            self.encoder,
            self.retriever,
            self.consolidator,
        )

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

    async def retrieve_context(self, request: RetrievalRequest) -> RetrievalResult:
        return await self.pipeline.retrieve_context(request)

    async def ingest_source(self, source: SourceInput) -> IngestionResult:
        return await self.pipeline.ingest_source(source)

    @asynccontextmanager
    async def session(self, query: str, session_id: Optional[str] = None):
        session_id = session_id or str(uuid.uuid4())

        sess = Session(mycelium=self, session_id=session_id, query=query)
        retrieval = await self.retrieve_context(RetrievalRequest(query=query))
        sess.page_references = retrieval.page_references
        sess.memory_evidence = retrieval.evidence

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
                await self.ingest_source(
                    SourceInput(
                        transcript=transcript_str,
                        session_id=session_id,
                        occurred_at=segments[0].timestamp,
                        segments=tuple(segments),
                        idempotency_key=f"session-transcript:{session_id}",
                    )
                )

    def consolidation_status(self) -> ShortTermMemoryStatus:
        return self.short_term_memory.status()

    async def consolidate(
        self, request: ConsolidationRequest = ConsolidationRequest()
    ) -> ConsolidationResult:
        return await self.pipeline.consolidate(request)
