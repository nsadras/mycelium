from __future__ import annotations

import asyncio
import copy
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Protocol

from pydantic import BaseModel, Field

from mycelium.core import Mycelium
from mycelium.artifacts import ArtifactStore, MemoryClaim
from mycelium.consolidation import ClaimRoute
from mycelium.store import LogStore, WikiStore
from mycelium.ollama import OllamaClient
from mycelium.memory_tools import MemoryToolset
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


RetrievalQuery = Annotated[str, Field(min_length=1, max_length=160)]
MAX_PLANNED_EVIDENCE_CHARS = 12_000
MAX_PLANNED_SOURCE_SEGMENT_CHARS = 1_400


class MemoryRetrievalPlan(BaseModel):
    """A small executable plan for questions that require composed evidence."""

    searches: list[RetrievalQuery] = Field(
        min_length=1,
        max_length=4,
        description="Distinct complementary searches, never paraphrases of one another.",
    )
    expand_top_hits: bool
    inspect_sources: bool


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
        self.case_id = "uninitialized"
        self.mem: Mycelium | None = None
        self._encoded_batches = 0
        self._dream_runs = 0
        self._memory_construction_seconds = 0.0
        self._errors: list[dict[str, Any]] = []
        self._dream_failures: list[dict[str, Any]] = []
        self._taxonomy_failures: list[dict[str, Any]] = []
        self._replay_page_kinds: dict[str, str] = {}
        self._evidence_stage_labels_cache: dict[str, set[str]] | None = None

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
        self._evidence_stage_labels_cache = None

    async def memorize(self, messages: list[BenchmarkMessage], metadata: dict[str, Any] | None = None) -> None:
        if not messages:
            return
        if self.frozen_store is not None:
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
                "_evidence_stage_labels": self._evidence_stage_labels(context),
            }
        )
        if self.include_retrieval_context:
            answer.metadata["retrieval_context"] = context
        return answer

    def _evidence_stage_labels(self, context: str) -> dict[str, list[str]]:
        if self._evidence_stage_labels_cache is None:
            mem = self._require_mem()
            label_by_segment = {
                segment.segment_id: str(label)
                for source in mem.artifacts.list_sources()
                for segment in source.segments
                if (label := segment.metadata.get("source_label"))
            }
            source_labels = set(label_by_segment.values())
            claim_labels: set[str] = set()
            wiki_labels: set[str] = set()
            for claim in mem.artifacts.list_claims(status="active"):
                labels = {
                    label_by_segment[segment_id]
                    for provenance in claim.provenance
                    for segment_id in provenance.segment_ids
                    if segment_id in label_by_segment
                }
                claim_labels.update(labels)
                if any(mem.wiki.exists(slug) for slug in claim.page_slugs):
                    wiki_labels.update(labels)
            self._evidence_stage_labels_cache = {
                "source": source_labels,
                "claim": claim_labels,
                "wiki": wiki_labels,
            }
        stage_labels = {
            stage: sorted(labels)
            for stage, labels in self._evidence_stage_labels_cache.items()
        }
        stage_labels["context"] = sorted(
            label
            for label in self._evidence_stage_labels_cache["source"]
            if re.search(
                rf"(?<![A-Za-z0-9]){re.escape(label)}(?![A-Za-z0-9])",
                context,
            )
        )
        return stage_labels

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


