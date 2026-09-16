import asyncio
import io
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from engram.config import EngramConfig
from engram.models import MeetingSummary
from engram.pipeline import EngramService, meeting_response
from engram.store import EngramStore
from mycelium.models import LogEntry
from mycelium.operations import IngestionResult
from mycelium.store import LogStore


def setup(tmp_path):
    config = EngramConfig(store_path=tmp_path, audio_dir=tmp_path / "audio")
    config.ensure_dirs()
    store = EngramStore(tmp_path / "engram.sqlite")
    return config, store


def recording(config, store, title="Review", *, reviewing=False):
    meeting = store.create_meeting(title)
    path = config.audio_dir / f"{meeting.id}.wav"
    path.write_bytes(b"audio")
    store.update_meeting(
        meeting.id, audio_path=str(path), status="reviewing" if reviewing else "ready"
    )
    if reviewing:
        store.add_segment(
            meeting.id, start_seconds=0, end_seconds=1, text="Reviewed words"
        )
    return store.get_meeting(meeting.id)


async def entered(event):
    assert await asyncio.to_thread(event.wait, 5), "Native worker did not start"


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["transcribe", "diarize", "retry"])
async def test_delete_waits_for_native_worker_and_leaves_no_late_writes(
    tmp_path, phase
):
    config, store = setup(tmp_path)
    meeting = recording(config, store, reviewing=phase == "retry")
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def wait_for_release(path):
        started.set()
        assert release.wait(5)
        assert Path(path).exists(), (
            "Audio disappeared while the native model was reading it"
        )
        finished.set()

    def transcribe(path):
        if phase == "transcribe":
            wait_for_release(path)
        return [SimpleNamespace(start_seconds=0, end_seconds=1, text="Original words")]

    def diarize(path, segments):
        assert phase != "transcribe", "Cancellation should stop the next stage"
        wait_for_release(path)
        return segments

    service = EngramService(
        config,
        store,
        lambda: None,
        transcriber_factory=lambda: SimpleNamespace(transcribe_audio=transcribe),
        diarizer_factory=lambda: SimpleNamespace(diarize=diarize),
    )
    job = (
        asyncio.create_task(service.retry_diarization(meeting.id))
        if phase == "retry"
        else service.start_processing(meeting.id)
    )
    try:
        await entered(started)
        deletion = asyncio.create_task(service.delete_meeting(meeting.id))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not deletion.done()
        assert store.get_meeting(meeting.id)
        release.set()
        await asyncio.wait_for(deletion, 5)
        assert finished.is_set() and job.cancelled()
        with pytest.raises(FileNotFoundError):
            store.get_meeting(meeting.id)
        assert store.list_segments(meeting.id) == []
        assert not Path(meeting.audio_path).exists()
        with pytest.raises(FileNotFoundError):
            store.add_segment(
                meeting.id, start_seconds=0, end_seconds=1, text="Late write"
            )
    finally:
        release.set()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_keeps_device_lock_until_worker_exits_and_deletes_queued_job(
    tmp_path,
):
    config, store = setup(tmp_path)
    first, queued, next_meeting = [recording(config, store, str(i)) for i in range(3)]
    started, release = threading.Event(), threading.Event()
    calls = []

    def transcribe(path):
        calls.append(path)
        if path == first.audio_path:
            started.set()
            assert release.wait(5)
        return [SimpleNamespace(start_seconds=0, end_seconds=1, text="Words")]

    service = EngramService(
        config,
        store,
        lambda: None,
        transcriber_factory=lambda: SimpleNamespace(transcribe_audio=transcribe),
        diarizer_factory=lambda: SimpleNamespace(
            diarize=lambda path, segments: segments
        ),
    )
    jobs = [service.start_processing(first.id)]
    try:
        await entered(started)
        jobs.extend(
            [
                service.start_processing(queued.id),
                service.start_processing(next_meeting.id),
            ]
        )
        await asyncio.sleep(0)
        await asyncio.wait_for(service.delete_meeting(queued.id), 1)
        assert jobs[1].cancelled()
        jobs[0].cancel()
        await asyncio.sleep(0)
        jobs[0].cancel()  # Repeated cancellation must not release the device early.
        await asyncio.sleep(0)
        assert calls == [first.audio_path]
        assert not jobs[0].done()
        release.set()
        results = await asyncio.wait_for(
            asyncio.gather(*jobs, return_exceptions=True), 5
        )
        assert isinstance(results[0], asyncio.CancelledError)
        assert results[2].status == "reviewing"
        assert calls == [first.audio_path, next_meeting.audio_path]
    finally:
        release.set()
        await asyncio.gather(*jobs, return_exceptions=True)


