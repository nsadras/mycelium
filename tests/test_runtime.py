import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from mycelium.artifacts import ArtifactStore
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.operations import IngestionResult, MemoryEvidence, RetrievalResult
from mycelium.store import LogStore
from server import runtime
from server.api import sessions
from server.runtime import append_tool_event_logs, ensure_session_record


@pytest.fixture(autouse=True)
def reset_runtime_locks(monkeypatch):
    monkeypatch.setattr(runtime, "_meta_lock", None)
    monkeypatch.setattr(runtime, "_session_locks", {})


def test_ensure_session_record_initializes_episode():
    record = {"query": "Test", "transcript": []}

    ensure_session_record(record, "ses")

    assert record["encoded_episodes"] == []
    assert record["active_episode"]["id"] == "ses-ep-1"
    assert record["active_episode"]["buffer"] == []


def test_timestamp_free_session_messages_are_rejected():
    record = {
        "query": "Old chat",
        "transcript": [{"role": "user", "content": "hello"}],
    }

    with pytest.raises(ValueError, match="timestamp-free transcript"):
        ensure_session_record(record, "legacy")


@pytest.mark.asyncio
async def test_append_tool_event_logs_creates_claim_artifacts(tmp_path, monkeypatch):
    log_store = LogStore(tmp_path / "logs")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "claims": [
            {
                "text": "Ollama version 1.2 supports asynchronous web search.",
                "claim_type": "observation",
                "predicate": "supports",
                "evidence_modality": "tool",
                "about": [{"entity": "Ollama"}],
                "segment_ids": ["source-placeholder"],
                "facets": {"version": "1.2"},
            }
        ],
    }
    encoder = Encoder(llm, log_store, Config.defaults(), artifacts)

    async def source_aware_response(system, user, output_type, **kwargs):
        response = dict(llm.call_structured.return_value)
        response["claims"] = [dict(response["claims"][0])]
        response["claims"][0]["segment_ids"] = [user.split("[", 1)[1].split("]", 1)[0]]
        if "segment_dispositions" in output_type.model_fields:
            return {
                "segment_dispositions": [
                    {
                        "segment_id": response["claims"][0]["segment_ids"][0],
                        "disposition": "claim_bearing",
                        "reason": "The tool result contains a durable observation.",
                    }
                ]
            }
        return response

    llm.call_structured.side_effect = source_aware_response
    monkeypatch.setattr(
        runtime,
        "get_mem",
        lambda: SimpleNamespace(
            log_store=log_store,
            ingest_source=encoder.ingest_source,
        ),
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
            }
        ],
        turn_count=2,
        occurred_at="2026-08-27T12:00:00+00:00",
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
    assert artifacts.list_sources()[0].occurred_at == "2026-08-27T12:00:00+00:00"
    assert (
        artifacts.list_sources()[0].segments[0].timestamp == "2026-08-27T12:00:00+00:00"
    )
    assert artifacts.list_claims()[0].evidence_modality == "tool"


@pytest.mark.asyncio
async def test_append_tool_event_logs_does_not_reingest_memory_reads(monkeypatch):
    ingest_source = AsyncMock()
    monkeypatch.setattr(
        runtime,
        "get_mem",
        lambda: SimpleNamespace(ingest_source=ingest_source),
    )

    created = await append_tool_event_logs(
        "chat-123",
        "chat-123-ep-1",
        [
            {
                "tool_name": "memory_search",
                "arguments": {"query": "prior project"},
                "result": "existing canonical memory",
                "failed": False,
            }
        ],
        turn_count=2,
        occurred_at="2026-08-27T12:00:00+00:00",
    )

    assert created == []
    ingest_source.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_flush_preserves_each_message_timestamp(tmp_path, monkeypatch):
    sessions_file = tmp_path / "sessions_meta.json"
    monkeypatch.setattr(runtime, "SESSIONS_FILE", sessions_file)
    runtime.save_meta(
        {
            "chat-1": {
                "query": "Long chat",
                "transcript": [],
                "episode_seq": 1,
                "encoded_episodes": [],
                "active_episode": {
                    "id": "chat-1-ep-1",
                    "started_at": "2026-08-26T23:59:00+00:00",
                    "last_activity_at": "2026-08-27T08:00:01+00:00",
                    "buffer": [
                        {
                            "role": "user",
                            "content": "I will finish this tomorrow.",
                            "timestamp": "2026-08-26T23:59:00+00:00",
                        },
                        {
                            "role": "assistant",
                            "content": "Understood.",
                            "timestamp": "2026-08-27T08:00:01+00:00",
                        },
                    ],
                    "turn_count": 1,
                },
            }
        }
    )
    ingest_source = AsyncMock(
        return_value=IngestionResult(
            status="complete",
            log_entries=(SimpleNamespace(entry_id="entry-1"),),
        )
    )
    monkeypatch.setattr(
        runtime, "get_mem", lambda: SimpleNamespace(ingest_source=ingest_source)
    )

    result = await runtime.flush_session_episode("chat-1")

    assert result["status"] == "flushed"
    source_input = ingest_source.await_args.args[0]
    assert source_input.session_id == "chat-1-ep-1"
    assert source_input.occurred_at == "2026-08-26T23:59:00+00:00"
    assert [segment.timestamp for segment in source_input.segments] == [
        "2026-08-26T23:59:00+00:00",
        "2026-08-27T08:00:01+00:00",
    ]
    assert runtime.load_meta()["chat-1"]["active_episode"]["buffer"] == []


