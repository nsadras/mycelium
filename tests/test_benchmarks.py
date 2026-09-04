from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from benchmarks.mycelium_bench.adapters import (
    BenchmarkAnswer,
    BenchmarkMessage,
    GoldEvidenceMemorySystem,
    OllamaQaClient,
    format_messages_for_memory,
)
from benchmarks.mycelium_bench.adapters import MyceliumMemorySystem
from benchmarks.mycelium_bench.locomo import (
    _record_evidence_survival,
    _record_retrieval_evidence,
    iter_locomo_sessions,
    run_locomo,
    select_questions_per_category,
)
from benchmarks.mycelium_bench.scoring import locomo_score
from mycelium.core import Mycelium
from mycelium.context import render_memory_context
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.models import LogEntry, WikiPage
from mycelium.ollama import AgentExecutionStep, ChatResponse, ToolEvent
from mycelium.store import LogStore


class FakeMemorySystem:
    name = "fake"

    def __init__(self) -> None:
        self.messages = []

    async def reset(self, case_id: str) -> None:
        self.case_id = case_id
        self.messages = []

    async def memorize(self, messages, metadata=None) -> None:
        self.messages.extend(messages)

    async def answer(self, question: str, metadata=None) -> BenchmarkAnswer:
        return BenchmarkAnswer(
            output="Pixel",
            input_len=3,
            output_len=1,
            memory_construction_time=0.01,
            query_time_len=0.02,
            metadata={"loaded_pages": []},
        )

    async def finalize_case(self) -> None:
        return None

    def stats(self):
        return {"messages": len(self.messages)}


class EvidenceMemorySystem(FakeMemorySystem):
    async def answer(self, question: str, metadata=None) -> BenchmarkAnswer:
        answer = await super().answer(question, metadata)
        answer.metadata["retrieval_context"] = "[D1:1] Avery adopted Pixel."
        return answer


class EmptyEvidenceMemorySystem(FakeMemorySystem):
    async def answer(self, question: str, metadata=None) -> BenchmarkAnswer:
        answer = await super().answer(question, metadata)
        answer.metadata["retrieval_context"] = ""
        return answer


def test_locomo_session_parser_orders_sessions():
    sample = {
        "conversation": {
            "session_10": [{"dia_id": "D10:1", "speaker": "B", "text": "late"}],
            "session_2": [{"dia_id": "D2:1", "speaker": "A", "text": "middle"}],
            "session_1": [{"dia_id": "D1:1", "speaker": "A", "text": "early"}],
        }
    }

    sessions = iter_locomo_sessions(sample)

    assert [session_id for session_id, _, _ in sessions] == [
        "session_1",
        "session_2",
        "session_10",
    ]


def test_select_questions_per_category_preserves_source_indices():
    questions = [
        (0, {"category": 1}),
        (1, {"category": 1}),
        (2, {"category": 2}),
        (3, {"category": 2}),
    ]

    selected = select_questions_per_category(questions, 1)

    assert [index for index, _ in selected] == [0, 2]


def test_format_messages_includes_metadata_and_speaker():
    text = format_messages_for_memory(
        [
            BenchmarkMessage(
                role="user",
                speaker="Avery",
                content="I adopted Pixel.",
                message_id="D1:1",
            )
        ],
        {"sample_id": "s1", "session_id": "session_1", "timestamp": "today"},
    )

    assert "Sample: s1" in text
    assert "Session: session_1" in text
    assert "[D1:1] Avery: I adopted Pixel." in text


def test_benchmark_page_rendering_renders_nested_recall_fact_once():
    now = datetime.now().astimezone()
    page = WikiPage(
        slug="single-fact",
        title="Single Fact",
        content="## Key Facts\n\n### Current Context\n- A single useful fact.",
        created=now,
        last_updated=now,
        version=1,
    )

    assert render_memory_context([page]).count("A single useful fact") == 1


