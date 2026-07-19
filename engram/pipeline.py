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
from engram.memory_adapter import ingest_meeting_into_memory, meeting_transcript_text, resolved_speaker_name
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
        self._processing_tasks: dict[str, asyncio.Task[Meeting]] = {}

    def start_processing(self, meeting_id: str) -> asyncio.Task[Meeting]:
        existing = self._processing_tasks.get(meeting_id)
        if existing and not existing.done():
            return existing

        task = asyncio.create_task(self.process_meeting(meeting_id))
        self._processing_tasks[meeting_id] = task

        def remove_completed(completed: asyncio.Task[Meeting]) -> None:
            if self._processing_tasks.get(meeting_id) is completed:
                self._processing_tasks.pop(meeting_id, None)

        task.add_done_callback(remove_completed)
        return task

    def recover_interrupted_meetings(self) -> list[Meeting]:
        recovered = []
        for meeting in self.store.list_meetings():
            if meeting.status in {"transcribing", "processing"}:
                recovered.append(
                    self.store.update_meeting(
                        meeting.id,
                        status="failed",
                        error="Processing was interrupted by a server restart. Retry the meeting to continue.",
                    )
                )
        return recovered

    async def process_meeting(self, meeting_id: str) -> Meeting:
        meeting = self.store.get_meeting(meeting_id)
        if meeting.status not in {"ready", "processing", "transcribing", "failed"}:
            return meeting
        if not meeting.audio_path or not Path(meeting.audio_path).exists():
            meeting = self.store.update_meeting(meeting_id, status="failed", error="No raw audio file is available for processing.")
            return meeting

        meeting = self.store.update_meeting(meeting_id, status="transcribing", error=None)

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
            except Exception:
                # Diarization is valuable but should not block summary or memory ingestion.
                pass

            meeting = self.store.update_meeting(
                meeting_id,
                status="reviewing",
                error=None,
            )
            return meeting
        except Exception as exc:
            meeting = self.store.update_meeting(meeting_id, status="failed", error=str(exc))
            return meeting

    async def update_speaker_names(self, meeting_id: str, speaker_names: dict[str, str]) -> Meeting:
        meeting = self.store.save_speaker_names(meeting_id, speaker_names)
        return meeting

    async def update_transcript(
        self,
        meeting_id: str,
        updates: dict[int, str],
        speaker: str | None = None,
    ) -> Meeting:
        meeting = self.store.get_meeting(meeting_id)
        if meeting.status != "reviewing":
            raise ValueError("Transcript can only be edited while the meeting is awaiting review.")
        self.store.update_segment_texts(meeting_id, updates, speaker=speaker)
        return self.store.get_meeting(meeting_id)

    async def delete_meeting(self, meeting_id: str) -> None:
        meeting = self.store.get_meeting(meeting_id)
        self.store.delete_meeting(meeting_id)
        if meeting.audio_path:
            audio_path = Path(meeting.audio_path)
            try:
                if audio_path.exists() and audio_path.is_file():
                    audio_path.unlink()
            except OSError:
                pass

    async def finalize_meeting(self, meeting_id: str) -> Meeting:
        meeting = self.store.get_meeting(meeting_id)
        if meeting.status == "completed":
            return meeting
        if meeting.status != "reviewing":
            raise ValueError("Meeting must be ready for review before finalization.")

        segments = self.store.list_segments(meeting_id)
        if not segments:
            raise ValueError("Meeting has no transcript segments to finalize.")

        meeting = self.store.update_meeting(meeting_id, status="processing", error=None)

        try:
            transcript = meeting_transcript_text(segments, meeting.speaker_names)
            summary = await self.summarizer_factory().summarize(meeting.title, transcript)
            meeting = self.store.save_summary(meeting_id, summary)
            entry = await asyncio.to_thread(ingest_meeting_into_memory, self.get_mem(), self.store, meeting_id)
            meeting = self.store.update_meeting(
                meeting_id,
                status="completed",
                memory_log_entry_id=entry.entry_id,
                error=None,
            )
            return meeting
        except Exception as exc:
            meeting = self.store.update_meeting(meeting_id, status="reviewing", error=str(exc))
            raise

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
        return meeting


def meeting_response(meeting: Meeting, segments: list[TranscriptSegment]) -> dict[str, Any]:
    response = {
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
        "speaker_names": meeting.speaker_names,
        "segment_count": len(segments) if segments else meeting.segment_count,
        "segments": [segment_response(segment, meeting.speaker_names) for segment in segments],
    }
    return response


def segment_response(segment: TranscriptSegment, speaker_names: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "id": segment.id,
        "meeting_id": segment.meeting_id,
        "segment_index": segment.segment_index,
        "start_seconds": segment.start_seconds,
        "end_seconds": segment.end_seconds,
        "text": segment.text,
        "speaker": segment.speaker,
        "display_speaker": resolved_speaker_name(segment.speaker, speaker_names),
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