@pytest.mark.asyncio
async def test_chat_and_manual_flush_are_serialized(tmp_path, monkeypatch):
    sessions_file = tmp_path / "sessions_meta.json"
    monkeypatch.setattr(runtime, "SESSIONS_FILE", sessions_file)
    runtime.save_meta(
        {
            "chat-1": {
                "query": "Concurrency",
                "transcript": [],
                "episode_seq": 1,
                "encoded_episodes": [],
                "active_episode": {
                    "id": "chat-1-ep-1",
                    "started_at": "2026-08-27T10:00:00+00:00",
                    "last_activity_at": "2026-08-27T10:00:00+00:00",
                    "buffer": [],
                    "turn_count": 0,
                },
            }
        }
    )
    generation_started = asyncio.Event()
    finish_generation = asyncio.Event()

    async def call_messages(_messages, **_kwargs):
        generation_started.set()
        await finish_generation.wait()
        return SimpleNamespace(content="Saved reply", tool_events=[])

    ingest_source = AsyncMock(
        return_value=IngestionResult(
            status="complete",
            log_entries=(SimpleNamespace(entry_id="entry-1"),),
        )
    )
    mem = SimpleNamespace(
        retrieve_context=AsyncMock(
            return_value=RetrievalResult((), MemoryEvidence(), "")
        ),
        llm=SimpleNamespace(call_messages=call_messages),
        config=SimpleNamespace(
            context_budget_tokens=32768,
            llm=SimpleNamespace(context_window_tokens=32768),
            retrieval=Config.defaults().retrieval,
        ),
        retriever=SimpleNamespace(),
        ingest_source=ingest_source,
    )
    monkeypatch.setattr(runtime, "get_mem", lambda: mem)
    monkeypatch.setattr(sessions, "get_mem", lambda: mem)
    timestamps = iter(
        [
            "2026-08-27T10:01:00+00:00",
            "2026-08-27T10:01:02+00:00",
        ]
    )
    monkeypatch.setattr(sessions, "iso_now", lambda: next(timestamps))

    chat_task = asyncio.create_task(
        sessions.chat("chat-1", sessions.ChatRequest(message="Save this"))
    )
    await generation_started.wait()
    flush_task = asyncio.create_task(runtime.flush_session_episode("chat-1"))
    await asyncio.sleep(0)
    assert not flush_task.done()

    finish_generation.set()
    chat_result = await chat_task
    flush_result = await flush_task

    assert chat_result["user_timestamp"] == "2026-08-27T10:01:00+00:00"
    assert chat_result["assistant_timestamp"] == "2026-08-27T10:01:02+00:00"
    assert flush_result["status"] == "flushed"
    saved = runtime.load_meta()["chat-1"]
    assert [message["timestamp"] for message in saved["transcript"]] == [
        "2026-08-27T10:01:00+00:00",
        "2026-08-27T10:01:02+00:00",
    ]
    assert saved["encoded_episodes"][0]["id"] == "chat-1-ep-1"
    assert saved["active_episode"]["buffer"] == []


@pytest.mark.asyncio
async def test_concurrent_chats_in_different_sessions_preserve_both(
    tmp_path, monkeypatch
):
    sessions_file = tmp_path / "sessions_meta.json"
    monkeypatch.setattr(runtime, "SESSIONS_FILE", sessions_file)
    runtime.save_meta(
        {
            session_id: {
                "query": session_id,
                "transcript": [],
                "episode_seq": 1,
                "encoded_episodes": [],
                "active_episode": {
                    "id": f"{session_id}-ep-1",
                    "started_at": "2026-08-27T10:00:00+00:00",
                    "last_activity_at": "2026-08-27T10:00:00+00:00",
                    "buffer": [],
                    "turn_count": 0,
                },
            }
            for session_id in ("chat-1", "chat-2")
        }
    )
    both_started = asyncio.Event()
    started_count = 0

    async def call_messages(messages, **_kwargs):
        nonlocal started_count
        started_count += 1
        if started_count == 2:
            both_started.set()
        await both_started.wait()
        request = messages[-1]["content"].split("CURRENT USER REQUEST\n", 1)[-1]
        return SimpleNamespace(
            content=f"Reply to {request}",
            tool_events=[],
        )

    mem = SimpleNamespace(
        retrieve_context=AsyncMock(
            return_value=RetrievalResult((), MemoryEvidence(), "")
        ),
        llm=SimpleNamespace(call_messages=call_messages),
        config=SimpleNamespace(
            context_budget_tokens=32768,
            llm=SimpleNamespace(context_window_tokens=32768),
            retrieval=Config.defaults().retrieval,
        ),
        retriever=SimpleNamespace(),
    )
    monkeypatch.setattr(sessions, "get_mem", lambda: mem)

    await asyncio.gather(
        sessions.chat("chat-1", sessions.ChatRequest(message="First")),
        sessions.chat("chat-2", sessions.ChatRequest(message="Second")),
    )

    saved = runtime.load_meta()
    assert [message["content"] for message in saved["chat-1"]["transcript"]] == [
        "First",
        "Reply to First",
    ]
    assert [message["content"] for message in saved["chat-2"]["transcript"]] == [
        "Second",
        "Reply to Second",
    ]