@pytest.mark.asyncio
async def test_delete_during_upload_waits_for_copy_and_cleans_partial_files(tmp_path):
    config, store = setup(tmp_path)
    started, release = threading.Event(), threading.Event()

    class Stream(io.BytesIO):
        def read(self, size):
            started.set()
            assert release.wait(5)
            return super().read(size)

    service = EngramService(config, store, lambda: None)
    job = asyncio.create_task(
        service.create_uploaded_meeting(
            title="Uploading",
            audio_stream=Stream(b"partial audio"),
            original_filename="test.wav",
        )
    )
    try:
        await entered(started)
        meeting = store.list_meetings()[0]
        deletion = asyncio.create_task(service.delete_meeting(meeting.id))
        await asyncio.sleep(0)
        assert not deletion.done()
        release.set()
        await asyncio.wait_for(deletion, 5)
        assert job.cancelled()
        assert store.list_meetings() == []
        assert list(config.audio_dir.iterdir()) == []
    finally:
        release.set()
        await asyncio.gather(job, return_exceptions=True)


class PausedMemory:
    def __init__(self, root):
        self.log_store = LogStore(root / "logs")
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.inputs = []

    async def ingest_source(self, source_input):
        self.inputs.append(source_input)
        self.started.set()
        await self.release.wait()
        entry = LogEntry(
            "2026-01-01#meeting",
            source_input.session_id,
            datetime.now(),
            source_input.transcript,
        )
        self.log_store.append(entry)
        return IngestionResult(status="captured", log_entries=(entry,))


@pytest.mark.asyncio
async def test_admission_freezes_inputs_and_serializes_finalization_across_restart(
    tmp_path,
):
    config, store = setup(tmp_path)
    meeting = recording(config, store, reviewing=True)
    memory = PausedMemory(tmp_path / "memory")
    summary = AsyncMock(return_value=MeetingSummary("A summary"))
    service = EngramService(
        config,
        store,
        lambda: memory,
        summarizer_factory=lambda: SimpleNamespace(summarize=summary),
    )
    job = asyncio.create_task(service.finalize_meeting(meeting.id))
    try:
        await asyncio.wait_for(memory.started.wait(), 5)
        assert store.get_meeting(meeting.id).status == "finalizing"
        assert store.get_meeting(meeting.id).admission_started_at is not None
        with pytest.raises(ValueError, match="already in progress"):
            await service.finalize_meeting(meeting.id)
        with pytest.raises(ValueError, match="already in progress"):
            await service.update_speaker_names(meeting.id, {"speaker": "Other"})
        # Losing in-memory task state must not unfreeze an admitted input.
        reopened = EngramStore(store.db_path)
        with pytest.raises(ValueError, match="admission"):
            reopened.update_segment_texts(
                meeting.id, {store.list_segments(meeting.id)[0].id: "Changed"}
            )
        with pytest.raises(ValueError, match="admission"):
            reopened.save_speaker_names(meeting.id, {"speaker": "Other"})
        with pytest.raises(ValueError, match="admission"):
            reopened.update_meeting(meeting.id, started_at=datetime(2030, 1, 1))
        memory.release.set()
        result = await asyncio.wait_for(job, 5)
        assert result.status == "completed" and result.summary is not None
        assert len(memory.inputs) == 1
        assert (await service.finalize_meeting(meeting.id)).summary == result.summary
        summary.assert_awaited_once()
    finally:
        memory.release.set()
        await asyncio.gather(job, return_exceptions=True)


