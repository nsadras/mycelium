import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium, SourceInput, ConsolidationRequest
from mycelium.models import DreamReport


@pytest.mark.asyncio
async def test_build_snapshot_leaves_concurrent_capture_pending_and_replays_safely(
    tmp_path,
):
    memory = Mycelium(tmp_path / "store")
    memory.encoder.llm = AsyncMock()
    first = await memory.ingest_source(
        SourceInput("USER: First input.", "one", idempotency_key="one")
    )
    assert first.status == "captured"
    assert memory.artifacts.list_claims() == []
    memory.encoder.llm.call_structured.assert_not_awaited()
    entered, release = asyncio.Event(), asyncio.Event()

    async def extract(source, episode):
        entered.set()
        await release.wait()
        episode.extraction_status = "complete"
        memory.artifacts.save_episode(episode)

    memory.encoder._extract_claims = AsyncMock(side_effect=extract)
    organizer = SimpleNamespace(run=AsyncMock(return_value=DreamReport(0, 0, 0)))
    memory.pipeline.consolidator = organizer
    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        build = tasks.create_task(memory.consolidate(ConsolidationRequest()))
        await entered.wait()
        second = await memory.ingest_source(
            SourceInput("USER: Later input.", "two", idempotency_key="two")
        )
        release.set()
        await build
    assert organizer.run.await_args.kwargs["source_ids"] == set(first.source_ids)
    assert (
        memory.artifacts.get_episode(second.episode_ids[0]).extraction_status
        == "pending"
    )
    assert memory.consolidation_status().pending_sources == 1
    await memory.consolidate(ConsolidationRequest())
    assert memory.encoder._extract_claims.await_count == 2
    await memory.consolidate(ConsolidationRequest())
    assert memory.encoder._extract_claims.await_count == 2
    assert memory.consolidation_status().pending_sources == 0


@pytest.mark.asyncio
async def test_capture_and_restart_do_not_call_extractor(tmp_path):
    path = tmp_path / "store"
    source = SourceInput("USER: A durable input.", "one", idempotency_key="one")
    first = Mycelium(path)
    first.encoder.llm = AsyncMock()
    initial = await first.ingest_source(source)
    restart = Mycelium(path)
    restart.encoder.llm = AsyncMock()
    repeated = await restart.ingest_source(source)
    assert repeated.source_ids == initial.source_ids
    assert len(restart.artifacts.list_sources()) == 1
    assert restart.artifacts.list_claims() == []
    restart.encoder.llm.call_structured.assert_not_awaited()


def test_only_build_routes_exist():
    from server.api.memory_lifecycle import router

    paths = {route.path for route in router.routes}
    assert "/build" in paths
    assert "/build/status" in paths
    assert not any("flush" in path or "run-if-ready" in path for path in paths)


@pytest.mark.asyncio
async def test_cross_turn_context_citations_keep_original_source_identity(tmp_path):
    memory = Mycelium(tmp_path / "store")
    previous = await memory.ingest_source(
        SourceInput("ASSISTANT: Would you lead the workshop?", "chat")
    )
    current = await memory.ingest_source(
        SourceInput(
            "USER: Yes, I will.",
            "chat",
            metadata={"context_source_ids": list(previous.source_ids)},
        )
    )
    prior_segment = (
        memory.artifacts.get_source(previous.source_ids[0]).segments[0].segment_id
    )
    new_segment = (
        memory.artifacts.get_source(current.source_ids[0]).segments[0].segment_id
    )

    async def response(_system, _user, output_type, **kwargs):
        if "segment_dispositions" in output_type.model_fields:
            return {
                "segment_dispositions": [
                    {
                        "segment_id": new_segment,
                        "disposition": "claim_bearing",
                        "reason": "Explicit commitment.",
                    }
                ]
            }
        return {
            "claims": [
                {
                    "text": "The user will lead the workshop.",
                    "about": [{"entity": "user"}],
                    "segment_ids": [new_segment],
                    "context_segment_ids": [prior_segment],
                }
            ]
        }

    memory.encoder.llm = SimpleNamespace(
        call_structured=AsyncMock(side_effect=response)
    )
    await memory.encoder.extract_pending(set(current.source_ids))
    claim = memory.artifacts.list_claims()[0]
    assert {(p.source_id, tuple(p.segment_ids)) for p in claim.provenance} == {
        (current.source_ids[0], (new_segment,)),
        (previous.source_ids[0], (prior_segment,)),
    }
    assert (
        memory.artifacts.get_episode(previous.episode_ids[0]).extraction_status
        == "pending"
    )


@pytest.mark.asyncio
async def test_meeting_admission_survives_summary_failure_and_freezes_review(tmp_path):
    from engram import EngramConfig, EngramService, EngramStore
    from engram.models import MeetingSummary, TranscriptSegment

    config = EngramConfig(
        store_path=tmp_path / "meetings", audio_dir=tmp_path / "audio"
    )
    config.ensure_dirs()
    store = EngramStore(config.db_path)
    meeting = store.create_meeting("Notes")
    store.replace_segments(
        meeting.id,
        [
            TranscriptSegment(
                id=None,
                meeting_id=meeting.id,
                segment_index=0,
                start_seconds=0,
                end_seconds=3,
                text="The review is on Thursday.",
                speaker="Nora",
            )
        ],
    )
    store.update_meeting(meeting.id, status="reviewing")
    memory = Mycelium(tmp_path / "memory")
    memory.encoder.llm = AsyncMock()
    summarizer = SimpleNamespace(
        summarize=AsyncMock(side_effect=RuntimeError("offline"))
    )
    service = EngramService(
        config, store, lambda: memory, summarizer_factory=lambda: summarizer
    )

    result = await service.finalize_meeting(meeting.id)

    assert result.status == "completed"
    assert "summary failed" in result.error
    assert len(memory.artifacts.list_sources()) == 1
    assert memory.artifacts.list_claims() == []
    memory.encoder.llm.call_structured.assert_not_awaited()
    with pytest.raises(ValueError, match="after source admission"):
        await service.update_speaker_names(meeting.id, {"Nora": "Someone else"})
    with pytest.raises(ValueError, match="awaiting review"):
        await service.update_transcript(meeting.id, {})
    summarizer.summarize.side_effect = None
    summarizer.summarize.return_value = MeetingSummary("Review on Thursday.")
    retried = await service.finalize_meeting(meeting.id)
    assert retried.summary is not None
    assert retried.error is None
    assert len(memory.artifacts.list_sources()) == 1