def test_locomo_score_matches_multi_answer_parts():
    assert locomo_score("running, pottery", "Running, pottery", 1) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_run_locomo_writes_predictions(tmp_path):
    summary = await run_locomo(
        data_path=Path("tests/fixtures/locomo_tiny.json"),
        output_dir=tmp_path,
        system=FakeMemorySystem(),
        prediction_key="fake_prediction",
    )

    assert summary["count"] == 1
    assert summary["mean_score"] == pytest.approx(1.0)
    assert (tmp_path / "predictions.json").exists()
    assert (tmp_path / "predictions.jsonl").exists()
    assert (tmp_path / "summary.json").exists()


@pytest.mark.asyncio
async def test_run_locomo_can_finalize_a_bounded_session_prefix(tmp_path):
    data_path = tmp_path / "locomo.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "bounded",
                    "conversation": {
                        "session_1": [
                            {"dia_id": "D1:1", "speaker": "A", "text": "First."}
                        ],
                        "session_2": [
                            {"dia_id": "D2:1", "speaker": "A", "text": "Second."}
                        ],
                        "session_3": [
                            {"dia_id": "D3:1", "speaker": "A", "text": "Third."}
                        ],
                    },
                    "qa": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    system = FakeMemorySystem()

    await run_locomo(
        data_path=data_path,
        output_dir=tmp_path / "run",
        system=system,
        prediction_key="fake_prediction",
        max_sessions=2,
    )

    assert [message.message_id for message in system.messages] == ["D1:1", "D2:1"]


@pytest.mark.asyncio
async def test_run_locomo_reports_labeled_retrieval_evidence_recall(tmp_path):
    summary = await run_locomo(
        data_path=Path("tests/fixtures/locomo_tiny.json"),
        output_dir=tmp_path,
        system=EvidenceMemorySystem(),
        prediction_key="fake_prediction",
    )

    row = json.loads((tmp_path / "predictions.jsonl").read_text(encoding="utf-8"))
    assert row["metadata"]["retrieval_evidence"] == {
        "required": ["D1:1"],
        "present": ["D1:1"],
        "recall": 1.0,
        "all_evidence_present": True,
    }
    assert summary["retrieval_evidence"] == {
        "question_count": 1,
        "mean_recall": 1.0,
        "all_evidence_question_rate": 1.0,
    }


@pytest.mark.asyncio
async def test_run_locomo_counts_empty_retrieval_context_as_zero_recall(tmp_path):
    summary = await run_locomo(
        data_path=Path("tests/fixtures/locomo_tiny.json"),
        output_dir=tmp_path,
        system=EmptyEvidenceMemorySystem(),
        prediction_key="fake_prediction",
    )

    assert summary["retrieval_evidence"] == {
        "question_count": 1,
        "mean_recall": 0.0,
        "all_evidence_question_rate": 0.0,
    }


def test_evidence_survival_records_exact_and_partial_segment_coverage():
    answer = BenchmarkAnswer(
        output="Pixel",
        input_len=1,
        output_len=1,
        memory_construction_time=0.0,
        query_time_len=0.0,
        metadata={
            "_evidence_stage_segments": {
                "segments_by_label": {
                    "D1:1": ["source-a#seg-0001", "source-a#seg-0002"],
                    "D1:2": ["source-a#seg-0003"],
                },
                "stages": {
                    "source": [
                        "source-a#seg-0001",
                        "source-a#seg-0002",
                        "source-a#seg-0003",
                    ],
                    "claim": ["source-a#seg-0001", "source-a#seg-0003"],
                    "wiki": [],
                    "context": ["source-a#seg-0001", "source-a#seg-0002"],
                },
            }
        },
    )

    _record_evidence_survival(answer, ["D1:1", "D1:2"])

    assert "_evidence_stage_segments" not in answer.metadata
    assert answer.metadata["evidence_survival"]["source"]["recall"] == 1.0
    assert answer.metadata["evidence_survival"]["claim"] == {
        "required": ["D1:1", "D1:2"],
        "present": ["D1:2"],
        "partially_present": ["D1:1"],
        "missing": [],
        "label_coverage": {"D1:1": 0.5, "D1:2": 1.0},
        "recall": 0.75,
        "all_evidence_present": False,
    }
    assert answer.metadata["evidence_survival"]["wiki"]["recall"] == 0.0
    assert answer.metadata["evidence_survival"]["context"]["recall"] == 0.5