@pytest.mark.asyncio
async def test_deletion_during_admission_finishes_bookkeeping_without_starting_summary(
    tmp_path,
):
    config, store = setup(tmp_path)
    meeting = recording(config, store, reviewing=True)
    memory = PausedMemory(tmp_path / "memory")
    summary = AsyncMock()
    service = EngramService(
        config,
        store,
        lambda: memory,
        summarizer_factory=lambda: SimpleNamespace(summarize=summary),
    )
    job = asyncio.create_task(service.finalize_meeting(meeting.id))
    try:
        await asyncio.wait_for(memory.started.wait(), 5)
        deletion = asyncio.create_task(service.delete_meeting(meeting.id))
        await asyncio.sleep(0)
        assert not deletion.done()
        memory.release.set()
        await asyncio.wait_for(deletion, 5)
        assert job.cancelled()
        summary.assert_not_awaited()
        assert len(memory.log_store.get_unconsolidated(days=None)) == 1
        with pytest.raises(FileNotFoundError):
            store.get_meeting(meeting.id)
    finally:
        memory.release.set()
        await asyncio.gather(job, return_exceptions=True)


def test_warning_history_is_typed_durable_and_cascades_on_delete(tmp_path):
    _, store = setup(tmp_path)
    meeting = store.create_meeting("History")
    store.add_warning(meeting.id, "diarization", "Device unavailable")
    store.add_warning(meeting.id, "summary", "Model unavailable")
    store.resolve_warnings(meeting.id, "summary")
    reopened = EngramStore(store.db_path)
    result = reopened.get_meeting(meeting.id)
    warnings = {warning.stage: warning for warning in result.warnings}
    assert warnings["summary"].resolved_at is not None
    assert warnings["diarization"].resolved_at is None
    payload = meeting_response(result, [])
    assert all(isinstance(w["created_at"], str) for w in payload["warnings"])
    assert reopened.list_meetings()[0].warnings == result.warnings
    with pytest.raises(ValueError, match="declared stage"):
        store.add_warning(meeting.id, "unknown", "Invalid")
    store.delete_meeting(meeting.id)
    with store._connect() as conn:
        assert conn.execute("SELECT count(*) FROM meeting_warnings").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_audio_delete_failure_keeps_retryable_meeting_record(
    tmp_path, monkeypatch
):
    config, store = setup(tmp_path)
    meeting = recording(config, store)
    service = EngramService(config, store, lambda: None)

    def denied(self, **kwargs):
        raise PermissionError("Read-only audio")

    monkeypatch.setattr(Path, "unlink", denied)
    with pytest.raises(PermissionError, match="Read-only"):
        await service.delete_meeting(meeting.id)
    assert store.get_meeting(meeting.id).id == meeting.id


def test_restart_preserves_completed_transcription_and_frozen_admission(tmp_path):
    config, store = setup(tmp_path)
    diarizing = recording(config, store, reviewing=True)
    admission = recording(config, store, reviewing=True)
    summary = recording(config, store, reviewing=True)
    original_segments = store.list_segments(diarizing.id)
    store.update_meeting(diarizing.id, status="processing")
    for item in (admission, summary):
        store.freeze_for_admission(item.id)
        store.update_meeting(item.id, status="finalizing")
    store.update_meeting(summary.id, memory_log_entry_id="saved")
    service = EngramService(config, store, lambda: None)
    service.recover_interrupted_meetings()
    assert store.get_meeting(diarizing.id).status == "reviewing"
    assert store.get_meeting(diarizing.id).warnings[0].stage == "diarization"
    assert store.list_segments(diarizing.id) == original_segments
    assert store.get_meeting(admission.id).status == "reviewing"
    assert store.get_meeting(admission.id).admission_started_at is not None
    assert store.get_meeting(summary.id).status == "completed"
    assert store.get_meeting(summary.id).warnings[0].stage == "summary"
    # A crash between persisting the summary and updating the status needs no inference.
    store.save_summary(summary.id, MeetingSummary("Already generated"))
    store.update_meeting(summary.id, status="finalizing")
    service.recover_interrupted_meetings()
    recovered = store.get_meeting(summary.id)
    assert recovered.status == "completed"
    assert recovered.summary.summary == "Already generated"
    assert len(recovered.warnings) == 1 and recovered.warnings[0].resolved_at is not None
