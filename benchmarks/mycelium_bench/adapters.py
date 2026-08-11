from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mycelium.core import Mycelium
from mycelium.artifacts import ArtifactStore, MemoryClaim
from mycelium.consolidation import ClaimRoute
from mycelium.facts import page_recall_context
from mycelium.store import LogStore, WikiStore
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import GroundedAnswerOutput


@dataclass
class BenchmarkMessage:
    role: str
    content: str
    speaker: str | None = None
    timestamp: str | None = None
    message_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkAnswer:
    output: str
    input_len: int
    output_len: int
    memory_construction_time: float
    query_time_len: float
    metadata: dict[str, Any] = field(default_factory=dict)


class MemorySystem(Protocol):
    name: str

    async def reset(self, case_id: str) -> None:
        ...

    async def memorize(self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None) -> None:
        ...

    async def answer(self, question: str, metadata: dict[str, Any] | None = None) -> BenchmarkAnswer:
        ...

    async def finalize_case(self) -> None:
        ...

    def stats(self) -> dict[str, Any]:
        ...


class OllamaQaClient:
    def __init__(self, model: str, url: str, temperature: float = 0.0, timeout: int = 120) -> None:
        self.model = model
        self.llm = OllamaClient(url=url, model=model, temperature=temperature, timeout=timeout)

    async def answer(self, question: str, context: str, instruction: str | None = None) -> BenchmarkAnswer:
        system = instruction or (
            "Answer using only the supplied memory evidence. Raw CANONICAL SOURCE LOG SNIPPETS "
            "outrank synthesized wiki summaries when they disagree. Ground every relation in the "
            "exact named subject: never transfer an action, possession, preference, or event from "
            "one person to another. A question whose premise assigns another person's fact to the "
            "named subject is unanswerable. Resolve relative dates such as yesterday, last week, "
            "or next month against the source's conversation_time when possible.\n\n"
            "Return the shortest exact answer span that satisfies the question. Preserve source "
            "wording; do not explain or restate the question. For a date, return only the resolved "
            "date. For yes/no, return only Yes or No. Set answerable=false when the evidence does "
            "not explicitly support the exact subject-relation-object asked about."
        )
        context_text = context.strip() or "No memory context is available."
        user = f"MEMORY CONTEXT:\n{context_text}\n\nQUESTION:\n{question}"
        start = time.perf_counter()
        response = await self.llm.call_structured(
            system,
            user,
            GroundedAnswerOutput,
            num_predict=256,
        )
        elapsed = time.perf_counter() - start
        answerable = isinstance(response, dict) and bool(response.get("answerable"))
        output = str(response.get("answer", "")).strip() if isinstance(response, dict) else ""
        if not answerable or not output:
            output = "I do not have enough information to answer this question."
        return BenchmarkAnswer(
            output=output,
            input_len=count_tokens(user),
            output_len=count_tokens(output),
            memory_construction_time=0.0,
            query_time_len=elapsed,
            metadata={"grounding": response},
        )


class NullMemorySystem:
    name = "null"

    def __init__(self, qa_client: OllamaQaClient) -> None:
        self.qa_client = qa_client

    async def reset(self, case_id: str) -> None:
        self.case_id = case_id

    async def memorize(self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None) -> None:
        return None

    async def answer(self, question: str, metadata: dict[str, Any] | None = None) -> BenchmarkAnswer:
        return await self.qa_client.answer(question, "")

    async def finalize_case(self) -> None:
        return None

    def stats(self) -> dict[str, Any]:
        return {"system": self.name}


class FullContextMemorySystem:
    name = "full_context"

    def __init__(self, qa_client: OllamaQaClient) -> None:
        self.qa_client = qa_client
        self.context_parts: list[str] = []

    async def reset(self, case_id: str) -> None:
        self.case_id = case_id
        self.context_parts = []

    async def memorize(self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None) -> None:
        self.context_parts.append(format_messages_for_memory(messages, metadata or {}))

    async def answer(self, question: str, metadata: dict[str, Any] | None = None) -> BenchmarkAnswer:
        return await self.qa_client.answer(question, "\n\n".join(self.context_parts))

    async def finalize_case(self) -> None:
        return None

    def stats(self) -> dict[str, Any]:
        return {"system": self.name, "context_batches": len(self.context_parts)}