def test_evidence_stage_segments_tracks_exact_ids_instead_of_turn_labels():
    first = SourceSegment(
        segment_id="source-a#seg-0001",
        index=0,
        content="First sentence.",
        metadata={"source_label": "D1:1"},
    )
    second = SourceSegment(
        segment_id="source-a#seg-0002",
        index=1,
        content="Second sentence.",
        metadata={"source_label": "D1:1"},
    )
    source = SimpleNamespace(segments=[first, second])
    claim = MemoryClaim(
        claim_id="claim-one",
        text="First sentence.",
        about=[{"entity": "Evan"}],
        provenance=[
            ClaimProvenance(
                source_id="source-a",
                segment_ids=[first.segment_id],
                raw_log_entry_id="log-one",
                speaker="Evan",
            )
        ],
        recorded_at="2026-09-04T00:00:00",
    )
    artifacts = SimpleNamespace(
        list_sources=lambda: [source],
        list_claims=lambda status: [claim],
        placement_for_claim=lambda claim_id: SimpleNamespace(
            owner_entity_id="person-evan"
        ),
        get_entity=lambda entity_id: SimpleNamespace(slug="evan"),
    )
    system = object.__new__(MyceliumMemorySystem)
    system.mem = SimpleNamespace(
        artifacts=artifacts,
        wiki=SimpleNamespace(exists=lambda slug: True),
    )
    system._evidence_stage_segments_cache = None

    stages = system._evidence_stage_segments(
        "The label D1:1 alone is not evidence. `source-a#seg-0002` is."
    )

    assert stages["segments_by_label"] == {
        "D1:1": ["source-a#seg-0001", "source-a#seg-0002"]
    }
    assert stages["stages"]["claim"] == ["source-a#seg-0001"]
    assert stages["stages"]["wiki"] == ["source-a#seg-0001"]
    assert stages["stages"]["context"] == ["source-a#seg-0002"]


def test_retrieval_evidence_uses_exact_context_survival_when_available():
    context_report = {
        "required": ["D1:1"],
        "present": [],
        "partially_present": ["D1:1"],
        "missing": [],
        "label_coverage": {"D1:1": 0.5},
        "recall": 0.5,
        "all_evidence_present": False,
    }
    answer = BenchmarkAnswer(
        output="Pixel",
        input_len=1,
        output_len=1,
        memory_construction_time=0.0,
        query_time_len=0.0,
        metadata={
            "retrieval_context": "A printed D1:1 label is not exact coverage.",
            "evidence_survival": {"context": context_report},
        },
    )

    _record_retrieval_evidence(answer, ["D1:1"])

    assert answer.metadata["retrieval_evidence"] == context_report
    assert answer.metadata["retrieval_evidence"] is not context_report


@pytest.mark.asyncio
async def test_run_locomo_sample_index_selects_one_based_sample(tmp_path):
    data_path = tmp_path / "locomo_two_samples.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "tiny-1",
                    "conversation": {
                        "session_1": [
                            {"dia_id": "D1:1", "speaker": "A", "text": "First sample."}
                        ],
                    },
                    "qa": [{"question": "First?", "answer": "Pixel", "category": 1}],
                },
                {
                    "sample_id": "tiny-2",
                    "conversation": {
                        "session_1": [
                            {"dia_id": "D1:1", "speaker": "B", "text": "Second sample."}
                        ],
                    },
                    "qa": [{"question": "Second?", "answer": "Pixel", "category": 1}],
                },
            ]
        ),
        encoding="utf-8",
    )
    system = FakeMemorySystem()

    await run_locomo(
        data_path=data_path,
        output_dir=tmp_path / "run",
        system=system,
        prediction_key="fake_prediction",
        sample_index=2,
    )

    predictions = json.loads(
        (tmp_path / "run" / "predictions.json").read_text(encoding="utf-8")
    )
    assert [sample["sample_id"] for sample in predictions] == ["tiny-2"]


def test_memory_profile_none_skips_seed_profile(tmp_path):
    mem = Mycelium(tmp_path / "store", memory_profile="none")

    assert not mem.wiki.exists("user-profile")


