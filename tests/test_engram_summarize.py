from unittest.mock import AsyncMock

import pytest

from engram.summarize import EngramSummarizer


@pytest.mark.asyncio
async def test_oversized_meeting_summary_batches_and_reduces_without_dropping_ends():
    summarizer = EngramSummarizer(
        ollama_url="http://localhost:11434",
        model="test-model",
        context_window_tokens=8192,
    )
    calls: list[str] = []

    async def fake_call(system, user, schema, **kwargs):
        calls.append(user)
        if "Partial summaries in chronological order" in user:
            return {
                "summary": "FIRST MARKER and LAST MARKER",
                "decisions": ["Keep all evidence"],
                "action_items": [],
                "open_questions": [],
            }
        markers = [marker for marker in ("FIRST MARKER", "LAST MARKER") if marker in user]
        return {
            "summary": " ".join(markers) or "middle",
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        }

    summarizer.llm.call_structured = AsyncMock(side_effect=fake_call)
    transcript = "FIRST MARKER\n" + ("middle discussion " * 4000) + "\nLAST MARKER"

    result = await summarizer.summarize("Long meeting", transcript)

    transcript_calls = [call for call in calls if "Transcript:" in call]
    assert len(transcript_calls) > 1
    assert any("FIRST MARKER" in call for call in transcript_calls)
    assert any("LAST MARKER" in call for call in transcript_calls)
    assert result.summary == "FIRST MARKER and LAST MARKER"
    assert result.decisions == ["Keep all evidence"]
