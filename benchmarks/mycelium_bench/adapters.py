from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mycelium.core import Mycelium
from mycelium.facts import page_recall_context
from mycelium.ollama import OllamaClient


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
            "You answer benchmark questions. Use the supplied memory context when it is relevant. "
            "Answer concisely and include only the answer."
        )
        context_text = context.strip() or "No memory context is available."
        user = f"MEMORY CONTEXT:\n{context_text}\n\nQUESTION:\n{question}"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        start = time.time()
        response = await self.llm.call_messages(messages, temperature=0.0, enable_tools=False)
        elapsed = time.time() - start
        return BenchmarkAnswer(
            output=response.content.strip(),
            input_len=count_tokens(user),
            output_len=count_tokens(response.content),
            memory_construction_time=0.0,
            query_time_len=elapsed,
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
        context_budget_tokens: int = 8192,
        dream_policy: str = "per-batch",
        reconsolidate: bool = False,
    ) -> None:
        self.run_dir = run_dir
        self.qa_client = qa_client
        self.memory_model = memory_model
        self.ollama_url = ollama_url
        self.config_path = config_path
        self.context_budget_tokens = context_budget_tokens
        self.dream_policy = dream_policy
        self.reconsolidate = reconsolidate
        self.case_id = "uninitialized"
        self.mem: Mycelium | None = None
        self._encoded_batches = 0
        self._dream_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors: list[dict[str, Any]] = []

    async def reset(self, case_id: str) -> None:
        self.case_id = sanitize_path_part(case_id)
        store_path = self.run_dir / "stores" / self.case_id
        store_path.mkdir(parents=True, exist_ok=True)
        self.mem = Mycelium(
            store_path=store_path,
            ollama_model=self.memory_model,
            ollama_url=self.ollama_url,
            context_budget_tokens=self.context_budget_tokens,
            dream_schedule="manual",
            config_path=self.config_path,
            memory_profile="none",
        )
        self.mem.config.dream.schedule = "manual"
        self.mem.config.reconsolidation.check_on_load = self.reconsolidate
        self._encoded_batches = 0
        self._dream_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors = []

    async def memorize(self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None) -> None:
        if not messages:
            return
        mem = self._require_mem()
        metadata = metadata or {}
        session_id = str(metadata.get("session_id") or f"{self.case_id}-batch-{self._encoded_batches + 1}")
        transcript = format_messages_for_memory(messages, metadata)
        start = time.time()
        try:
            await mem.encoder.encode_session(transcript, session_id)
        except Exception as exc:
            self._errors.append({"stage": "encode_session", "session_id": session_id, "error": str(exc)})
            await mem.encoder.encode(
                content=(
                    "Raw benchmark session transcript preserved after structured encoding failed.\n"
                    "Dream consolidation should extract durable facts, exact dates, people, and source IDs from this transcript.\n\n"
                    f"{transcript}"
                ),
                session_id=session_id,
                importance=0.6,
                durability="durable",
            )
        self._encoded_batches += 1
        if self.dream_policy == "per-batch":
            try:
                await mem.dream()
                self._dream_runs += 1
            except Exception as exc:
                self._errors.append({"stage": "dream", "session_id": session_id, "error": str(exc)})
        self._memory_construction_seconds += time.time() - start

    async def answer(self, question: str, metadata: dict[str, Any] | None = None) -> BenchmarkAnswer:
        mem = self._require_mem()
        metadata = metadata or {}
        start = time.time()
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
        memory_construction_time = time.time() - start
        context = "\n\n".join(
            f"=== MEMORY: {page.title} ({page.slug}) ===\n{format_page_for_prompt(page)}"
            for page in loaded_pages
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
                        "retrievability": page.retrievability,
                    }
                    for page in loaded_pages
                ],
            }
        )
        return answer

    async def finalize_case(self) -> None:
        if self.dream_policy == "per-case" and self.mem is not None:
            start = time.time()
            try:
                await self.mem.dream()
                self._dream_runs += 1
            except Exception as exc:
                self._errors.append({"stage": "dream", "case_id": self.case_id, "error": str(exc)})
            self._memory_construction_seconds += time.time() - start

    def stats(self) -> dict[str, Any]:
        page_count = 0
        log_count = 0
        if self.mem is not None:
            page_count = len(self.mem.wiki.list_all())
            log_count = len(self.mem.log_store.get_unconsolidated())
        return {
            "system": self.name,
            "encoded_batches": self._encoded_batches,
            "dream_runs": self._dream_runs,
            "wiki_pages": page_count,
            "unconsolidated_logs": log_count,
            "memory_construction_seconds": self._memory_construction_seconds,
            "errors": self._errors,
        }

    def _require_mem(self) -> Mycelium:
        if self.mem is None:
            raise RuntimeError("Memory system has not been reset for a benchmark case.")
        return self.mem


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


def format_page_for_prompt(page: Any) -> str:
    recall_context = page_recall_context(page)
    body = f"{recall_context}\n\n{page.content}" if recall_context else page.content
    source_context = getattr(page, "source_context", "")
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