class MyceliumMemorySystem:
    name = "mycelium"

    def __init__(
        self,
        *,
        run_dir: Path,
        qa_client: OllamaQaClient,
        memory_model: str,
        ollama_url: str,
        config_path: Path | None = None,
        context_budget_tokens: int = 32768,
        dream_policy: str = "per-batch",
        replay_store: Path | None = None,
        replay_assignments: bool = False,
    ) -> None:
        self.run_dir = run_dir
        self.qa_client = qa_client
        self.memory_model = memory_model
        self.ollama_url = ollama_url
        self.config_path = config_path
        self.context_budget_tokens = context_budget_tokens
        self.dream_policy = dream_policy
        self.replay_store = replay_store
        self.replay_assignments = replay_assignments
        self.case_id = "uninitialized"
        self.mem: Mycelium | None = None
        self._encoded_batches = 0
        self._dream_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors: list[dict[str, Any]] = []
        self._dream_failures: list[dict[str, Any]] = []
        self._taxonomy_failures: list[dict[str, Any]] = []
        self._replay_page_kinds: dict[str, str] = {}

    async def reset(self, case_id: str) -> None:
        self.case_id = sanitize_path_part(case_id)
        store_path = self.run_dir / "stores" / self.case_id
        store_path.mkdir(parents=True, exist_ok=True)
        self.mem = Mycelium(
            store_path=store_path,
            ollama_model=self.memory_model,
            ollama_url=self.ollama_url,
            context_budget_tokens=self.context_budget_tokens,
            config_path=self.config_path,
            memory_profile="none",
        )
        self._replay_page_kinds = {}
        if self.replay_assignments:
            replay_store = self._require_replay_store()
            fixture = ArtifactStore(replay_store / "artifacts")
            for proposal in fixture.list_reconsolidation_proposals():
                self.mem.artifacts.save_reconsolidation_proposal(copy.deepcopy(proposal))
            self._replay_page_kinds = {
                page.slug: next(
                    (
                        tag.removeprefix("page-type-")
                        for tag in page.tags
                        if tag.startswith("page-type-")
                    ),
                    "topic",
                )
                for page in WikiStore(replay_store / "wiki").list_all()
            }
        self._encoded_batches = 0
        self._dream_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors = []
        self._dream_failures = []
        self._taxonomy_failures = []

    async def memorize(self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None) -> None:
        if not messages:
            return
        mem = self._require_mem()
        metadata = metadata or {}
        session_id = str(metadata.get("session_id") or f"{self.case_id}-batch-{self._encoded_batches + 1}")
        start = time.perf_counter()
        if self.replay_store is not None:
            replayed_claims = self._replay_session(mem, session_id)
            if self.replay_assignments:
                await self._materialize_replayed_assignments(
                    mem, replayed_claims, session_id=session_id
                )
        else:
            transcript = format_messages_for_memory(messages, metadata)
            await mem.encoder.encode_session(
                transcript, session_id,
                source_type="multi_party_conversation",
                occurred_at=metadata.get("timestamp"),
                metadata={key: value for key, value in metadata.items() if value is not None},
            )
        self._encoded_batches += 1
        if self.dream_policy == "per-batch" and not self.replay_assignments:
            try:
                report = await mem.dream()
                self._record_dream_report(report, session_id=session_id)
                self._dream_runs += 1
            except Exception as exc:
                self._errors.append({"stage": "dream", "session_id": session_id, "error": str(exc)})
        self._memory_construction_seconds += time.perf_counter() - start

    async def answer(self, question: str, metadata: dict[str, Any] | None = None) -> BenchmarkAnswer:
        mem = self._require_mem()
        metadata = metadata or {}
        start = time.perf_counter()
        try:
            loaded_pages = await mem.load_context(
                question,
                budget_tokens=self.context_budget_tokens,
                session_id=str(metadata.get("query_id") or f"{self.case_id}-query"),
            )
        except Exception as exc:
            self._errors.append({"stage": "load_context", "question": question, "error": str(exc)})
            loaded_pages = []
        memory_construction_time = time.perf_counter() - start
        wiki_context = "\n\n".join(
            f"=== MEMORY: {page.title} ({page.slug}) ===\n{format_page_for_prompt(page)}"
            for page in loaded_pages
        )
        source_context = "\n\n".join(
            page.source_context for page in loaded_pages if page.source_context
        )
        context = wiki_context
        if source_context:
            context = (
                f"SYNTHESIZED MEMORY PAGES:\n{wiki_context}\n\n"
                f"CANONICAL SOURCE EVIDENCE:\n{source_context}"
            )
        answer = await self.qa_client.answer(question, context)
        answer.memory_construction_time = memory_construction_time
        answer.metadata.update(
            {
                "loaded_pages": [
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "confidence": page.confidence,
                        "importance": page.importance,
                    }
                    for page in loaded_pages
                ],
            }
        )
        return answer

    async def finalize_case(self) -> None:
        if (
            self.dream_policy == "per-case"
            and self.mem is not None
            and not self.replay_assignments
        ):
            start = time.perf_counter()
            try:
                report = await self.mem.dream()
                self._record_dream_report(report, session_id=self.case_id)
                self._dream_runs += 1
            except Exception as exc:
                self._errors.append({"stage": "dream", "case_id": self.case_id, "error": str(exc)})
            self._memory_construction_seconds += time.perf_counter() - start

    def stats(self) -> dict[str, Any]:
        page_count = 0
        log_count = 0
        if self.mem is not None:
            page_count = len(self.mem.wiki.list_all())
            log_count = len(self.mem.log_store.get_unconsolidated())
        coverage = self.mem.artifacts.coverage_report() if self.mem is not None else {}
        return {
            "system": self.name,
            "encoded_batches": self._encoded_batches,
            "dream_runs": self._dream_runs,
            "wiki_pages": page_count,
            "unconsolidated_logs": log_count,
            "memory_construction_seconds": self._memory_construction_seconds,
            "errors": self._errors,
            "dream_failures": self._dream_failures,
            "taxonomy_failures": self._taxonomy_failures,
            "artifact_coverage": coverage,
        }

    def _record_dream_report(self, report: Any, *, session_id: str) -> None:
        for failure in getattr(report, "failures", []) or []:
            self._dream_failures.append({"session_id": session_id, **failure})
        for failure in getattr(report, "taxonomy_failures", []) or []:
            self._taxonomy_failures.append({"session_id": session_id, **failure})

    def _require_mem(self) -> Mycelium:
        if self.mem is None:
            raise RuntimeError("Memory system has not been reset for a benchmark case.")
        return self.mem

    def _require_replay_store(self) -> Path:
        if self.replay_store is None:
            raise RuntimeError("Replay store is not configured")
        return self.replay_store

    def _replay_session(self, mem: Mycelium, session_id: str) -> list[MemoryClaim]:
        """Inject frozen extraction artifacts while resetting downstream Dream state."""
        replay_store = self._require_replay_store()
        fixture_artifacts = ArtifactStore(replay_store / "artifacts")
        fixture_logs = LogStore(replay_store / "logs")
        sources = [
            source for source in fixture_artifacts.list_sources()
            if source.session_id == session_id
            or str(source.metadata.get("session_id", "")) == session_id
        ]
        if not sources:
            raise ValueError(f"Replay store has no source for session {session_id}")
        episodes = {
            episode.source_id: episode for episode in fixture_artifacts.list_episodes()
        }
        replayed_claims: list[MemoryClaim] = []
        for source in sources:
            mem.artifacts.save_source(copy.deepcopy(source))
            episode = episodes.get(source.source_id)
            if episode is None:
                raise ValueError(f"Replay source {source.source_id} has no episode")
            mem.artifacts.save_episode(copy.deepcopy(episode))
            for claim_id in episode.claim_ids:
                claim = copy.deepcopy(fixture_artifacts.get_claim(claim_id))
                claim.links = []
                if not self.replay_assignments:
                    claim.page_slugs = []
                claim.dream_disposition = "pending"
                claim.dream_disposition_reason = None
                claim.dream_run_id = None
                claim.dream_disposition_at = None
                mem.artifacts.save_claim(claim)
                replayed_claims.append(claim)
            if not source.raw_log_entry_id:
                raise ValueError(f"Replay source {source.source_id} has no raw log entry")
            entry = copy.deepcopy(fixture_logs.get(source.raw_log_entry_id))
            entry.status = "raw"
            entry.consolidated = False
            mem.log_store.append(entry)
        return replayed_claims

    async def _materialize_replayed_assignments(
        self,
        mem: Mycelium,
        claims: list[MemoryClaim],
        *,
        session_id: str,
    ) -> None:
        routes = [
            ClaimRoute(
                claim_id=claim.claim_id,
                page_slug=page_slug,
                page_type=self._replay_page_kinds.get(page_slug, "topic"),
                raw_log_entry_id=(
                    claim.provenance[0].raw_log_entry_id
                    or claim.provenance[0].source_id
                ),
            )
            for claim in claims
            for page_slug in claim.page_slugs
        ]
        materialized = mem.dream_process.materializer.stage(routes)
        taxonomy = await mem.dream_process.taxonomist.classify(
            mem.dream_process.materializer.taxonomy_candidates(materialized)
        )
        mem.dream_process.materializer.apply_page_types(
            materialized, taxonomy.assignments
        )
        mem.dream_process.materializer.refresh_you_memory_map(materialized)
        mem.dream_process.materializer.persist(materialized)
        for failure in taxonomy.failures:
            self._taxonomy_failures.append({"session_id": session_id, **failure})

        eligible = [
            claim for claim in claims
            if claim.status == "active" and not claim.derivation_operation
        ]
        if eligible and all(len(claim.page_slugs) == 1 for claim in eligible):
            raw_ids = {
                provenance.raw_log_entry_id
                for claim in eligible
                for provenance in claim.provenance
                if provenance.raw_log_entry_id
            }
            mem.log_store.mark_consolidated(sorted(raw_ids))


