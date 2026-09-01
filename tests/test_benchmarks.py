from __future__ import annotations

from pathlib import Path
import json
from datetime import datetime
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

    assert [session_id for session_id, _, _ in sessions] == ["session_1", "session_2", "session_10"]


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
        [BenchmarkMessage(role="user", speaker="Avery", content="I adopted Pixel.", message_id="D1:1")],
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


def test_evidence_survival_records_each_pipeline_stage():
    answer = BenchmarkAnswer(
        output="Pixel",
        input_len=1,
        output_len=1,
        memory_construction_time=0.0,
        query_time_len=0.0,
        metadata={"_evidence_stage_labels": {
            "source": ["D1:1", "D1:2"],
            "claim": ["D1:1"],
            "wiki": [],
            "context": ["D1:1"],
        }},
    )

    _record_evidence_survival(answer, ["D1:1", "D1:2"])

    assert "_evidence_stage_labels" not in answer.metadata
    assert answer.metadata["evidence_survival"]["source"]["recall"] == 1.0
    assert answer.metadata["evidence_survival"]["claim"]["recall"] == 0.5
    assert answer.metadata["evidence_survival"]["wiki"]["recall"] == 0.0
    assert answer.metadata["evidence_survival"]["context"]["recall"] == 0.5


@pytest.mark.asyncio
async def test_run_locomo_sample_index_selects_one_based_sample(tmp_path):
    data_path = tmp_path / "locomo_two_samples.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "sample_id": "tiny-1",
                    "conversation": {
                        "session_1": [{"dia_id": "D1:1", "speaker": "A", "text": "First sample."}],
                    },
                    "qa": [{"question": "First?", "answer": "Pixel", "category": 1}],
                },
                {
                    "sample_id": "tiny-2",
                    "conversation": {
                        "session_1": [{"dia_id": "D1:1", "speaker": "B", "text": "Second sample."}],
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

    predictions = json.loads((tmp_path / "run" / "predictions.json").read_text(encoding="utf-8"))
    assert [sample["sample_id"] for sample in predictions] == ["tiny-2"]


def test_memory_profile_none_skips_seed_profile(tmp_path):
    mem = Mycelium(tmp_path / "store", memory_profile="none")

    assert not mem.wiki.exists("user-profile")


@pytest.mark.asyncio
async def test_qa_client_uses_grounded_structured_answer():
    client = OllamaQaClient("test", "http://localhost:11434")
    client.llm.call_structured = AsyncMock(
        return_value={"answerable": True, "answer": "19 January, 2023", "evidence": "D1:2"}
    )

    answer = await client.answer(
        "When did Jon lose his job?",
        "conversation_time=20 January, 2023\n[D1:2] Jon: Lost my job yesterday.",
    )

    assert answer.output == "19 January, 2023"
    assert answer.metadata["grounding"]["evidence"] == "D1:2"


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
async def test_gold_evidence_system_uses_only_requested_labeled_turns():
    qa_client = type(
        "QaClient",
        (),
        {"answer": AsyncMock(return_value=BenchmarkAnswer(
            output="19 January, 2023",
            input_len=10,
            output_len=3,
            memory_construction_time=0.0,
            query_time_len=0.1,
        ))},
    )()
    system = GoldEvidenceMemorySystem(qa_client)
    await system.reset("case")
    await system.memorize([
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
    ])

    answer = await system.answer(
        "When did Jon lose his job?", {"gold_evidence": ["D1:2"]}
    )

    context = qa_client.answer.await_args.args[1]
    assert "[D1:2]" in context
    assert "conversation_time=20 January, 2023" in context
    assert "[D1:3]" not in context
    assert answer.metadata["oracle"] == "gold_evidence"


@pytest.mark.asyncio
async def test_mycelium_benchmark_adapter_surfaces_encode_failure_without_fallback(tmp_path):
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
    system.mem.encoder.encode_session = AsyncMock(side_effect=ValueError("bad json"))

    with pytest.raises(ValueError, match="bad json"):
        await system.memorize([
            BenchmarkMessage(
                role="user", content="Caroline researched adoption agencies."
            )
        ])

    system.mem.encoder.encode_session.assert_awaited_once()
    assert system.stats()["encoded_batches"] == 0


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
    system.mem.encoder.encode_session = AsyncMock()
    await system.memorize([BenchmarkMessage(role="user", content="must be skipped")])

    copied = tmp_path / "run" / "stores" / "case-1" / "marker.txt"
    assert copied.read_text(encoding="utf-8") == "exact fixture"
    system.mem.encoder.encode_session.assert_not_awaited()
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
        segments=[SourceSegment(
            segment_id="source-one#seg-0001",
            index=0,
            speaker="Jon",
            content="Jon likes dancing.",
        )],
        raw_log_entry_id="2026-08-05#session-one",
    )
    claim = MemoryClaim(
        claim_id="claim-one",
        text="Jon likes dancing.",
        about=[{"entity": "Jon"}],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=[source.segments[0].segment_id],
            raw_log_entry_id=source.raw_log_entry_id,
            speaker="Jon",
        )],
        recorded_at=source.recorded_at,
        links=[{"relation": "supports", "claim_id": "other"}],
        dream_disposition="routed",
        dream_run_id="old-run",
    )
    artifacts.save_source(source)
    artifacts.save_claim(claim)
    artifacts.save_episode(EpisodeManifest(
        episode_id="episode-one",
        source_id=source.source_id,
        source_type=source.source_type,
        occurred_at=source.occurred_at,
        participants=source.participants,
        segment_ids=[source.segments[0].segment_id],
        claim_ids=[claim.claim_id],
        extraction_status="complete",
    ))
    logs.append(LogEntry(
        entry_id=source.raw_log_entry_id,
        session_id=source.session_id,
        timestamp=datetime(2026, 8, 5, 10, 0),
        content="Frozen transcript",
        consolidated=True,
    ))

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
        segments=[SourceSegment(
            segment_id="source-one#seg-0001",
            index=0,
            speaker="Jon",
            content="Jon likes dancing.",
        )],
        raw_log_entry_id="2026-08-05#session-one",
    )
    claim = MemoryClaim(
        claim_id="claim-one",
        text="Jon likes dancing.",
        about=[{"entity": "Jon"}],
        provenance=[ClaimProvenance(
            source_id=source.source_id,
            segment_ids=[source.segments[0].segment_id],
            raw_log_entry_id=source.raw_log_entry_id,
            speaker="Jon",
        )],
        recorded_at=source.recorded_at,
    )
    artifacts.save_source(source)
    artifacts.save_claim(claim)
    person = artifacts.create_entity("person", "Jon")
    from mycelium.artifacts import ClaimPlacement
    artifacts.save_placement(ClaimPlacement(
        claim_id=claim.claim_id,
        owner_entity_id=person.entity_id,
        section_key="timeline",
        linked_entity_ids=[],
        status="placed",
        reason="fixture",
        created_at="2026-08-05T10:00:00",
        updated_at="2026-08-05T10:00:00",
    ))
    artifacts.save_episode(EpisodeManifest(
        episode_id="episode-one",
        source_id=source.source_id,
        source_type=source.source_type,
        occurred_at=None,
        participants=source.participants,
        segment_ids=[source.segments[0].segment_id],
        claim_ids=[claim.claim_id],
        extraction_status="complete",
    ))
    logs.append(LogEntry(
        entry_id=source.raw_log_entry_id,
        session_id=source.session_id,
        timestamp=datetime(2026, 8, 5, 10, 0),
        content="Frozen transcript",
        consolidated=True,
    ))

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

    assert system.mem.artifacts.get_placement("claim-one").owner_entity_id == person.entity_id
    assert system.mem.wiki.get("jon").page_type == "person"
    assert system.mem.log_store.get(source.raw_log_entry_id).consolidated is True
    assert system.stats()["dream_runs"] == 0
