from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mycelium.core import Mycelium
from mycelium.facts import page_recall_context
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
        reconsolidate: bool = False,
        evidence_mode: str = "hybrid",
    ) -> None:
        self.run_dir = run_dir
        self.qa_client = qa_client
        self.memory_model = memory_model
        self.ollama_url = ollama_url
        self.config_path = config_path
        self.context_budget_tokens = context_budget_tokens
        self.dream_policy = dream_policy
        self.reconsolidate = reconsolidate
        self.evidence_mode = evidence_mode
        self.case_id = "uninitialized"
        self.mem: Mycelium | None = None
        self._encoded_batches = 0
        self._dream_runs = 0
        self._compaction_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors: list[dict[str, Any]] = []
        self._dream_failures: list[dict[str, Any]] = []

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
            evidence_mode=self.evidence_mode,
        )
        self.mem.config.reconsolidation.check_on_load = self.reconsolidate
        self._encoded_batches = 0
        self._dream_runs = 0
        self._compaction_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors = []
        self._dream_failures = []

    async def memorize(self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None) -> None:
        if not messages:
            return
        mem = self._require_mem()
        metadata = metadata or {}
        session_id = str(metadata.get("session_id") or f"{self.case_id}-batch-{self._encoded_batches + 1}")
        transcript = format_messages_for_memory(messages, metadata)
        start = time.perf_counter()
        await mem.encoder.encode_session(
            transcript, session_id,
            source_type="multi_party_conversation",
            occurred_at=metadata.get("timestamp"),
            metadata={key: value for key, value in metadata.items() if value is not None},
        )
        self._encoded_batches += 1
        if self.dream_policy == "per-batch":
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
                reconsolidate=self.reconsolidate,
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
        if self.dream_policy == "per-case" and self.mem is not None:
            start = time.perf_counter()
            try:
                report = await self.mem.dream()
                self._record_dream_report(report, session_id=self.case_id)
                self._dream_runs += 1
            except Exception as exc:
                self._errors.append({"stage": "dream", "case_id": self.case_id, "error": str(exc)})
            self._memory_construction_seconds += time.perf_counter() - start
        if self.mem is not None:
            start = time.perf_counter()
            try:
                await self.mem.compact()
                self._compaction_runs += 1
            except Exception as exc:
                self._errors.append({"stage": "compact", "case_id": self.case_id, "error": str(exc)})
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
            "compaction_runs": self._compaction_runs,
            "wiki_pages": page_count,
            "unconsolidated_logs": log_count,
            "memory_construction_seconds": self._memory_construction_seconds,
            "errors": self._errors,
            "dream_failures": self._dream_failures,
            "evidence_mode": self.evidence_mode,
            "artifact_coverage": coverage,
        }

    def _record_dream_report(self, report: Any, *, session_id: str) -> None:
        for failure in getattr(report, "failures", []) or []:
            self._dream_failures.append({"session_id": session_id, **failure})

    def _require_mem(self) -> Mycelium:
        if self.mem is None:
            raise RuntimeError("Memory system has not been reset for a benchmark case.")
        return self.mem


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
    reconsolidate: bool = False,
    evidence_mode: str = "hybrid",
) -> MemorySystem:
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
            reconsolidate=reconsolidate,
            evidence_mode=evidence_mode,
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
            reconsolidate=reconsolidate,
            evidence_mode=evidence_mode,
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
