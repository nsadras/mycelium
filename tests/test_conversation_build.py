"""Conversation-sized work and partial admission without semantic repair."""

import json
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium, SourceInput, memory_contract
from mycelium.artifacts import SourceSegment
from mycelium.config import Config, LLMConfig
from mycelium.memory_admission import retention
from mycelium.memory_budget import retention_size
from tests.lifecycle_support import lifecycle_response


def configured(memory, monkeypatch):
    monkeypatch.setattr(memory.retriever.claim_index, "search", AsyncMock(return_value=[]))
    memory.llm.call_structured = AsyncMock(side_effect=lifecycle_response)


async def capture(memory, text, session="conversation", date="2034-06-03"):
    return await memory.ingest_source(SourceInput(text, session, occurred_at=date,
        segments=(SourceSegment("", 0, text, speaker="user", role="user", timestamp=date),)))


@pytest.mark.asyncio
async def test_pending_chat_turns_share_one_decision_and_preserve_each_source(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configured(memory, monkeypatch)
        first = await capture(memory, "I can inspect the pump.")
        second = await capture(memory, "Only after the electrician approves it.", date="2034-06-04")
        def respond(system, user, schema, **kwargs):
            result = lifecycle_response(system, user, schema, **kwargs)
            if kwargs["debug_label"] == "memory-retention":
                result["subjects"][0]["participant_ids"] = [p["id"] for p in json.loads(user)["participants"]]
            return result

        memory.llm.call_structured.side_effect = respond
        seen = []
        original = memory_contract.retain

        async def inspect(llm, payload):
            seen.append(payload)
            assert len(payload["segments"]) == 2
            assert {s["source_time"] for s in payload["segments"]} == {"2034-06-03", "2034-06-04"}
            assert {p["source_id"] for p in payload["participants"]} == set(first.source_ids + second.source_ids)
            return await original(llm, payload)

        monkeypatch.setattr(memory_contract, "retain", inspect)
        result = await memory.consolidate()
        assert not result.report.failures
        assert set(result.processed_episode_ids) == set(first.episode_ids + second.episode_ids)
        assert len(seen) == 1
        assert [c.kwargs["debug_label"] for c in memory.llm.call_structured.call_args_list] == ["memory-retention", "memory-presentation"]
        episodes = memory.artifacts.list_episodes()
        assert len({e.extraction_batches[0].batch_id for e in episodes}) == 1
        for episode in episodes:
            claim, = [memory.artifacts.get_claim(cid) for cid in episode.claim_ids]
            assert claim.provenance[0].source_id == episode.source_id
            assert episode.extraction_batches[0].diagnostics["omitted"]["context_segment_ids"] == []
        bindings = [memory.db.get("participant-bindings", pid) for pid in memory.db.ids("participant-bindings")]
        assert {b["source_id"] for b in bindings} == set(first.source_ids + second.source_ids)
        assert {b["entity_id"] for b in bindings} == {"you"}
    with Mycelium(tmp_path) as memory:
        configured(memory, monkeypatch)
        await memory.consolidate()
        memory.llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_follow_on_turn_receives_processed_conversation_without_reextracting(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configured(memory, monkeypatch)
        first = await capture(memory, "I can inspect the pump.")
        await memory.consolidate()
        previous = {c.claim_id for c in memory.artifacts.list_claims()}
        second = await capture(memory, "The electrician approved it.")
        original = memory_contract.retain

        async def inspect(llm, payload):
            assert {s["source_id"] for s in payload["segments"]} == set(second.source_ids)
            assert {s["source_id"] for s in payload["context_segments"]} == set(first.source_ids)
            roster = {p["id"]: p for p in payload["participants"]}
            for segment in payload["segments"] + payload["context_segments"]:
                assert roster[segment["participant_id"]]["source_id"] == segment["source_id"]
                assert roster[segment["participant_id"]]["subject_id"] == "you"
            return await original(llm, payload)

        monkeypatch.setattr(memory_contract, "retain", inspect)
        memory.llm.call_structured.reset_mock()
        assert not (await memory.consolidate()).report.failures
        assert previous < {c.claim_id for c in memory.artifacts.list_claims()}
        assert memory.llm.call_structured.await_count == 2


@pytest.mark.asyncio
async def test_short_segments_do_not_force_multiple_calls_when_compacted_request_fits(tmp_path, monkeypatch):
    config = Config(llm=LLMConfig(context_window_tokens=65536))
    with Mycelium(tmp_path, config=config) as memory:
        configured(memory, monkeypatch)
        lines = tuple(SourceSegment("", i, "The next item is ready for review.", speaker="Alex",
            participant_id="speaker-0", metadata={"engram_segment_id": f"audio-{i}"}) for i in range(884))
        await memory.ingest_source(SourceInput("Recorded discussion", "meeting", source_type="meeting_transcript", segments=lines))
        sizes = []

        async def retain(llm, payload):
            sizes.append(retention_size(payload))
            assert len(payload["segments"]) == len(lines)
            return {"subjects": [], "memories": [], "changes": []}

        monkeypatch.setattr(memory_contract, "retain", retain)
        assert not (await memory.consolidate()).report.failures
        assert len(sizes) == 1 and sizes[0] < 65536 - 8192 - 2048


@pytest.mark.asyncio
async def test_partial_output_keeps_good_records_once_and_exposes_rejections(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configured(memory, monkeypatch)
        await capture(memory, "I will inspect the pump.")

        def respond(system, user, schema, **kwargs):
            result = lifecycle_response(system, user, schema, **kwargs)
            if kwargs["debug_label"] == "memory-retention":
                data = json.loads(user)
                subject = data["new_subject_ids"][0]
                result["subjects"].append({"id": subject, "title": "Pump", "entity_type": "topic",
                                           "participant_ids": [data["participants"][0]["id"]]})
                result["memories"].append({"id": "bad", "text": "Unsupported memory", "subject_ids": [subject], "segment_ids": ["missing"]})
                result["changes"].append({"earlier_id": "missing", "later_id": "bad", "relation": "supersedes", "reason": "Invalid dependency"})
            return result

        memory.llm.call_structured.side_effect = respond
        result = await memory.consolidate()
        assert not result.report.failures and not result.report.pending_source_ids
        assert {w["collection"] for w in result.report.warnings} == {"participant_bindings", "memories", "changes"}
        assert {c.text for c in memory.artifacts.list_claims()} == {"I will inspect the pump."}
        assert memory.llm.call_structured.await_count == 2
        batch = memory.artifacts.list_episodes()[0].extraction_batches[0]
        assert len(batch.response["_rejections"]) == 3
        assert memory.artifacts.list_dream_runs()[-1].warnings == result.report.warnings
        await memory.consolidate()
        assert memory.llm.call_structured.await_count == 2


def test_rejected_subjects_and_duplicate_ids_cannot_leave_dangling_claims():
    payload = {"participants": [], "segments": [{"id": "new"}], "context_segments": [{"id": "old"}],
               "existing_subjects": [], "new_subject_ids": ["person"], "prior_memories": []}
    subject = {"id": "person", "title": "Alex", "entity_type": "person", "participant_ids": []}
    response = {"subjects": [subject, subject], "memories": [
        {"id": "m", "text": "A claim", "segment_ids": ["new"], "subject_ids": ["person"]},
        {"id": "old-only", "text": "Old information", "segment_ids": ["old"], "subject_ids": []}], "changes": []}
    accepted, rejected = retention(payload, response)
    assert accepted == {"subjects": [], "memories": [], "changes": []}
    assert len(rejected) == 4


@pytest.mark.asyncio
async def test_group_retraction_during_inference_prevents_partial_commit(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configured(memory, monkeypatch)
        await capture(memory, "An earlier statement.")
        later = await capture(memory, "A later statement.")
        original = memory_contract.retain

        async def retract(llm, payload):
            result = await original(llm, payload)
            source = memory.artifacts.get_source(later.source_ids[0])
            source.status, source.retracted_at, source.retraction_reason = "retracted", "2034-06-04", "User request"
            memory.artifacts.save_source(source)
            return result

        monkeypatch.setattr(memory_contract, "retain", retract)
        result = await memory.consolidate()
        assert result.report.failures and all(f["category"] == "pipeline" for f in result.report.failures)
        assert not memory.artifacts.list_claims()
