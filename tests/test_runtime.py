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
from server.runtime import append_tool_event_logs, append_turn, ensure_session_record


@pytest.fixture(autouse=True)
def reset_runtime_locks(monkeypatch):
    monkeypatch.setattr(runtime, "_meta_lock", None)
    monkeypatch.setattr(runtime, "_session_locks", {})


def test_ensure_session_record_initializes_capture_cursor():
    record = {"query": "Test", "transcript": []}

    ensure_session_record(record, "ses")

    assert record["captured_turns"] == 0
    assert "active_episode" not in record


def test_timestamp_free_session_messages_are_rejected():
    record = {
        "query": "Old chat",
        "transcript": [{"role": "user", "content": "hello"}],
    }

    with pytest.raises(ValueError, match="timestamp-free transcript"):
        ensure_session_record(record, "legacy")


@pytest.mark.asyncio
async def test_chat_page_metadata_follows_evidence_that_fits(tmp_path, monkeypatch):
    from mycelium.operations import EvidenceRecord, WikiPageReference

    monkeypatch.setattr(runtime, "SESSIONS_FILE", tmp_path / "sessions.json")
    runtime.save_meta({"chat-budget": {"query": "Schedule", "transcript": []}})
    small = EvidenceRecord(
        record_id="claim-small", record_type="claim", statement="The meeting is at noon.",
        subject_entity_id="subject-small", subject_name="Schedule", claim_ids=("claim-small",),
    )
    large = EvidenceRecord(
        record_id="claim-large", record_type="claim", statement="Long detail " * 2000,
        subject_entity_id="subject-large", subject_name="Details", claim_ids=("claim-large",),
    )
    config = Config.defaults()
    config.context_budget_tokens = 1000
    config.retrieval.tool_evidence_budget_tokens = 300
    mem = SimpleNamespace(
        config=config, retriever=SimpleNamespace(),
        retrieve_context=AsyncMock(return_value=RetrievalResult(
            page_references=(
                WikiPageReference("subject-large", "details", "Details", 1),
                WikiPageReference("subject-small", "schedule", "Schedule", 2),
            ),
            evidence=MemoryEvidence(records=(large, small)), rendered_context="",
        )),
        llm=SimpleNamespace(call_messages=AsyncMock(return_value=SimpleNamespace(
            content="At noon.", tool_events=[],
        ))),
    )
    mem.ingest_source = AsyncMock(return_value=IngestionResult(
        status="captured", source_ids=("source-test",),
    ))
    monkeypatch.setattr(runtime, "get_mem", lambda: mem)
    monkeypatch.setattr(sessions, "get_mem", lambda: mem)

    result = await sessions.chat("chat-budget", sessions.ChatRequest(message="When is it?"))

    assert result["capture_status"] == "captured"
    assert result["loaded_pages"] == [{"slug": "schedule", "title": "Schedule", "version": 2}]
    assert [r["record_id"] for r in result["memory_workspace"]["evidence"]["records"]] == ["claim-small"]
    assert runtime.load_meta()["chat-budget"]["transcript"][-1]["loaded_pages"] == result["loaded_pages"]


def test_append_turn_persists_the_final_memory_workspace():
    meta = {"chat-1": {"query": "Test", "transcript": []}}
    ensure_session_record(meta["chat-1"], "chat-1")
    workspace = {
        "revision": 1,
        "evidence": {"records": [], "sources": [], "more_available": False},
        "operations": [],
    }

    append_turn(
        meta,
        "chat-1",
        "Question",
        "Answer",
        "2026-09-04T10:00:00+00:00",
        "2026-09-04T10:00:01+00:00",
        memory_workspace=workspace,
    )

    assert meta["chat-1"]["transcript"][-1]["memory_workspace"] == workspace
    assert "active_episode" not in meta["chat-1"]


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
        response.update({
                "segment_dispositions": [
                    {
                        "segment_id": response["claims"][0]["segment_ids"][0],
                        "disposition": "claimed",
                        "reason": "The tool result contains a durable observation.",
                    }
                ]
        })
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
    assert artifacts.list_claims() == []
    llm.call_structured.assert_not_awaited()
    await encoder.extract_pending()
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
async def test_automatic_capture_preserves_timestamps_and_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "SESSIONS_FILE", tmp_path / "sessions.json")
    encoder = Encoder(AsyncMock(), LogStore(tmp_path / "logs"), Config.defaults(), ArtifactStore(tmp_path / "artifacts"))
    mem = SimpleNamespace(ingest_source=encoder.ingest_source)
    monkeypatch.setattr(runtime, "get_mem", lambda: mem)
    meta = {"chat-1": {"query": "Plan", "transcript": []}}
    append_turn(meta, "chat-1", "I will finish tomorrow.", "Understood.",
                "2026-08-26T23:59:00+00:00", "2026-08-27T08:00:01+00:00")
    runtime.save_meta(meta)
    original_save = runtime.save_meta
    monkeypatch.setattr(runtime, "save_meta", lambda _: (_ for _ in ()).throw(OSError("interrupted cursor write")))
    with pytest.raises(OSError):
        await runtime.capture_saved_turns("chat-1")
    monkeypatch.setattr(runtime, "save_meta", original_save)
    await runtime.capture_saved_turns("chat-1")
    await runtime.capture_saved_turns("chat-1")
    source = encoder.artifacts.list_sources()[0]
    assert len(encoder.artifacts.list_sources()) == 1
    assert [s.timestamp for s in source.segments] == [
        "2026-08-26T23:59:00+00:00", "2026-08-27T08:00:01+00:00",
    ]
    assert runtime.load_meta()["chat-1"]["captured_turns"] == 1
    assert encoder.artifacts.list_claims() == []
    encoder.llm.call_structured.assert_not_awaited()
    # A later turn retains source pointers for context, rather than duplicating old text.
    meta = runtime.load_meta()
    append_turn(meta, "chat-1", "Actually, next week.", "Noted.",
                "2026-08-27T09:00:00+00:00", "2026-08-27T09:00:01+00:00")
    runtime.save_meta(meta)
    await runtime.capture_saved_turns("chat-1")
    newest = next(s for s in encoder.artifacts.list_sources() if s.source_id != source.source_id)
    assert newest.metadata["context_source_ids"] == [source.source_id]
    assert len(newest.segments) == 2


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
    mem.ingest_source = AsyncMock(return_value=IngestionResult(
        status="captured", source_ids=("source-test",),
    ))
    monkeypatch.setattr(runtime, "get_mem", lambda: mem)
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