class MemoryAgentSystem(MyceliumMemorySystem):
    """Selectively gather composed evidence before the normal grounded QA call."""

    name = "memory_agent"

    async def reset(self, case_id: str) -> None:
        await super().reset(case_id)
        self._memory_tools = MemoryToolset(self._require_mem().artifacts)

    async def answer(
        self, question: str, metadata: dict[str, Any] | None = None
    ) -> BenchmarkAnswer:
        mem = self._require_mem()
        metadata = metadata or {}
        started = time.perf_counter()
        loaded_pages = await mem.load_context(
            question,
            budget_tokens=self.context_budget_tokens,
            session_id=str(metadata.get("query_id") or f"{self.case_id}-query"),
        )
        wiki_context = "\n\n".join(
            f"=== MEMORY: {page.title} ({page.slug}) ===\n{format_page_for_prompt(page)}"
            for page in loaded_pages
        )
        source_context = "\n\n".join(
            page.source_context for page in loaded_pages if page.source_context
        )
        initial_context = wiki_context
        if source_context:
            initial_context = (
                f"SYNTHESIZED MEMORY PAGES:\n{wiki_context}\n\n"
                f"CANONICAL SOURCE EVIDENCE:\n{source_context}"
            )

        escalation_reason = memory_escalation_reason(question)
        context = initial_context
        plan: MemoryRetrievalPlan | None = None
        plan_trace: dict[str, Any] | None = None
        planner_input_tokens = 0
        if escalation_reason:
            planner_system = (
                "Create a small read-only retrieval plan for a private personal-memory archive. "
                "Do not answer the question. Produce one focused search for each named subject, "
                "event, relation, or component whose evidence must be combined. Preserve names "
                "from the question and include the relevant relation terms in every search. Use "
                "at most four searches, and never emit paraphrases of the same search. For an "
                "open-ended shared-property question, search each subject separately using the "
                "same relevant dimensions, such as major events, work or projects, and interests. "
                "For a causal question, separate the triggering event, motivation, and resulting "
                "decision. For a multi-attribute description, search distinct dimensions implied "
                "by the question, such as setting, physical features, and constraints, without "
                "inventing their values. Set expand_top_hits=true for comparisons, shared-property "
                "questions, causes, sequences, or when related claims may supply another required "
                "fact. Set inspect_sources=true only when exact attribution, chronology, or source "
                "wording must be verified. Never request outside information."
            )
            planner_input = f"QUESTION:\n{question}"
            planner_input_tokens = count_tokens(
                planner_system + "\n" + planner_input
            )
            raw_plan = await self.qa_client.llm.call_structured(
                planner_system,
                planner_input,
                MemoryRetrievalPlan,
                num_predict=384,
            )
            plan = MemoryRetrievalPlan.model_validate(raw_plan)
            planned_context, plan_trace = execute_memory_plan(
                self._memory_tools, plan
            )
            context = (
                f"PLANNED CANONICAL MEMORY EVIDENCE:\n{planned_context}\n\n"
                f"INITIAL MEMORY EVIDENCE:\n{initial_context}"
            ).strip()

        exploration_seconds = time.perf_counter() - started
        answer = await self.qa_client.answer(question, context)
        answer.memory_construction_time = exploration_seconds
        answer.query_time_len += exploration_seconds
        answer.input_len += planner_input_tokens
        answer.metadata.update({
            "loaded_pages": [
                {
                    "slug": page.slug,
                    "title": page.title,
                    "confidence": page.confidence,
                    "importance": page.importance,
                }
                for page in loaded_pages
            ],
            "memory_agent": {
                "escalated": bool(escalation_reason),
                "reason": escalation_reason,
                "plan": plan.model_dump() if plan else None,
                "trace": plan_trace,
            },
            "_evidence_stage_labels": self._evidence_stage_labels(context),
        })
        if self.include_retrieval_context:
            answer.metadata["retrieval_context"] = context
        return answer


_QUESTION_LEAD_WORDS = {
    "are", "can", "could", "did", "do", "does", "how", "is", "was", "were",
    "what", "when", "where", "which", "who", "why", "will", "would",
}
_COMPOSITION_CUES = re.compile(
    r"\b(both|common|shared|same|different|difference|between|each|respectively)\b",
    re.IGNORECASE,
)
_CAUSAL_CUES = re.compile(
    r"^(why\b|how did\b)|\b(what led to|as a result|because of)\b",
    re.IGNORECASE,
)
_MULTI_ATTRIBUTE_CUES = re.compile(
    r"\b(look like|requirements?|features?|qualities|reasons|ways)\b",
    re.IGNORECASE,
)


