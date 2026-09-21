"""Evidence and identity context survives request compaction and resumed builds."""

from copy import deepcopy
import json
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium import Mycelium, memory_contract as contract
from mycelium.artifacts import ExtractionBatchState, SourceSegment
from mycelium.budget import count_tokens
from mycelium.memory_inputs import compact_retention
from mycelium.operations import SourceInput
from mycelium.telemetry import trace_metadata


@pytest.mark.asyncio
async def test_retention_round_trip_keeps_literal_text_and_exact_citations():
    source_id, segment_id = "source-0123456789abcdef", "source-0123456789abcdef#seg-0001"
    person, prior = "subject-0123456789abcdefabcd", "claim-0123456789abcdefabcd"
    participant = "participant-source-scoped-0123456789"
    literal = f"The label is {person}; keep r0 unchanged."
    payload = {
        "occurred_at": "2032-06-01", "segments": [{"id": segment_id, "text": literal,
            "speaker": "Ari", "role": "user", "participant_id": participant, "source_id": source_id, "source_time": "2032-06-01",
            "metadata": {"engram_segment_id": "audio-12", "id": person, "note": literal}}],
        "context_segments": [{"id": "old#seg-1", "text": "Earlier context", "speaker": "Ari",
                              "source_id": "old", "source_time": "2031-01-01", "role": None}],
        "existing_subjects": [{"id": person, "title": person, "entity_type": "person", "aliases": [person]}],
        "participants": [{"id": participant, "name": "Ari", "role": "user", "subject_id": person, "binding_origin": "user"}],
        "new_subject_ids": ["subject-new-0123456789abcdef"],
        "prior_memories": [{"id": prior, "text": literal, "subject_ids": [person]}],
    }
    before = deepcopy(payload)

    async def respond(system, user, schema, **kwargs):
        data = json.loads(user)
        segment = data["segments"][0]
        assert trace_metadata()["request_ids"][segment["id"]] == segment_id
        assert segment["text"] == literal and segment["role"] == "user"
        assert "source_time" not in segment
        assert data["context_segments"][0]["source_time"] == "2031-01-01"
        assert segment["metadata"] == {"id": person, "note": literal}
        subject = data["existing_subjects"][0]
        pid = data["participants"][0]["id"]
        assert pid == segment["participant_id"] and pid != participant
        assert data["participants"][0]["subject_id"] == subject["id"]
        assert subject["id"] != person and subject["title"] == person and subject["aliases"] == [person]
        result = {"subjects": [{**{k: subject[k] for k in ("id", "title", "entity_type")}, "participant_ids": [pid]}],
                  "memories": [{"id": "m1", "text": literal, "subject_ids": [subject["id"]],
                                "segment_ids": [segment["id"], data["context_segments"][0]["id"]]}],
                  "changes": [{"earlier_id": data["prior_memories"][0]["id"], "later_id": "m1",
                               "relation": "supersedes", "reason": literal}]}
        return result if isinstance(schema, dict) else schema.model_validate(result).model_dump()

    llm = AsyncMock()
    llm.call_structured.side_effect = respond
    result = await contract.retain(llm, payload)
    assert result["subjects"][0]["participant_ids"] == [participant]
    assert result["memories"] == [{"id": "m1", "text": literal, "subject_ids": [person],
                                   "segment_ids": [segment_id, "old#seg-1"]}]
    assert result["changes"][0] == {"earlier_id": prior, "later_id": "m1", "relation": "supersedes", "reason": literal}
    assert payload == before
    assert "request_ids" not in trace_metadata()
    llm.call_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_presentation_round_trip_preserves_shared_items_and_no_page_review():
    payload = {"subjects": [{"id": "subject-a", "title": "A"}, {"id": "subject-b", "title": "B"}],
        "affected_subject_ids": ["subject-a", "subject-b"],
        "memories": [{"id": "claim-one", "subject_ids": ["subject-a", "subject-b"]}],
        "existing_items": [{"id": "view-old", "owner_id": "subject-a", "memory_ids": ["claim-one"],
                            "linked_subject_ids": ["subject-b"], "protected": True}],
        "pending_changes": [{"proposal_id": "proposal-one", "incoming_claim_ids": ["claim-one"],
                             "target_claim_ids": ["claim-old"], "affected_entity_ids": ["subject-a"]}],
        "page_exclusions": []}

    async def respond(system, user, schema, **kwargs):
        data = json.loads(user)
        a, b = data["affected_subject_ids"]
        cid = data["memories"][0]["id"]
        assert data["existing_items"][0]["linked_subject_ids"] == [b]
        assert data["existing_items"][0]["protected"]
        assert data["pending_changes"][0]["incoming_claim_ids"] == [cid]
        assert data["pending_changes"][0]["affected_entity_ids"] == [a]
        item = {"owner_id": a, "heading": "Work", "text": "The literal label is claim-one.",
                "memory_ids": [cid], "linked_subject_ids": [b], "state": "current"}
        return schema.model_validate({"items": [item]}).model_dump()

    llm = AsyncMock()
    llm.call_structured.side_effect = respond
    result = await contract.present(llm, payload)
    assert result["items"][0]["owner_id"] == "subject-a"
    assert result["items"][0]["linked_subject_ids"] == ["subject-b"]
    assert result["items"][0]["memory_ids"] == ["claim-one"]
    assert result["items"][0]["text"] == "The literal label is claim-one."
    payload["page_exclusions"] = [{"memory_id": "claim-one", "subject_id": "subject-b"}]
    with pytest.raises(ValidationError, match="no-page"):
        await contract.present(llm, payload)


