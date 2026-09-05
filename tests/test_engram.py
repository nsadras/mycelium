from types import SimpleNamespace
from datetime import datetime
import sys
import wave

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from engram.config import EngramConfig
from engram.models import MeetingSummary
from engram.pipeline import EngramService, meeting_response
from engram.store import EngramStore
from mycelium.models import LogEntry
from mycelium.operations import IngestionResult
from mycelium.store import LogStore
from server.api import engram as engram_api


def test_engram_config_prefers_cuda_for_auto_device(monkeypatch):
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    monkeypatch.setitem(sys.modules, "torch", torch)

    config = EngramConfig()

    assert config.resolved_whisper_device() == "cuda"
    assert config.resolved_whisper_compute_type("cuda") == "float16"


def test_engram_config_falls_back_to_cpu_for_auto_device(monkeypatch):
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", torch)

    config = EngramConfig()

    assert config.resolved_whisper_device() == "cpu"
    assert config.resolved_whisper_compute_type("cpu") == "int8"


def test_engram_store_persists_meeting_segments_and_summary(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")

    meeting = store.create_meeting("Planning")
    segment = store.add_segment(
        meeting.id,
        start_seconds=0.0,
        end_seconds=2.5,
        text="We should ship the local recorder first.",
        speaker="SPEAKER_00",
        status="diarized",
    )
    store.save_summary(
        meeting.id,
        MeetingSummary(
            summary="The team discussed shipping the local recorder.",
            decisions=["Ship the local recorder first."],
            action_items=[{"owner": "Nitin", "task": "Test uploaded audio", "due": None}],
            open_questions=["Which model runs fastest locally?"],
        ),
    )
    store.save_speaker_names(meeting.id, {"SPEAKER_00": "Alice"})

    loaded = store.get_meeting(meeting.id)
    segments = store.list_segments(meeting.id)

    assert loaded.title == "Planning"
    assert loaded.summary is not None
    assert loaded.summary.decisions == ["Ship the local recorder first."]
    assert loaded.speaker_names == {"SPEAKER_00": "Alice"}
    assert loaded.segment_count == 1
    assert segments == [segment]


def test_engram_store_updates_segment_texts_atomically(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")
    meeting = store.create_meeting("Transcript corrections")
    first = store.add_segment(meeting.id, start_seconds=0, end_seconds=1, text="Original one")
    second = store.add_segment(meeting.id, start_seconds=1, end_seconds=2, text="Original two")
    other_meeting = store.create_meeting("Other meeting")
    other = store.add_segment(other_meeting.id, start_seconds=0, end_seconds=1, text="Untouched")

    updated = store.update_segment_texts(meeting.id, {first.id: "Corrected one", second.id: "Corrected two"})

    assert [segment.text for segment in updated] == ["Corrected one", "Corrected two"]
    with pytest.raises(ValueError):
        store.update_segment_texts(meeting.id, {first.id: "Should not persist", other.id: "Wrong meeting"})
    assert [segment.text for segment in store.list_segments(meeting.id)] == ["Corrected one", "Corrected two"]


def test_engram_store_updates_text_and_speaker_atomically(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")
    meeting = store.create_meeting("Speaker correction")
    first = store.add_segment(meeting.id, start_seconds=0, end_seconds=1, text="One", speaker="SPEAKER_00")
    second = store.add_segment(meeting.id, start_seconds=1, end_seconds=2, text="Two", speaker="SPEAKER_00")
    other_meeting = store.create_meeting("Other meeting")
    other = store.add_segment(other_meeting.id, start_seconds=0, end_seconds=1, text="Other")

    updated = store.update_segment_texts(
        meeting.id,
        {first.id: "Corrected one", second.id: "Corrected two"},
        speaker="SPEAKER_01",
    )

    assert [segment.text for segment in updated] == ["Corrected one", "Corrected two"]
    assert [segment.speaker for segment in updated] == ["SPEAKER_01", "SPEAKER_01"]
    assert all(segment.status == "diarized" for segment in updated)
    with pytest.raises(ValueError):
        store.update_segment_texts(
            meeting.id,
            {first.id: "Should not persist", other.id: "Wrong meeting"},
            speaker="SPEAKER_02",
        )
    assert [segment.speaker for segment in store.list_segments(meeting.id)] == ["SPEAKER_01", "SPEAKER_01"]


@pytest.mark.asyncio
async def test_engram_service_only_updates_transcript_during_review(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")
    service = EngramService(EngramConfig(store_path=tmp_path / "engram"), store, lambda: None)
    meeting = store.create_meeting("Editable transcript")
    segment = store.add_segment(meeting.id, start_seconds=0, end_seconds=1, text="Before")

    with pytest.raises(ValueError, match="awaiting review"):
        await service.update_transcript(meeting.id, {segment.id: "Too early"})

    store.update_meeting(meeting.id, status="reviewing")
    await service.update_transcript(meeting.id, {segment.id: "After correction"})
    assert store.list_segments(meeting.id)[0].text == "After correction"

    store.update_meeting(meeting.id, status="completed")
    with pytest.raises(ValueError, match="awaiting review"):
        await service.update_transcript(meeting.id, {segment.id: "Too late"})


@pytest.mark.asyncio
async def test_engram_service_creates_ready_meeting_from_uploaded_audio(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")
    config = EngramConfig(store_path=tmp_path / "engram", audio_dir=tmp_path / "audio")
    service = EngramService(config, store, lambda: SimpleNamespace(log_store=LogStore(tmp_path / "logs")))

    audio = tmp_path / "phone.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 8000)

    meeting = await service.create_uploaded_meeting(
        title="Phone recording",
        audio_bytes=audio.read_bytes(),
        original_filename="phone.wav",
    )
    response = meeting_response(meeting, [])

    assert meeting.status == "ready"
    assert response["segments"] == []
    assert meeting.audio_path is not None
    assert meeting.audio_path.endswith(".wav")
    assert meeting.duration_seconds == 0.5
    assert store.get_meeting(meeting.id).title == "Phone recording"


@pytest.mark.asyncio
async def test_engram_service_deletes_meeting_segments_and_audio(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")
    config = EngramConfig(store_path=tmp_path / "engram", audio_dir=tmp_path / "audio")
    service = EngramService(config, store, lambda: SimpleNamespace(log_store=LogStore(tmp_path / "logs")))

    audio_path = tmp_path / "audio" / "delete-me.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)

    meeting = store.create_meeting("Delete me")
    store.update_meeting(meeting.id, status="reviewing", audio_path=str(audio_path))
    store.add_segment(
        meeting.id,
        start_seconds=0.0,
        end_seconds=1.0,
        text="This should be deleted.",
        speaker="SPEAKER_00",
        status="diarized",
    )

    await service.delete_meeting(meeting.id)

    with pytest.raises(FileNotFoundError):
        store.get_meeting(meeting.id)
    assert store.list_segments(meeting.id) == []
    assert not audio_path.exists()


@pytest.mark.asyncio
async def test_engram_service_processes_then_finalizes_meeting_with_speaker_names(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")
    log_store = LogStore(tmp_path / "logs")
    config = EngramConfig(store_path=tmp_path / "engram", audio_dir=tmp_path / "audio")
    audio_path = tmp_path / "audio" / "meeting.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)

    class FakeTranscriber:
        def transcribe_audio(self, audio_path):
            return [
                SimpleNamespace(
                    start_seconds=0.0,
                    end_seconds=3.0,
                    text="Use local-only models for Engram.",
                )
            ]

    captured_transcripts = []

    class FakeSummarizer:
        async def summarize(self, title, transcript):
            captured_transcripts.append(transcript)
            return MeetingSummary(
                summary=f"{title}: {transcript[:30]}",
                decisions=["Use local-only models."],
            )

    class FakeDiarizer:
        def diarize(self, audio_path, fallback_segments):
            for segment in fallback_segments:
                segment.speaker = "SPEAKER_00"
                segment.status = "diarized"
            return fallback_segments

    class FakeMemory:
        def __init__(self):
            self.log_store = log_store

        async def ingest_source(self, source_input):
            entry = LogEntry(
                entry_id="2026-08-28#meeting-test",
                session_id=source_input.session_id,
                timestamp=datetime.now(),
                content=source_input.transcript,
            )
            log_store.append(entry)
            return IngestionResult(status="captured", log_entries=(entry,))

    service = EngramService(
        config,
        store,
        lambda: FakeMemory(),
        transcriber_factory=lambda: FakeTranscriber(),
        diarizer_factory=lambda: FakeDiarizer(),
        summarizer_factory=lambda: FakeSummarizer(),
    )

    meeting = store.create_meeting("Architecture review")
    store.update_meeting(meeting.id, status="ready", audio_path=str(audio_path))
    processed = await service.process_meeting(meeting.id)
    processed_segments = store.list_segments(meeting.id)
    event_payload = meeting_response(processed, processed_segments)

    assert processed.status == "reviewing"
    assert event_payload["segments"][0]["text"] == "Use local-only models for Engram."
    assert event_payload["segments"][0]["speaker"] == "SPEAKER_00"
    assert not processed.memory_log_entry_id
    assert store.get_meeting(meeting.id).summary is None
    assert len(log_store.get_unconsolidated(days=None)) == 0

    await service.update_speaker_names(meeting.id, {"SPEAKER_00": "Alice"})
    finalized = await service.finalize_meeting(meeting.id)

    assert finalized.status == "completed"
    assert finalized.memory_log_entry_id
    assert store.get_meeting(meeting.id).summary.decisions == ["Use local-only models."]
    assert "Alice: Use local-only models for Engram." in captured_transcripts[0]
    assert len(log_store.get_unconsolidated(days=None)) == 1


def test_engram_service_recovers_interrupted_processing(tmp_path):
    store = EngramStore(tmp_path / "engram.sqlite")
    config = EngramConfig(store_path=tmp_path / "engram", audio_dir=tmp_path / "audio")
    service = EngramService(config, store, lambda: SimpleNamespace(log_store=LogStore(tmp_path / "logs")))
    transcribing = store.create_meeting("Interrupted transcription")
    processing = store.create_meeting("Interrupted diarization")
    completed = store.create_meeting("Already completed")
    store.update_meeting(transcribing.id, status="transcribing")
    store.update_meeting(processing.id, status="processing")
    store.update_meeting(completed.id, status="completed")

    recovered = service.recover_interrupted_meetings()

    assert {meeting.id for meeting in recovered} == {transcribing.id, processing.id}
    assert store.get_meeting(transcribing.id).status == "failed"
    assert "server restart" in store.get_meeting(processing.id).error
    assert store.get_meeting(completed.id).status == "completed"


def test_process_meeting_api_returns_accepted_and_starts_background_task(tmp_path, monkeypatch):
    store = EngramStore(tmp_path / "engram.sqlite")
    meeting = store.create_meeting("Async processing")
    started = []
    service = SimpleNamespace(store=store, start_processing=started.append)
    monkeypatch.setattr(engram_api, "get_engram", lambda: service)
    app = FastAPI()
    app.include_router(engram_api.router, prefix="/api/engram")

    with TestClient(app) as client:
        response = client.post(f"/api/engram/meetings/{meeting.id}/process")

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    assert started == [meeting.id]


def test_update_meeting_transcript_api_persists_review_edits_and_locks_completed_meetings(tmp_path, monkeypatch):
    store = EngramStore(tmp_path / "engram.sqlite")
    service = EngramService(EngramConfig(store_path=tmp_path / "engram"), store, lambda: None)
    meeting = store.create_meeting("API transcript correction")
    segment = store.add_segment(meeting.id, start_seconds=0, end_seconds=2, text="Incorrect wording")
    store.update_meeting(meeting.id, status="reviewing")
    monkeypatch.setattr(engram_api, "get_engram", lambda: service)
    app = FastAPI()
    app.include_router(engram_api.router, prefix="/api/engram")

    with TestClient(app) as client:
        response = client.put(
            f"/api/engram/meetings/{meeting.id}/transcript",
            json={
                "segments": [{"id": segment.id, "text": "Correct wording"}],
                "speaker": "SPEAKER_01",
            },
        )
        store.update_meeting(meeting.id, status="completed")
        locked_response = client.put(
            f"/api/engram/meetings/{meeting.id}/transcript",
            json={"segments": [{"id": segment.id, "text": "Too late"}]},
        )

    assert response.status_code == 200
    assert response.json()["segments"][0]["text"] == "Correct wording"
    assert response.json()["segments"][0]["speaker"] == "SPEAKER_01"
    assert locked_response.status_code == 409
    assert store.list_segments(meeting.id)[0].text == "Correct wording"


def test_meeting_audio_api_supports_range_requests(tmp_path, monkeypatch):
    config = EngramConfig(store_path=tmp_path / "engram", audio_dir=tmp_path / "audio")
    store = EngramStore(config.db_path)
    service = EngramService(config, store, lambda: None)
    audio_path = config.audio_dir / "meeting.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 160)
    meeting = store.create_meeting("Playback")
    store.update_meeting(meeting.id, audio_path=str(audio_path))
    monkeypatch.setattr(engram_api, "get_engram", lambda: service)
    app = FastAPI()
    app.include_router(engram_api.router, prefix="/api/engram")

    with TestClient(app) as client:
        full_response = client.get(f"/api/engram/meetings/{meeting.id}/audio")
        response = client.get(
            f"/api/engram/meetings/{meeting.id}/audio",
            headers={"Range": "bytes=0-3"},
        )

    assert full_response.status_code == 200
    assert full_response.headers["accept-ranges"] == "bytes"
    assert full_response.headers["content-type"] == "audio/wav"
    assert response.status_code == 206
    assert response.content == b"RIFF"
    assert response.headers["content-range"].startswith("bytes 0-3/")
    assert response.headers["content-type"] == "audio/wav"


def test_meeting_audio_api_rejects_files_outside_audio_directory(tmp_path, monkeypatch):
    config = EngramConfig(store_path=tmp_path / "engram", audio_dir=tmp_path / "audio")
    store = EngramStore(config.db_path)
    service = EngramService(config, store, lambda: None)
    outside_audio = tmp_path / "outside.wav"
    outside_audio.write_bytes(b"not available through the API")
    meeting = store.create_meeting("Invalid audio path")
    store.update_meeting(meeting.id, audio_path=str(outside_audio))
    monkeypatch.setattr(engram_api, "get_engram", lambda: service)
    app = FastAPI()
    app.include_router(engram_api.router, prefix="/api/engram")

    with TestClient(app) as client:
        response = client.get(f"/api/engram/meetings/{meeting.id}/audio")

    assert response.status_code == 404


def test_meeting_audio_api_returns_not_found_without_recording(tmp_path, monkeypatch):
    config = EngramConfig(store_path=tmp_path / "engram", audio_dir=tmp_path / "audio")
    store = EngramStore(config.db_path)
    service = EngramService(config, store, lambda: None)
    meeting = store.create_meeting("No recording")
    monkeypatch.setattr(engram_api, "get_engram", lambda: service)
    app = FastAPI()
    app.include_router(engram_api.router, prefix="/api/engram")

    with TestClient(app) as client:
        no_recording = client.get(f"/api/engram/meetings/{meeting.id}/audio")
        missing_meeting = client.get("/api/engram/meetings/missing/audio")

    assert no_recording.status_code == 404
    assert missing_meeting.status_code == 404