@pytest.mark.asyncio
async def test_qa_client_uses_grounded_structured_answer():
    client = OllamaQaClient("test", "http://localhost:11434")
    client.llm.call_structured = AsyncMock(
        return_value={
            "answerable": True,
            "answer": "19 January, 2023",
            "evidence": "D1:2",
        }
    )

    answer = await client.answer(
        "When did Jon lose his job?",
        "conversation_time=20 January, 2023\n[D1:2] Jon: Lost my job yesterday.",
    )

    assert answer.output == "19 January, 2023"
    assert answer.metadata["grounding"]["evidence"] == "D1:2"
    assert "num_predict" not in client.llm.call_structured.await_args.kwargs


@pytest.mark.asyncio
async def test_qa_client_returns_consistent_refusal_for_unsupported_premise():
    client = OllamaQaClient("test", "http://localhost:11434")
    client.llm.call_structured = AsyncMock(
        return_value={"answerable": False, "answer": "", "evidence": None}
    )

    answer = await client.answer(
        "Why did Gina close her bank account?",
        "[D8:1] Jon: I had to shut down my bank account.",
    )

    assert answer.output == "I do not have enough information to answer this question."


@pytest.mark.asyncio
async def test_qa_client_exposes_bounded_memory_tools_and_records_their_evidence():
    client = OllamaQaClient("test", "http://localhost:11434")
    client.llm.call_messages = AsyncMock(
        return_value=ChatResponse(
            content="watercolor painting",
            tool_events=[
                ToolEvent(
                    tool_name="memory_search",
                    arguments={"query": "Sam creative outlet"},
                    result=(
                        "<memory-search-results>\n"
                        "Statement: Sam practiced watercolor painting.\n"
                        "</memory-search-results>"
                    ),
                )
            ],
            execution_trace=[
                AgentExecutionStep(
                    attempt_index=1,
                    round_index=1,
                    thinking="The supplied evidence is about the wrong person.",
                    content="",
                    tool_calls=[
                        {
                            "tool_name": "memory_search",
                            "arguments": {"query": "Sam creative outlet"},
                        }
                    ],
                    outcome="tools_executed",
                )
            ],
            metadata={"done_reason": "stop"},
        )
    )
    tools = SimpleNamespace(
        search_limit=3,
        remaining_evidence_tokens=6000,
        run=AsyncMock(),
    )

    answer = await client.answer_with_memory_tools(
        "What creative outlet did Sam use?",
        "Evan practiced watercolor painting.",
        tools,
    )

    call = client.llm.call_messages.await_args
    definitions = call.kwargs["tool_definitions"]
    assert [item["function"]["name"] for item in definitions] == [
        "memory_sources",
        "memory_search",
    ]
    assert call.kwargs["tool_runner"] is tools.run
    assert call.kwargs["max_tool_rounds"] == 3
    assert "num_predict" not in call.kwargs
    assert call.kwargs["num_ctx"] == client.llm.context_window_tokens
    assert answer.output == "watercolor painting"
    assert answer.metadata["memory_tool_events"][0]["tool_name"] == "memory_search"
    assert answer.metadata["agent_execution_trace"][0]["thinking"] == (
        "The supplied evidence is about the wrong person."
    )


@pytest.mark.asyncio
async def test_gold_evidence_system_uses_only_requested_labeled_turns():
    qa_client = type(
        "QaClient",
        (),
        {
            "answer": AsyncMock(
                return_value=BenchmarkAnswer(
                    output="19 January, 2023",
                    input_len=10,
                    output_len=3,
                    memory_construction_time=0.0,
                    query_time_len=0.1,
                )
            )
        },
    )()
    system = GoldEvidenceMemorySystem(qa_client)
    await system.reset("case")
    await system.memorize(
        [
            BenchmarkMessage(
                role="user",
                speaker="Jon",
                content="I lost my job yesterday.",
                timestamp="20 January, 2023",
                message_id="D1:2",
            ),
            BenchmarkMessage(
                role="user",
                speaker="Gina",
                content="I opened a store.",
                timestamp="20 January, 2023",
                message_id="D1:3",
            ),
        ]
    )

    answer = await system.answer(
        "When did Jon lose his job?", {"gold_evidence": ["D1:2"]}
    )

    context = qa_client.answer.await_args.args[1]
    assert "[D1:2]" in context
    assert "conversation_time=20 January, 2023" in context
    assert "[D1:3]" not in context
    assert answer.metadata["oracle"] == "gold_evidence"