def test_compact_input_reduces_envelope_cost_without_changing_source_text():
    payload = {"occurred_at": "2032-01-01", "segments": [
        {"id": f"source-0123456789abcdef#seg-{i:04}", "text": "A complete spoken sentence.",
         "speaker": "Ari", "role": None, "source_id": "source-0123456789abcdef",
         "source_time": "2032-01-01", "metadata": {"engram_segment_id": f"audio-{i:04}"}}
        for i in range(100)], "existing_subjects": [], "new_subject_ids": [
            f"subject-{i:020}" for i in range(32)], "prior_memories": []}
    data, ids = compact_retention(payload)
    assert [row["text"] for row in data["segments"]] == [row["text"] for row in payload["segments"]]
    assert [ids.reverse[row["id"]] for row in data["segments"]] == [row["id"] for row in payload["segments"]]
    def size(value):
        return count_tokens(json.dumps(value)) + count_tokens(json.dumps(contract.retention_model(value).model_json_schema()))
    assert size(data) < size(payload) / 2


@pytest.mark.asyncio
async def test_resumed_batches_keep_prior_identity_and_adjacent_context(tmp_path, monkeypatch):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        search = AsyncMock(return_value=[])
        monkeypatch.setattr(memory.retriever.claim_index, "search", search)
        lines = ["Sana created the orchard map.", "She plans to add irrigation pipes next month.",
                 "She will ask the gardeners to check the draft."]
        capture = await memory.ingest_source(SourceInput("\n".join(lines), "orchard",
            occurred_at="2032-06-08", source_type="meeting_transcript", participants=("Kai",),
            segments=tuple(SourceSegment(str(i), i, text, speaker="Kai") for i, text in enumerate(lines))))
        source = memory.artifacts.get_source(capture.source_ids[0])
        retainer = memory.consolidator.retainer
        payload = await retainer.input(source, source.segments[:1], "first", prior_ids=[])
        person = payload["new_subject_ids"][0]
        retained = {"subjects": [{"id": person, "title": "Sana", "entity_type": "person", "participant_ids": []}],
                    "memories": [{"id": "m1", "text": lines[0], "subject_ids": [person],
                                  "segment_ids": [source.segments[0].segment_id]}], "changes": []}
        with memory.db.transaction():
            first_ids = retainer.persist(source, "first", payload, retained)
            entity = memory.artifacts.get_entity(person)
            entity.aliases = ["Sana Patel"]
            memory.artifacts.save_entity(entity)
            episode = memory.artifacts.get_episode(capture.episode_ids[0])
            episode.claim_ids = first_ids
            episode.extraction_status = "partial"
            episode.extraction_batches = [ExtractionBatchState(f"batch-{i}", i, [s.segment_id],
                status="complete" if i == 0 else "pending") for i, s in enumerate(source.segments)]
            memory.artifacts.save_episode(episode)
        seen = []

        async def respond(system, user, schema, **kwargs):
            data = json.loads(user)
            stage = kwargs["debug_label"]
            seen.append(stage)
            if stage == "memory-retention":
                position = len(seen)
                assert [r["text"] for r in data["segments"]] == lines[position:]
                assert [r["text"] for r in data["context_segments"]] == lines[:position]
                assert all(r["speaker"] == "Kai" for r in data["context_segments"])
                assert data["prior_memories"]
                sana = next(s for s in data["existing_subjects"] if s["title"] == "Sana")
                assert sana["aliases"] == ["Sana Patel"]
                prior = next(m for m in data["prior_memories"] if m["text"] == lines[0])
                assert prior["provenance"] == [{"speaker": "Kai", "role": None,
                    "source_type": "meeting_transcript", "source_time": source.occurred_at}]
                output = {"subjects": [{k: sana[k] for k in ("id", "title", "entity_type")} | {"participant_ids": []}],
                    "memories": [{"id": "new", "text": lines[position], "subject_ids": [sana["id"]],
                                  "segment_ids": [data["segments"][0]["id"], data["context_segments"][0]["id"]]}], "changes": []}
            else:
                assert data["subjects"][0]["aliases"] == ["Sana Patel"]
                assert all(m["provenance"][0]["speaker"] == "Kai" for m in data["memories"])
                output = {"items": [{"owner_id": data["affected_subject_ids"][0], "heading": "Map",
                    "text": "Sana is developing the orchard map.", "memory_ids": [m["id"] for m in data["memories"]],
                    "linked_subject_ids": [], "state": "current"}]}
            return output if isinstance(schema, dict) else schema.model_validate(output).model_dump()

        memory.llm.call_structured = AsyncMock(side_effect=respond)
        result = await memory.consolidate()
        assert not result.report.failures
        assert seen == ["memory-retention", "memory-presentation"]
        assert len(memory.artifacts.list_claims()) == 2
        assert memory.artifacts.get_episode(episode.episode_id).extraction_status == "complete"
        assert all(memory.artifacts.entities_for_claims({c.claim_id}) == {person} for c in memory.artifacts.list_claims())
        assert all(p.source_id == source.source_id and p.speaker == "Kai"
                   for c in memory.artifacts.list_claims() for p in c.provenance)
        assert all(sid.startswith(source.source_id + "#")
                   for c in memory.artifacts.list_claims() for p in c.provenance for sid in p.segment_ids)
        assert any("Kai:" in call.args[0] for call in search.call_args_list)
        assert any(call.args[0] == "Kai" for call in search.call_args_list)
        await memory.consolidate()
        assert memory.llm.call_structured.await_count == 2