class FullWikiMemorySystem(MyceliumMemorySystem):
    name = "full_wiki"

    async def answer(self, question: str, metadata: dict[str, Any] | None = None) -> BenchmarkAnswer:
        mem = self._require_mem()
        
        # Load all pages in the wiki store
        all_pages = mem.wiki.list_all()
        # Sort by slug to be deterministic
        all_pages.sort(key=lambda p: p.slug)
        
        # Format all pages into one single context
        context_parts = []
        for page in all_pages:
            context_parts.append(
                f"=== MEMORY: {page.title} ({page.slug}) ===\n{format_page_for_prompt(page)}"
            )
        context = "\n\n".join(context_parts)
        
        start = time.perf_counter()
        answer = await self.qa_client.answer(question, context)
        query_time = time.perf_counter() - start
        
        answer.memory_construction_time = 0.0
        answer.query_time_len = query_time
        answer.metadata.update(
            {
                "loaded_pages": [
                    {
                        "slug": page.slug,
                        "title": page.title,
                        "confidence": page.confidence,
                        "importance": page.importance,
                    }
                    for page in all_pages
                ],
            }
        )
        return answer


def build_memory_system(
    *,
    system_name: str,
    run_dir: Path,
    qa_model: str,
    memory_model: str,
    ollama_url: str,
    config_path: Path | None,
    context_budget_tokens: int,
    dream_policy: str,
    replay_store: Path | None = None,
    replay_assignments: bool = False,
) -> MemorySystem:
    if replay_store is not None and system_name not in {"mycelium", "full_wiki"}:
        raise ValueError("--replay-store is only supported by mycelium and full_wiki")
    if replay_store is not None and not replay_store.is_dir():
        raise ValueError(f"Replay store does not exist: {replay_store}")
    if replay_assignments and replay_store is None:
        raise ValueError("--replay-assignments requires --replay-store")
    qa_client = OllamaQaClient(model=qa_model, url=ollama_url)
    if system_name == "mycelium":
        return MyceliumMemorySystem(
            run_dir=run_dir,
            qa_client=qa_client,
            memory_model=memory_model,
            ollama_url=ollama_url,
            config_path=config_path,
            context_budget_tokens=context_budget_tokens,
            dream_policy=dream_policy,
            replay_store=replay_store,
            replay_assignments=replay_assignments,
        )
    if system_name == "full_wiki":
        return FullWikiMemorySystem(
            run_dir=run_dir,
            qa_client=qa_client,
            memory_model=memory_model,
            ollama_url=ollama_url,
            config_path=config_path,
            context_budget_tokens=context_budget_tokens,
            dream_policy=dream_policy,
            replay_store=replay_store,
            replay_assignments=replay_assignments,
        )
    if system_name == "null":
        return NullMemorySystem(qa_client)
    if system_name == "full_context":
        return FullContextMemorySystem(qa_client)
    raise ValueError(f"Unknown benchmark system: {system_name}")