@pytest.mark.asyncio
async def test_mycelium_benchmark_adapter_surfaces_encode_failure_without_fallback(
    tmp_path,
):
    class FakeQa:
        pass

    system = MyceliumMemorySystem(
        run_dir=tmp_path,
        qa_client=FakeQa(),
        memory_model="test",
        ollama_url="http://localhost:11434",
        dream_policy="none",
    )
    await system.reset("case-1")
    system.mem.ingest_source = AsyncMock(side_effect=ValueError("bad json"))

    with pytest.raises(ValueError, match="bad json"):
        await system.memorize(
            [
                BenchmarkMessage(
                    role="user", content="Caroline researched adoption agencies."
                )
            ]
        )

    system.mem.ingest_source.assert_awaited_once()
    assert system.stats()["encoded_batches"] == 0


@pytest.mark.asyncio
async def test_mycelium_benchmark_leaves_segments_unspecified_for_transcript_ingestion(
    tmp_path,
):
    class FakeQa:
        pass

    system = MyceliumMemorySystem(
        run_dir=tmp_path,
        qa_client=FakeQa(),
        memory_model="test",
        ollama_url="http://localhost:11434",
        dream_policy="none",
    )
    await system.reset("case-1")
    system.mem.ingest_source = AsyncMock()

    await system.memorize(
        [
            BenchmarkMessage(
                role="user", content="Caroline researched adoption agencies."
            )
        ]
    )

    source_input = system.mem.ingest_source.await_args.args[0]
    assert source_input.transcript
    assert source_input.segments is None


@pytest.mark.asyncio
async def test_frozen_store_is_copied_exactly_and_skips_memorization(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "marker.txt").write_text("exact fixture", encoding="utf-8")
    system = MyceliumMemorySystem(
        run_dir=tmp_path / "run",
        qa_client=object(),
        memory_model="test",
        ollama_url="http://localhost:11434",
        dream_policy="none",
        frozen_store=fixture,
    )

    await system.reset("case-1")
    system.mem.ingest_source = AsyncMock()
    await system.memorize([BenchmarkMessage(role="user", content="must be skipped")])

    copied = tmp_path / "run" / "stores" / "case-1" / "marker.txt"
    assert copied.read_text(encoding="utf-8") == "exact fixture"
    system.mem.ingest_source.assert_not_awaited()
    assert system.stats()["encoded_batches"] == 0


@pytest.mark.asyncio
async def test_mycelium_benchmark_replays_frozen_extraction_artifacts(tmp_path):
    fixture = tmp_path / "fixture"
    artifacts = ArtifactStore(fixture / "artifacts")
    logs = LogStore(fixture / "logs")
    source = SourceDocument(
        source_id="source-one",
        source_type="multi_party_conversation",
        session_id="session_1",
        recorded_at="2026-08-05T10:00:00",
        occurred_at="2023-01-01T10:00:00",
        participants=["Jon"],
        segments=[
            SourceSegment(
                segment_id="source-one#seg-0001",
                index=0,
                speaker="Jon",
                content="Jon likes dancing.",
            )
        ],
        raw_log_entry_id="2026-08-05#session-one",
    )
    claim = MemoryClaim(
        claim_id="claim-one",
        text="Jon likes dancing.",
        about=[{"entity": "Jon"}],
        provenance=[
            ClaimProvenance(
                source_id=source.source_id,
                segment_ids=[source.segments[0].segment_id],
                raw_log_entry_id=source.raw_log_entry_id,
                speaker="Jon",
            )
        ],
        recorded_at=source.recorded_at,
        links=[{"relation": "supports", "claim_id": "other"}],
        dream_disposition="routed",
        dream_run_id="old-run",
    )
    artifacts.save_source(source)
    artifacts.save_claim(claim)
    artifacts.save_episode(
        EpisodeManifest(
            episode_id="episode-one",
            source_id=source.source_id,
            source_type=source.source_type,
            occurred_at=source.occurred_at,
            participants=source.participants,
            segment_ids=[source.segments[0].segment_id],
            claim_ids=[claim.claim_id],
            extraction_status="complete",
        )
    )
    logs.append(
        LogEntry(
            entry_id=source.raw_log_entry_id,
            session_id=source.session_id,
            timestamp=datetime(2026, 8, 5, 10, 0),
            content="Frozen transcript",
            consolidated=True,
        )
    )

    system = MyceliumMemorySystem(
        run_dir=tmp_path / "run",
        qa_client=object(),
        memory_model="test",
        ollama_url="http://localhost:11434",
        dream_policy="none",
        replay_store=fixture,
    )
    await system.reset("case-1")
    await system.memorize(
        [BenchmarkMessage(role="user", content="Ignored because replay is enabled.")],
        {"session_id": "session_1"},
    )

    replayed = system.mem.artifacts.get_claim("claim-one")
    assert replayed.text == claim.text
    assert system.mem.artifacts.placement_for_claim("claim-one") is None
    assert replayed.links == []
    assert replayed.dream_disposition == "pending"
    assert replayed.dream_run_id is None
    assert system.mem.log_store.get(source.raw_log_entry_id).consolidated is False


