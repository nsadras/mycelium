from __future__ import annotations

import asyncio
import copy
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from mycelium.context import render_memory_context
from mycelium.core import Mycelium
from mycelium.artifacts import ArtifactStore, MemoryClaim, SourceSegment
from mycelium.store import LogStore
from mycelium.ollama import OllamaClient
from mycelium.prompting import render_prompt
from mycelium.operations import (
    ConsolidationRequest,
    MemoryEvidence,
    RetrievalRequest,
    SourceInput,
)
from mycelium.memory_tools import MEMORY_TOOL_DEFINITIONS, MemoryToolset
from mycelium.retrieval_context import render_memory_workspace
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

    async def reset(self, case_id: str) -> None: ...

    async def memorize(
        self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None
    ) -> None: ...

    async def answer(
        self, question: str, metadata: dict[str, Any] | None = None
    ) -> BenchmarkAnswer: ...

    async def finalize_case(self) -> None: ...

    def stats(self) -> dict[str, Any]: ...


class OllamaQaClient:
    def __init__(
        self, model: str, url: str, temperature: float = 0.0, timeout: int = 120
    ) -> None:
        self.model = model
        self.llm = OllamaClient(
            url=url, model=model, temperature=temperature, timeout=timeout
        )

    async def answer(
        self, question: str, context: str, instruction: str | None = None
    ) -> BenchmarkAnswer:
        system = instruction or render_prompt("benchmarks/grounded_answer.system.jinja")
        user = render_prompt(
            "benchmarks/grounded_answer.user.jinja",
            memory_context=context.strip(),
            no_memory_context="No memory context is available.",
            question=question,
        )
        start = time.perf_counter()
        response = await self.llm.call_structured(
            system,
            user,
            GroundedAnswerOutput,
        )
        elapsed = time.perf_counter() - start
        answerable = isinstance(response, dict) and bool(response.get("answerable"))
        output = (
            str(response.get("answer", "")).strip()
            if isinstance(response, dict)
            else ""
        )
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

    async def answer_with_memory_tools(
        self,
        question: str,
        tools: MemoryToolset,
    ) -> BenchmarkAnswer:
        system = render_prompt(
            "assistant/memory_agent.system.jinja",
            response_instructions=render_prompt(
                "benchmarks/concise_answer.instructions.jinja"
            ),
        )
        user = render_prompt(
            "assistant/memory_request.user.jinja",
            memory_evidence=render_memory_workspace(tools.workspace.snapshot),
            user_request=question,
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        start = time.perf_counter()
        response = await self.llm.call_messages(
            messages,
            max_tool_rounds=tools.search_limit,
            num_ctx=self.llm.context_window_tokens,
            think=True,
            tool_definitions=MEMORY_TOOL_DEFINITIONS,
            tool_runner=tools.run,
            replaceable_context_message_index=1,
            replacement_context_content=render_prompt(
                "assistant/current_request.user.jinja", user_request=question
            ),
        )
        elapsed = time.perf_counter() - start
        output = response.content.strip()
        if not output:
            output = "I do not have enough information to answer this question."
        return BenchmarkAnswer(
            output=output,
            input_len=count_tokens(system + "\n" + user),
            output_len=count_tokens(output),
            memory_construction_time=0.0,
            query_time_len=elapsed,
            metadata={
                "memory_tool_events": [asdict(event) for event in response.tool_events],
                "agent_execution_trace": [
                    asdict(step) for step in response.execution_trace
                ],
                "ollama": response.metadata,
                "memory_workspace": asdict(tools.workspace.snapshot),
            },
        )


class NullMemorySystem:
    name = "null"

    def __init__(self, qa_client: OllamaQaClient) -> None:
        self.qa_client = qa_client

    async def reset(self, case_id: str) -> None:
        self.case_id = case_id

    async def memorize(
        self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None
    ) -> None:
        return None

    async def answer(
        self, question: str, metadata: dict[str, Any] | None = None
    ) -> BenchmarkAnswer:
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

    async def memorize(
        self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None
    ) -> None:
        self.context_parts.append(format_messages_for_memory(messages, metadata or {}))

    async def answer(
        self, question: str, metadata: dict[str, Any] | None = None
    ) -> BenchmarkAnswer:
        return await self.qa_client.answer(question, "\n\n".join(self.context_parts))

    async def finalize_case(self) -> None:
        return None

    def stats(self) -> dict[str, Any]:
        return {"system": self.name, "context_batches": len(self.context_parts)}


class GoldEvidenceMemorySystem:
    """Benchmark oracle that answers from exactly the labeled source turns."""

    name = "gold_evidence"

    def __init__(self, qa_client: OllamaQaClient) -> None:
        self.qa_client = qa_client
        self.messages_by_id: dict[str, BenchmarkMessage] = {}

    async def reset(self, case_id: str) -> None:
        self.case_id = case_id
        self.messages_by_id = {}

    async def memorize(
        self,
        messages: list[BenchmarkMessage],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        for message in messages:
            if message.message_id:
                self.messages_by_id[message.message_id] = message

    async def answer(
        self, question: str, metadata: dict[str, Any] | None = None
    ) -> BenchmarkAnswer:
        metadata = metadata or {}
        evidence_ids = [str(value) for value in metadata.get("gold_evidence", [])]
        context = "\n".join(
            _format_gold_evidence(message)
            for evidence_id in evidence_ids
            if (message := self.messages_by_id.get(evidence_id)) is not None
        )
        answer = await self.qa_client.answer(question, context)
        answer.metadata.update(
            {
                "oracle": "gold_evidence",
                "requested_evidence": evidence_ids,
                "retrieval_context": context,
            }
        )
        return answer

    async def finalize_case(self) -> None:
        return None

    def stats(self) -> dict[str, Any]:
        return {"system": self.name, "indexed_messages": len(self.messages_by_id)}


def _format_gold_evidence(message: BenchmarkMessage) -> str:
    pieces = [f"[{message.message_id}]" if message.message_id else ""]
    if message.timestamp:
        pieces.append(f"(conversation_time={message.timestamp})")
    if message.speaker:
        pieces.append(f"{message.speaker}:")
    pieces.append(message.content)
    return " ".join(piece for piece in pieces if piece)


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
        frozen_store: Path | None = None,
        include_retrieval_context: bool = False,
        memory_profile: Literal["user", "none"] = "none",
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
        self.frozen_store = frozen_store
        self.include_retrieval_context = include_retrieval_context
        self.memory_profile = memory_profile
        self.case_id = "uninitialized"
        self.mem: Mycelium | None = None
        self._encoded_batches = 0
        self._dream_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors: list[dict[str, Any]] = []
        self._dream_failures: list[dict[str, Any]] = []
        self._evidence_stage_segments_cache: dict[str, Any] | None = None

    async def reset(self, case_id: str) -> None:
        self.case_id = sanitize_path_part(case_id)
        store_path = self.run_dir / "stores" / self.case_id
        if self.frozen_store is not None:
            shutil.copytree(self.frozen_store, store_path, dirs_exist_ok=True)
        store_path.mkdir(parents=True, exist_ok=True)
        self.mem = Mycelium(
            store_path=store_path,
            ollama_model=self.memory_model,
            ollama_url=self.ollama_url,
            context_budget_tokens=self.context_budget_tokens,
            config_path=self.config_path,
            memory_profile=self.memory_profile,
        )
        if self.replay_assignments:
            replay_store = self._require_replay_store()
            fixture = ArtifactStore(replay_store / "artifacts")
            for proposal in fixture.list_reconsolidation_proposals():
                self.mem.artifacts.save_reconsolidation_proposal(
                    copy.deepcopy(proposal)
                )
            for entity in fixture.list_entities():
                self.mem.artifacts.save_entity(copy.deepcopy(entity))
        self._encoded_batches = 0
        self._dream_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors = []
        self._dream_failures = []
        self._evidence_stage_segments_cache = None

    async def memorize(
        self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None
    ) -> None:
        if not messages:
            return
        if self.frozen_store is not None:
            return
        mem = self._require_mem()
        metadata = metadata or {}
        session_id = str(
            metadata.get("session_id")
            or f"{self.case_id}-batch-{self._encoded_batches + 1}"
        )
        start = time.perf_counter()
        if self.replay_store is not None:
            replayed_claims = self._replay_session(mem, session_id)
            if self.replay_assignments:
                await self._materialize_replayed_assignments(
                    mem, replayed_claims, session_id=session_id
                )
        else:
            transcript = format_messages_for_memory(messages, metadata)
            await mem.ingest_source(
                SourceInput(
                    transcript=transcript,
                    session_id=session_id,
                    source_type="multi_party_conversation",
                    occurred_at=metadata.get("timestamp"),
                    participants=tuple(dict.fromkeys(m.speaker for m in messages if m.speaker)),
                    segments=tuple(SourceSegment(
                        segment_id="", index=index, content=message.content,
                        speaker=message.speaker, role=message.role,
                        timestamp=message.timestamp,
                        metadata={**message.metadata, "source_label": message.message_id},
                    ) for index, message in enumerate(messages)) if all(m.speaker for m in messages) else None,
                    metadata={
                        key: value
                        for key, value in metadata.items()
                        if value is not None
                    },
                    idempotency_key=f"benchmark:{self.case_id}:{session_id}",
                )
            )
        self._encoded_batches += 1
        if self.dream_policy == "per-batch" and not self.replay_assignments:
            try:
                result = await mem.consolidate(ConsolidationRequest())
                self._record_dream_report(result.report, session_id=session_id)
                self._dream_runs += 1
            except Exception as exc:
                self._errors.append(
                    {"stage": "dream", "session_id": session_id, "error": str(exc)}
                )
        self._memory_construction_seconds += time.perf_counter() - start

    async def answer(
        self, question: str, metadata: dict[str, Any] | None = None
    ) -> BenchmarkAnswer:
        mem = self._require_mem()
        metadata = metadata or {}
        start = time.perf_counter()
        retrieval_trace: dict[str, Any] = {}
        initial_evidence = MemoryEvidence()
        tool_evidence_budget = mem.config.retrieval.tool_evidence_budget_tokens
        if tool_evidence_budget >= self.context_budget_tokens:
            raise ValueError(
                "Memory tool evidence budget must be smaller than the benchmark context budget"
            )
        initial_budget = self.context_budget_tokens - tool_evidence_budget
        try:
            retrieval = await mem.retrieve_context(
                RetrievalRequest(
                    query=question,
                    budget_tokens=initial_budget,
                )
            )
            loaded_pages = list(retrieval.page_references)
            retrieval_trace = retrieval.trace
            initial_evidence = retrieval.evidence
        except Exception as exc:
            self._errors.append(
                {
                    "stage": "retrieve_context",
                    "question": question,
                    "error": str(exc),
                }
            )
            loaded_pages = []
        memory_construction_time = time.perf_counter() - start
        memory_tools = MemoryToolset(
            mem.retriever,
            result_limit=mem.config.retrieval.tool_result_limit,
            search_limit=mem.config.retrieval.tool_search_limit,
            evidence_budget_tokens=tool_evidence_budget,
            request=question,
            initial_evidence=initial_evidence,
        )
        answer = await self.qa_client.answer_with_memory_tools(
            question, memory_tools
        )
        answer.memory_construction_time = memory_construction_time
        full_evidence_context = render_memory_workspace(
            memory_tools.workspace.snapshot
        )
        answer.metadata.update(
            {
                "loaded_pages": [
                    {
                        "slug": page.slug,
                        "title": page.title,
                    }
                    for page in loaded_pages
                ],
                "retrieval_trace": retrieval_trace,
                "_evidence_stage_segments": self._evidence_stage_segments(
                    full_evidence_context
                ),
            }
        )
        if self.include_retrieval_context:
            answer.metadata["retrieval_context"] = full_evidence_context
        return answer

    def _evidence_stage_segments(self, context: str) -> dict[str, Any]:
        if self._evidence_stage_segments_cache is None:
            mem = self._require_mem()
            label_by_segment = {
                segment.segment_id: str(label)
                for source in mem.artifacts.list_sources()
                for segment in source.segments
                if (label := segment.metadata.get("source_label"))
            }
            segments_by_label: dict[str, set[str]] = {}
            for segment_id, label in label_by_segment.items():
                segments_by_label.setdefault(label, set()).add(segment_id)

            source_segments = set(label_by_segment)
            claim_segments: set[str] = set()
            wiki_segments: set[str] = set()
            for claim in mem.artifacts.list_claims(status="active"):
                segments = {
                    segment_id
                    for provenance in claim.provenance
                    for segment_id in provenance.segment_ids
                    if segment_id in label_by_segment
                }
                claim_segments.update(segments)
                placement = mem.artifacts.placement_for_claim(claim.claim_id)
                if placement and placement.owner_entity_id:
                    entity = mem.artifacts.get_entity(placement.owner_entity_id)
                    if mem.wiki.exists(entity.slug):
                        wiki_segments.update(segments)
            self._evidence_stage_segments_cache = {
                "segments_by_label": segments_by_label,
                "stages": {
                    "source": source_segments,
                    "claim": claim_segments,
                    "wiki": wiki_segments,
                },
            }

        segments_by_label = self._evidence_stage_segments_cache["segments_by_label"]
        source_segments = self._evidence_stage_segments_cache["stages"]["source"]
        stage_segments = {
            stage: sorted(segment_ids)
            for stage, segment_ids in self._evidence_stage_segments_cache[
                "stages"
            ].items()
        }
        stage_segments["context"] = sorted(
            segment_id for segment_id in source_segments if segment_id in context
        )
        return {
            "segments_by_label": {
                label: sorted(segment_ids)
                for label, segment_ids in segments_by_label.items()
            },
            "stages": stage_segments,
        }

    async def finalize_case(self) -> None:
        if self.frozen_store is not None:
            return
        if (
            self.dream_policy == "per-case"
            and self.mem is not None
            and not self.replay_assignments
        ):
            start = time.perf_counter()
            try:
                result = await self.mem.consolidate(ConsolidationRequest())
                self._record_dream_report(result.report, session_id=self.case_id)
                self._dream_runs += 1
            except Exception as exc:
                self._errors.append(
                    {"stage": "dream", "case_id": self.case_id, "error": str(exc)}
                )
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
            "artifact_coverage": coverage,
        }

    def _record_dream_report(self, report: Any, *, session_id: str) -> None:
        for failure in getattr(report, "failures", []) or []:
            self._dream_failures.append({"session_id": session_id, **failure})

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
            source
            for source in fixture_artifacts.list_sources()
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
                claim.dream_disposition = "pending"
                claim.dream_disposition_reason = None
                claim.dream_run_id = None
                claim.dream_disposition_at = None
                mem.artifacts.save_claim(claim)
                if self.replay_assignments:
                    placement = fixture_artifacts.placement_for_claim(claim.claim_id)
                    if placement:
                        mem.artifacts.save_placement(copy.deepcopy(placement))
                replayed_claims.append(claim)
            if not source.raw_log_entry_id:
                raise ValueError(
                    f"Replay source {source.source_id} has no raw log entry"
                )
            entry = copy.deepcopy(fixture_logs.get(source.raw_log_entry_id))
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
        # Assignment replay bypasses model synthesis, not content projection. Render
        # each frozen canonical statement once while preserving its saved section.
        for claim in claims:
            placement = mem.artifacts.placement_for_claim(claim.claim_id)
            if claim.status != "active" or placement is None or placement.status != "placed":
                continue
            if mem.artifacts.facts_for_claim(claim.claim_id):
                continue
            owner = mem.artifacts.get_entity(placement.owner_entity_id)
            fact, _ = mem.consolidator.fact_resolver._direct_projection(owner, claim, placement)
            fact.section_key = placement.section_key
            mem.artifacts.save_consolidated_fact(fact)
        owner_ids = {
            placement.owner_entity_id
            for claim in claims
            if (placement := mem.artifacts.placement_for_claim(claim.claim_id))
            and placement.owner_entity_id
        }
        mem.consolidator.materializer.regenerate(owner_ids)

        eligible = [claim for claim in claims if claim.status == "active"]
        if eligible and all(
            (placement := mem.artifacts.placement_for_claim(claim.claim_id)) is not None
            and placement.status in {"placed", "unassigned"}
            for claim in eligible
        ):
            raw_ids = {
                provenance.raw_log_entry_id
                for claim in eligible
                for provenance in claim.provenance
                if provenance.raw_log_entry_id
            }
            mem.log_store.mark_consolidated(sorted(raw_ids))


class FullWikiMemorySystem(MyceliumMemorySystem):
    name = "full_wiki"

    async def answer(
        self, question: str, metadata: dict[str, Any] | None = None
    ) -> BenchmarkAnswer:
        mem = self._require_mem()

        # Load all pages in the wiki store
        all_pages = mem.wiki.list_all()
        # Sort by slug to be deterministic
        all_pages.sort(key=lambda p: p.slug)

        context = render_memory_context(all_pages)

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
    frozen_store: Path | None = None,
    include_retrieval_context: bool = False,
) -> MemorySystem:
    if replay_store is not None and system_name not in {
        "mycelium",
        "full_wiki",
    }:
        raise ValueError("--replay-store is only supported by mycelium and full_wiki")
    if replay_store is not None and not replay_store.is_dir():
        raise ValueError(f"Replay store does not exist: {replay_store}")
    if replay_assignments and replay_store is None:
        raise ValueError("--replay-assignments requires --replay-store")
    if frozen_store is not None and replay_store is not None:
        raise ValueError("--frozen-store and --replay-store are mutually exclusive")
    if frozen_store is not None and not frozen_store.is_dir():
        raise ValueError(f"Frozen store does not exist: {frozen_store}")
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
            frozen_store=frozen_store,
            include_retrieval_context=include_retrieval_context,
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
            frozen_store=frozen_store,
            include_retrieval_context=include_retrieval_context,
        )
    if system_name == "null":
        return NullMemorySystem(qa_client)
    if system_name == "full_context":
        return FullContextMemorySystem(qa_client)
    if system_name == "gold_evidence":
        return GoldEvidenceMemorySystem(qa_client)
    raise ValueError(f"Unknown benchmark system: {system_name}")


def format_messages_for_memory(
    messages: list[BenchmarkMessage], metadata: dict[str, Any]
) -> str:
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
    raise RuntimeError(
        f"Cannot run benchmark command inside an existing event loop: {loop}"
    )
