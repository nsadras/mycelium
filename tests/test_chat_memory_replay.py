"""Opt-in, real-model replay of the user's two-conversation smoke test.

MYCELIUM_RUN_CHAT_REPLAY=1 .venv/bin/pytest -q -s tests/test_chat_memory_replay.py
Uses mycelium.toml and a fresh pytest temporary store, never the live store.
"""

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from mycelium import Mycelium
from mycelium.memory_tools import MEMORY_TOOL_DEFINITIONS
from server import runtime
from server.api import sessions


FIXTURE = Path(__file__).parent / "fixtures" / "chat_memory_replay.json"
CONFIG = Path(__file__).resolve().parents[1] / "mycelium.toml"


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("MYCELIUM_RUN_CHAT_REPLAY") != "1",
    reason="Set MYCELIUM_RUN_CHAT_REPLAY=1 to run real Ollama capture/build/chat replay",
)
@pytest.mark.asyncio
async def test_two_conversations_build_one_user_page_and_recall_cooking(tmp_path, monkeypatch):
    fixture = json.loads(FIXTURE.read_text())
    store = tmp_path / "store"
    print(f"Replay artifacts: {tmp_path}", flush=True)
    assert not store.exists()
    memory = Mycelium(store, config_path=CONFIG)
    monkeypatch.setattr(runtime, "SESSIONS_FILE", store / "sessions_meta.json")
    monkeypatch.setattr(runtime, "get_mem", lambda: memory)
    monkeypatch.setattr(sessions, "get_mem", lambda: memory)
    monkeypatch.setattr(runtime, "_meta_lock", None)
    monkeypatch.setattr(runtime, "_dream_lock", None)
    monkeypatch.setattr(runtime, "_session_locks", {})
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    assert [(p.entity_id, p.slug) for p in memory.wiki.list()] == [("you", "you")]
    assert memory.artifacts.list_sources() == []
    assert memory.artifacts.list_claims() == []

    # Persist original completed turns in timestamp order, exactly as chat capture
    # does. Do not regenerate the historical assistant replies or copy derived state.
    meta = {
        c["session_id"]: {"query": c["topic"], "transcript": []}
        for c in fixture["conversations"]
    }
    runtime.save_meta(meta)
    turns = []
    for conversation in fixture["conversations"]:
        messages = conversation["messages"]
        assert len(messages) % 2 == 0
        for index in range(0, len(messages), 2):
            pair = messages[index:index + 2]
            assert [m["role"] for m in pair] == ["user", "assistant"]
            turns.append((pair[-1]["timestamp"], conversation["session_id"], pair))
    for _, session_id, pair in sorted(turns):
        meta = runtime.load_meta()
        meta[session_id]["transcript"].extend(pair)
        runtime.save_meta(meta)
        async with runtime.get_session_lock(session_id):
            await runtime.capture_saved_turns(session_id)
    sources = memory.artifacts.list_sources()
    assert len(sources) == len(turns)
    assert memory.artifacts.list_claims() == []
    source_ids_by_session = {
        c["session_id"]: {s.source_id for s in sources if s.session_id == c["session_id"]}
        for c in fixture["conversations"]
    }
    # Verify the persisted canonical input, not merely the fixture loader.
    for conversation in fixture["conversations"]:
        saved = sorted(
            (s for s in sources if s.session_id == conversation["session_id"]),
            key=lambda s: s.metadata["turn_index"],
        )
        assert [
            {"role": segment.role, "content": segment.content, "timestamp": segment.timestamp}
            for source in saved for segment in source.segments
        ] == conversation["messages"]

    print("Captured both conversations; building memory with configured model.", flush=True)
    report = await runtime.run_consolidation()
    (tmp_path / "build_report.json").write_text(json.dumps(report, indent=2))
    assert report["failures"] == [], report
    assert memory.consolidation_status().pending_sources == 0
    assert all(e.extraction_status == "complete" for e in memory.artifacts.list_episodes())

    pages = memory.wiki.list()
    (tmp_path / "pages.json").write_text(json.dumps([asdict(p) for p in pages], indent=2, default=str))
    user_pages = [p for p in pages if p.page_type == "you" or p.title.casefold() == "you"]
    assert [(p.entity_id, p.slug) for p in user_pages] == [("you", "you")]
    assert not memory.wiki.exists("you-2")
    # The canonical page must actually own supported facts from BOTH conversations;
    # one surviving but empty startup page is not a pass.
    facts = memory.artifacts.list_consolidated_facts(owner_entity_id="you")
    owned_source_ids = {
        provenance.source_id
        for fact in facts for claim_id in fact.member_claim_ids
        for provenance in memory.artifacts.get_claim(claim_id).provenance
    }
    for session_id, source_ids in source_ids_by_session.items():
        assert owned_source_ids & source_ids, f"No user-owned facts from {session_id}"

    recall = fixture["recall"]
    meta = runtime.load_meta()
    assert recall["session_id"] not in meta
    meta[recall["session_id"]] = {"query": recall["topic"], "transcript": []}
    runtime.save_meta(meta)
    # Keep the real chat/model/tool loop, but make this a local-memory test: no web
    # tools or external API keys. Extraction, routing, embeddings and admission are real.
    call_messages = memory.llm.call_messages

    async def local_chat(*args, **kwargs):
        kwargs["tool_definitions"] = MEMORY_TOOL_DEFINITIONS
        return await call_messages(*args, **kwargs)

    monkeypatch.setattr(memory.llm, "call_messages", local_chat)
    print("Build complete; asking the cooking question in an empty third chat.", flush=True)
    response = await sessions.chat(
        recall["session_id"], sessions.ChatRequest(message=recall["message"]),
    )
    (tmp_path / "recall_response.json").write_text(json.dumps(response, indent=2))
    assert response["capture_status"] == "captured", response["capture_error"]
    assert response["response"].strip()
    assert response["retrieval_trace"]["selection_error"] is None
    # Check admitted/rendered evidence, not merely a vector-search candidate or
    # an answer mentioning the dish from general model knowledge.
    records = response["memory_workspace"]["evidence"]["records"]
    citations = [citation for record in records for citation in record["citations"]]
    expected_sources = source_ids_by_session[fixture["expected_retrieval_session_id"]]
    assert {c["source_id"] for c in citations} & expected_sources
    for citation in citations:
        source = memory.artifacts.get_source(citation["source_id"])
        assert citation["segment_ids"]
        assert set(citation["segment_ids"]) <= {s.segment_id for s in source.segments}
    print("PASS: one populated You page and fried-rice citations in the third chat.", flush=True)