@pytest.mark.asyncio
async def test_assignment_replay_preserves_routes_and_rebuilds_pages(tmp_path):
    fixture = tmp_path / "fixture"
    artifacts = ArtifactStore(fixture / "artifacts")
    logs = LogStore(fixture / "logs")
    source = SourceDocument(
        source_id="source-one",
        source_type="multi_party_conversation",
        session_id="session_1",
        recorded_at="2026-08-05T10:00:00",
        occurred_at=None,
        participants=["Jon"],
        segments=[
            SourceSegment(
                segment_id="source-one#seg-0001",
                index=0,
                speaker="Jon",
                content="Jon likes dancing.",
            )
        ],
        raw_log_entry_id="2026-08-05#session-one",
    )
    claim = MemoryClaim(
        claim_id="claim-one",
        text="Jon likes dancing.",
        about=[{"entity": "Jon"}],
        provenance=[
            ClaimProvenance(
                source_id=source.source_id,
                segment_ids=[source.segments[0].segment_id],
                raw_log_entry_id=source.raw_log_entry_id,
                speaker="Jon",
            )
        ],
        recorded_at=source.recorded_at,
    )
    artifacts.save_source(source)
    artifacts.save_claim(claim)
    person = artifacts.create_entity("person", "Jon")
    from mycelium.artifacts import ClaimPlacement

    artifacts.save_placement(
        ClaimPlacement(
            claim_id=claim.claim_id,
            owner_entity_id=person.entity_id,
            section_key="timeline",
            linked_entity_ids=[],
            status="placed",
            reason="fixture",
            created_at="2026-08-05T10:00:00",
            updated_at="2026-08-05T10:00:00",
        )
    )
    artifacts.save_episode(
        EpisodeManifest(
            episode_id="episode-one",
            source_id=source.source_id,
            source_type=source.source_type,
            occurred_at=None,
            participants=source.participants,
            segment_ids=[source.segments[0].segment_id],
            claim_ids=[claim.claim_id],
            extraction_status="complete",
        )
    )
    logs.append(
        LogEntry(
            entry_id=source.raw_log_entry_id,
            session_id=source.session_id,
            timestamp=datetime(2026, 8, 5, 10, 0),
            content="Frozen transcript",
            consolidated=True,
        )
    )

    system = MyceliumMemorySystem(
        run_dir=tmp_path / "run",
        qa_client=object(),
        memory_model="test",
        ollama_url="http://localhost:11434",
        dream_policy="per-batch",
        replay_store=fixture,
        replay_assignments=True,
    )
    await system.reset("case-1")
    await system.memorize(
        [BenchmarkMessage(role="user", content="Ignored.")],
        {"session_id": "session_1"},
    )

    assert (
        system.mem.artifacts.get_placement("claim-one").owner_entity_id
        == person.entity_id
    )
    assert system.mem.wiki.get("jon").page_type == "person"
    assert system.mem.log_store.get(source.raw_log_entry_id).consolidated is True
    assert system.stats()["dream_runs"] == 0
