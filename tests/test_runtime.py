from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from mycelium.artifacts import ArtifactStore
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.store import LogStore
from server import runtime
from server.runtime import append_tool_event_logs, ensure_session_record


def test_ensure_session_record_initializes_episode():
    record = {"query": "Test", "transcript": []}

    ensure_session_record(record, "ses")

    assert record["encoded_episodes"] == []
    assert record["active_episode"]["id"] == "ses-ep-1"
    assert record["active_episode"]["buffer"] == []


def test_no_entries_flush_should_preserve_buffer_shape():
    record = {
        "query": "Test",
        "transcript": [{"role": "user", "content": "hello"}],
        "episode_seq": 1,
        "encoded_episodes": [],
        "active_episode": {
            "id": "ses-ep-1",
            "started_at": "2026-05-19T00:00:00+00:00",
            "last_activity_at": "2026-05-19T00:00:00+00:00",
            "buffer": [{"role": "user", "content": "hello"}],
            "turn_count": 1,
        },
    }

    ensure_session_record(record, "ses")

    assert record["active_episode"]["turn_count"] == 1
    assert record["encoded_episodes"] == []


@pytest.mark.asyncio
async def test_append_tool_event_logs_creates_claim_artifacts(tmp_path, monkeypatch):
    log_store = LogStore(tmp_path / "logs")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "claims": [{
            "text": "Ollama version 1.2 supports asynchronous web search.",
            "kind": "tool fact",
            "claim_type": "observation",
            "predicate": "supports",
            "evidence_modality": "tool",
            "about": [{"entity": "Ollama"}],
            "segment_ids": ["source-placeholder"],
            "facets": {"version": "1.2"},
        }],
        "ignored_segment_ids": [],
    }
    encoder = Encoder(llm, log_store, Config.defaults(), artifacts)

    async def source_aware_response(system, user, output_type, **kwargs):
        response = dict(llm.call_structured.return_value)
        response["claims"] = [dict(response["claims"][0])]
        response["claims"][0]["segment_ids"] = [
            user.split("[", 1)[1].split("]", 1)[0]
        ]
        return response

    llm.call_structured.side_effect = source_aware_response
    monkeypatch.setattr(
        runtime, "get_mem", lambda: SimpleNamespace(log_store=log_store, encoder=encoder)
    )

    created = await append_tool_event_logs(
        "chat-123",
        "chat-123-ep-1",
        [
            {
                "tool_name": "web_search",
                "arguments": {"query": "local llm news"},
                "result": "1. Result\nhttps://example.com\nUseful new information.",
                "failed": False,
                "truncated": True,
            }
        ],
        turn_count=2,
    )

    entries = log_store.get_unconsolidated()
    assert len(created) == 1
    assert len(entries) == 1
    assert entries[0].entry_id == created[0].entry_id
    assert entries[0].session_id == "chat-123-ep-1"
    assert "Tool observation from chat." in entries[0].content
    assert "- chat_session_id: chat-123" in entries[0].content
    assert "- tool_name: web_search" in entries[0].content
    assert '"query": "local llm news"' in entries[0].content
    assert "Useful new information." in entries[0].content
    assert artifacts.list_sources()[0].source_type == "tool_observation"
    assert artifacts.list_claims()[0].evidence_modality == "tool"