def format_messages_for_memory(messages: list[BenchmarkMessage], metadata: dict[str, Any]) -> str:
    prefix_lines = []
    if metadata.get("session_id"):
        prefix_lines.append(f"Session: {metadata['session_id']}")
    if metadata.get("timestamp"):
        prefix_lines.append(f"Timestamp: {metadata['timestamp']}")
    if metadata.get("sample_id"):
        prefix_lines.append(f"Sample: {metadata['sample_id']}")

    body_lines = []
    for message in messages:
        label = message.speaker or message.role
        pieces = []
        if message.message_id:
            pieces.append(f"[{message.message_id}]")
        if message.timestamp:
            pieces.append(f"({message.timestamp})")
        pieces.append(f"{label}: {message.content}")
        body_lines.append(" ".join(pieces))

    return "\n".join([*prefix_lines, *body_lines]).strip()


def format_page_for_prompt(page: Any, *, include_source: bool = False) -> str:
    recall_context = page_recall_context(page)
    body = f"{recall_context}\n\n{page.content}" if recall_context else page.content
    source_context = getattr(page, "source_context", "") if include_source else ""
    if source_context:
        return f"{body}\n\n{source_context}"
    return body


def sanitize_path_part(value: str) -> str:
    keep = [ch.lower() if ch.isalnum() else "-" for ch in str(value)]
    return "-".join("".join(keep).split("-")).strip("-") or "case"


def count_tokens(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        return len(enc.encode(text, disallowed_special=()))
    except Exception:
        return len(text.split())


def run_async(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError(f"Cannot run benchmark command inside an existing event loop: {loop}")
