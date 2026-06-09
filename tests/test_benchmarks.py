from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from benchmarks.mycelium_bench.adapters import BenchmarkAnswer, BenchmarkMessage, format_messages_for_memory
from benchmarks.mycelium_bench.adapters import MyceliumMemorySystem
from benchmarks.mycelium_bench.locomo import iter_locomo_sessions, run_locomo
from benchmarks.mycelium_bench.scoring import locomo_score
from mycelium.core import Mycelium


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


def test_format_messages_includes_metadata_and_speaker():
    text = format_messages_for_memory(
        [BenchmarkMessage(role="user", speaker="Avery", content="I adopted Pixel.", message_id="D1:1")],
        {"sample_id": "s1", "session_id": "session_1", "timestamp": "today"},
    )

    assert "Sample: s1" in text
    assert "Session: session_1" in text
    assert "[D1:1] Avery: I adopted Pixel." in text


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


def test_memory_profile_none_skips_seed_profile(tmp_path):
    mem = Mycelium(tmp_path / "store", memory_profile="none")

    assert not mem.wiki.exists("user-profile")


@pytest.mark.asyncio
async def test_mycelium_benchmark_adapter_preserves_raw_transcript_on_encode_failure(tmp_path):
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
    system.mem.encoder.encode = AsyncMock()

    await system.memorize([BenchmarkMessage(role="user", content="Caroline researched adoption agencies.")])

    system.mem.encoder.encode.assert_called_once()
    kwargs = system.mem.encoder.encode.call_args.kwargs
    assert "Raw benchmark session transcript preserved" in kwargs["content"]
    assert "Caroline researched adoption agencies." in kwargs["content"]
    assert system.stats()["encoded_batches"] == 1