def memory_escalation_reason(question: str) -> str | None:
    """Return the structural reason a question needs composed memory evidence."""
    normalized = " ".join(question.split()).strip()
    if not normalized:
        return None
    if _COMPOSITION_CUES.search(normalized):
        return "composition"
    if _CAUSAL_CUES.search(normalized):
        return "causal"
    if _MULTI_ATTRIBUTE_CUES.search(normalized):
        return "multi_attribute"
    names = [
        value
        for value in re.findall(r"\b[A-Z][a-z]+\b", normalized)
        if value.lower() not in _QUESTION_LEAD_WORDS
    ]
    if len(set(names)) >= 2 and re.search(r"\band\b", normalized, re.IGNORECASE):
        return "multiple_subjects"
    return None


def execute_memory_plan(
    tools: MemoryToolset,
    plan: MemoryRetrievalPlan,
) -> tuple[str, dict[str, Any]]:
    """Execute a validated plan with fixed result and provenance bounds."""
    selected_claims: dict[str, dict[str, Any]] = {}
    search_trace: list[dict[str, Any]] = []
    seed_ids: list[str] = []
    for query in plan.searches:
        hits = tools.search(query, limit=5)
        hit_ids = [str(hit["claim_id"]) for hit in hits]
        search_trace.append({"query": query, "claim_ids": hit_ids})
        for hit in hits:
            selected_claims.setdefault(str(hit["claim_id"]), hit)
        seed_ids.extend(hit_ids[:2])

    expanded_ids: list[str] = []
    if plan.expand_top_hits and seed_ids:
        expansions = tools.expand(list(dict.fromkeys(seed_ids))[:6], limit=8)
        expanded_ids = [str(hit["claim_id"]) for hit in expansions]
        for hit in expansions:
            selected_claims.setdefault(str(hit["claim_id"]), hit)

    source_results: list[dict[str, Any]] = []
    if plan.inspect_sources and selected_claims:
        source_results = tools.sources(list(selected_claims)[:4], neighbor_count=1)

    lines = [
        _format_planned_claim(claim)
        for claim in list(selected_claims.values())[:24]
    ]
    if source_results:
        lines.append("\nVERIFIED SOURCE SEGMENTS:")
        for source in source_results:
            occurred_at = source.get("occurred_at") or "unknown time"
            for segment in source.get("segments", []):
                label = segment.get("source_label") or segment.get("segment_id")
                speaker = segment.get("speaker") or "unknown speaker"
                content = str(segment.get("content", ""))[
                    :MAX_PLANNED_SOURCE_SEGMENT_CHARS
                ]
                lines.append(
                    f"- [{label}] ({occurred_at}) {speaker}: {content}"
                )
    rendered, truncated = _bounded_evidence(lines)
    trace = {
        "searches": search_trace,
        "expanded_claim_ids": expanded_ids,
        "selected_claim_ids": list(selected_claims)[:24],
        "source_ids": [str(source.get("source_id")) for source in source_results],
        "evidence_chars": len(rendered),
        "truncated": truncated,
    }
    return rendered, trace


def _format_planned_claim(claim: dict[str, Any]) -> str:
    subjects = ", ".join(str(value) for value in claim.get("subjects", []))
    temporal = claim.get("temporal") or {}
    bounds = ""
    if temporal.get("start") or temporal.get("end"):
        bounds = f"; time={temporal.get('start') or '?'}..{temporal.get('end') or '?'}"
    return (
        f"- [{claim['claim_id']}] {str(claim['text'])[:1000]} "
        f"(subjects={subjects or 'unknown'}{bounds})"
    )


def _bounded_evidence(lines: list[str]) -> tuple[str, bool]:
    if not lines:
        return "No canonical claims matched the retrieval plan.", False
    selected: list[str] = []
    used = 0
    for line in lines:
        added = len(line) + (1 if selected else 0)
        if used + added > MAX_PLANNED_EVIDENCE_CHARS:
            return "\n".join(selected), True
        selected.append(line)
        used += added
    return "\n".join(selected), False


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
    frozen_store: Path | None = None,
    include_retrieval_context: bool = False,
) -> MemorySystem:
    if replay_store is not None and system_name not in {
        "mycelium", "memory_agent", "full_wiki"
    }:
        raise ValueError(
            "--replay-store is only supported by mycelium, memory_agent, and full_wiki"
        )
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
    if system_name == "memory_agent":
        return MemoryAgentSystem(
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
    body = page.content
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
