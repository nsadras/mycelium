from __future__ import annotations

import asyncio
import shutil
import wave
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from engram.config import EngramConfig
from engram.diarize import WhisperXDiarizer
from engram.memory_adapter import ingest_meeting_into_memory, meeting_transcript_text
from engram.models import Meeting, TranscriptSegment, iso_or_none
from engram.store import EngramStore
from engram.summarize import EngramSummarizer
from engram.transcribe import FasterWhisperTranscriber

MemoryGetter = Callable[[], Any]


class EngramService:
    def __init__(
        self,
        config: EngramConfig,
        store: EngramStore,
        get_mem: MemoryGetter,
        *,
        transcriber_factory: Callable[[], Any] | None = None,
        diarizer_factory: Callable[[], Any] | None = None,
        summarizer_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.get_mem = get_mem
        self.transcriber_factory = transcriber_factory or (lambda: FasterWhisperTranscriber(self.config))
        self.diarizer_factory = diarizer_factory or (lambda: WhisperXDiarizer(self.config))
        self.summarizer_factory = summarizer_factory or (
            lambda: EngramSummarizer(
                ollama_url=self.config.ollama_url,
                model=self.config.ollama_model,
                temperature=self.config.summary_temperature,
            )
        )
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    async def process_meeting(self, meeting_id: str) -> Meeting:
        meeting = self.store.get_meeting(meeting_id)
        if meeting.status not in {"ready", "processing", "transcribing", "failed"}:
            return meeting
        if not meeting.audio_path or not Path(meeting.audio_path).exists():
            meeting = self.store.update_meeting(meeting_id, status="failed", error="No raw audio file is available for processing.")
            await self.publish(meeting_id, {"type": "error", "message": meeting.error, "meeting": meeting_response(meeting, [])})
            return meeting

        meeting = self.store.update_meeting(meeting_id, status="transcribing", error=None)
        await self.publish(meeting_id, {"type": "meeting", "meeting": meeting_response(meeting, self.store.list_segments(meeting_id))})

        try:
            transcribed = await asyncio.to_thread(
                self.transcriber_factory().transcribe_audio,
                meeting.audio_path,
            )
            transcript_segments = [
                TranscriptSegment(
                    id=None,
                    meeting_id=meeting_id,
                    segment_index=idx,
                    start_seconds=segment.start_seconds,
                    end_seconds=segment.end_seconds,
                    text=segment.text,
                    status="final",
                )
                for idx, segment in enumerate(transcribed)
            ]
            self.store.replace_segments(meeting_id, transcript_segments)
            segments = self.store.list_segments(meeting_id)
            meeting = self.store.update_meeting(meeting_id, status="processing")
            await self.publish(
                meeting_id,
                {"type": "meeting", "meeting": meeting_response(meeting, segments)},
            )

            try:
                diarized = await asyncio.to_thread(
                    self.diarizer_factory().diarize,
                    meeting.audio_path,
                    segments,
                )
                for segment in diarized:
                    segment.meeting_id = meeting_id
                self.store.replace_segments(meeting_id, diarized)
                segments = self.store.list_segments(meeting_id)
            except Exception as exc:
                # Diarization is valuable but should not block summary or memory ingestion.
                await self.publish(meeting_id, {"type": "warning", "message": f"Diarization skipped: {exc}"})

            transcript = meeting_transcript_text(segments)
            summary = await self.summarizer_factory().summarize(meeting.title, transcript)
            meeting = self.store.save_summary(meeting_id, summary)
            entry = await asyncio.to_thread(ingest_meeting_into_memory, self.get_mem(), self.store, meeting_id)
            meeting = self.store.update_meeting(
                meeting_id,
                status="completed",
                memory_log_entry_id=entry.entry_id,
                error=None,
            )
            await self.publish(
                meeting_id,
                {"type": "meeting", "meeting": meeting_response(meeting, self.store.list_segments(meeting_id))},
            )
            return meeting
        except Exception as exc:
            meeting = self.store.update_meeting(meeting_id, status="failed", error=str(exc))
            await self.publish(
                meeting_id,
                {"type": "error", "message": str(exc), "meeting": meeting_response(meeting, self.store.list_segments(meeting_id))},
            )
            return meeting

    async def subscribe(self, meeting_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(meeting_id, set()).add(queue)
        meeting = self.store.get_meeting(meeting_id)
        await queue.put({"type": "meeting", "meeting": meeting_response(meeting, self.store.list_segments(meeting_id))})
        return queue

    def unsubscribe(self, meeting_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(meeting_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(meeting_id, None)

    async def publish(self, meeting_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers.get(meeting_id, set())):
            await queue.put(event)

    async def create_uploaded_meeting(
        self,
        *,
        title: str,
        audio_bytes: bytes,
        original_filename: str | None = None,
    ) -> Meeting:
        self.config.ensure_dirs()
        meeting = self.store.create_meeting(title)
        suffix = _audio_suffix(original_filename)
        audio_path = self.config.audio_dir / f"{meeting.id}{suffix}"
        audio_path.write_bytes(audio_bytes)
        now = datetime.now()
        duration = await asyncio.to_thread(_audio_duration, audio_path)
        meeting = self.store.update_meeting(
            meeting.id,
            status="ready",
            ended_at=now,
            duration_seconds=duration,
            audio_path=str(audio_path),
            error=None,
        )
        await self.publish(meeting.id, {"type": "meeting", "meeting": meeting_response(meeting, [])})
        return meeting


def meeting_response(meeting: Meeting, segments: list[TranscriptSegment]) -> dict[str, Any]:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "status": meeting.status,
        "created_at": iso_or_none(meeting.created_at),
        "started_at": iso_or_none(meeting.started_at),
        "ended_at": iso_or_none(meeting.ended_at),
        "duration_seconds": meeting.duration_seconds,
        "audio_path": meeting.audio_path,
        "error": meeting.error,
        "memory_log_entry_id": meeting.memory_log_entry_id,
        "summary": asdict(meeting.summary) if meeting.summary else None,
        "segment_count": len(segments) if segments else meeting.segment_count,
    }


def segment_response(segment: TranscriptSegment) -> dict[str, Any]:
    return {
        "id": segment.id,
        "meeting_id": segment.meeting_id,
        "segment_index": segment.segment_index,
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "text": segment.text,
        "speaker": segment.speaker,
        "status": segment.status,
        "created_at": iso_or_none(segment.created_at),
    }


def _audio_suffix(filename: str | None) -> str:
    if not filename:
        return ".wav"
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".aac"} else ".wav"


def _audio_duration(path: Path) -> float | None:
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                return frames / rate if rate else None
        except wave.Error:
            return None
    if shutil.which("ffprobe"):
        import subprocess

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            return float(result.stdout.strip())
        except ValueError:
            return None
    return None
