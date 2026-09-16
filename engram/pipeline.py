from __future__ import annotations

import asyncio
import shutil
import wave
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, BinaryIO

from engram.config import EngramConfig
from engram.jobs import finish_before_cancelling
from engram.diarize import WhisperXDiarizer
from engram.memory_adapter import (
    encode_meeting_into_memory,
    meeting_transcript_text,
    resolved_speaker_name,
)
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
        self.transcriber_factory = transcriber_factory or (
            lambda: FasterWhisperTranscriber(self.config)
        )
        self.diarizer_factory = diarizer_factory or (
            lambda: WhisperXDiarizer(self.config)
        )
        self.summarizer_factory = summarizer_factory or (
            lambda: EngramSummarizer(
                ollama_url=self.config.ollama_url,
                model=self.config.ollama_model,
                temperature=self.config.summary_temperature,
                context_window_tokens=self.config.summary_context_window_tokens,
                trace_path=self.config.store_path / "diagnostics" / "llm-calls.jsonl",
            )
        )
        self._processing_tasks: dict[str, asyncio.Task[Meeting]] = {}
        self._processing_lock = asyncio.Lock()
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._deleting: set[str] = set()

    def _ensure_idle(self, meeting_id: str) -> None:
        task = self._active_tasks.get(meeting_id) or self._processing_tasks.get(
            meeting_id
        )
        if meeting_id in self._deleting or (
            task is not None and not task.done() and task is not asyncio.current_task()
        ):
            raise ValueError("A meeting operation is already in progress")

    @asynccontextmanager
    async def _operation(self, meeting_id: str):
        self._ensure_idle(meeting_id)
        task = asyncio.current_task()
        self._active_tasks[meeting_id] = task
        try:
            yield
        finally:
            if self._active_tasks.get(meeting_id) is task:
                self._active_tasks.pop(meeting_id)

    def start_processing(self, meeting_id: str) -> asyncio.Task[Meeting]:
        existing = self._processing_tasks.get(meeting_id)
        if existing and not existing.done():
            return existing

        self._ensure_idle(meeting_id)

        task = asyncio.create_task(self.process_meeting(meeting_id))
        self._processing_tasks[meeting_id] = task

        def remove_completed(completed: asyncio.Task[Meeting]) -> None:
            if self._processing_tasks.get(meeting_id) is completed:
                self._processing_tasks.pop(meeting_id, None)
            if not completed.cancelled() and completed.exception() is not None:
                logging.getLogger(__name__).error(
                    "Meeting processing failed: %s", completed.exception()
                )

        task.add_done_callback(remove_completed)
        return task

    def recover_interrupted_meetings(self) -> list[Meeting]:
        recovered = []
        for meeting in self.store.list_meetings():
            if meeting.status == "processing" and self.store.list_segments(meeting.id):
                self.store.add_warning(
                    meeting.id,
                    "diarization",
                    "Speaker detection was interrupted by a server restart. The transcript is preserved.",
                )
                recovered.append(
                    self.store.update_meeting(
                        meeting.id, status="reviewing", error=None
                    )
                )
            elif meeting.status in {"transcribing", "processing"}:
                recovered.append(
                    self.store.update_meeting(
                        meeting.id,
                        status="failed",
                        error="Processing was interrupted by a server restart. Retry the meeting to continue.",
                    )
                )
            elif meeting.status == "finalizing":
                if meeting.memory_log_entry_id and meeting.summary is not None:
                    self.store.resolve_warnings(meeting.id, "summary")
                elif meeting.memory_log_entry_id:
                    self.store.add_warning(
                        meeting.id,
                        "summary",
                        "Summary generation was interrupted by a server restart.",
                    )
                recovered.append(
                    self.store.update_meeting(
                        meeting.id,
                        status="completed"
                        if meeting.memory_log_entry_id
                        else "reviewing",
                        error=None
                        if meeting.memory_log_entry_id
                        else "Source admission was interrupted. Retry finalization with the frozen transcript.",
                    )
                )
        return recovered

    async def process_meeting(self, meeting_id: str) -> Meeting:
        # Speech models share the same device; bound their lifetime to one job.
        async with self._operation(meeting_id):
            meeting = self.store.get_meeting(meeting_id)
            if meeting.status not in {"ready", "processing", "transcribing", "failed"}:
                return meeting
            if meeting.admission_started_at or meeting.memory_log_entry_id:
                raise ValueError("Admitted transcripts cannot be reprocessed")
            try:
                async with self._processing_lock:
                    return await self._process_meeting(meeting_id)
            except asyncio.CancelledError:
                self.store.update_meeting(
                    meeting_id, status="failed", error="Processing was cancelled."
                )
                raise

    async def _process_meeting(self, meeting_id: str) -> Meeting:
        meeting = self.store.get_meeting(meeting_id)
        if meeting.status not in {"ready", "processing", "transcribing", "failed"}:
            return meeting
        if meeting.admission_started_at or meeting.memory_log_entry_id:
            raise ValueError("Admitted transcripts cannot be reprocessed")
        if not meeting.audio_path or not Path(meeting.audio_path).exists():
            meeting = self.store.update_meeting(
                meeting_id,
                status="failed",
                error="No raw audio file is available for processing.",
            )
            return meeting

        meeting = self.store.update_meeting(
            meeting_id, status="transcribing", error=None
        )

        try:
            transcribed = await finish_before_cancelling(
                asyncio.to_thread(
                    lambda: self.transcriber_factory().transcribe_audio(
                        meeting.audio_path
                    ),
                )
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

            await self._diarize(meeting, segments)
            meeting = self.store.update_meeting(
                meeting_id,
                status="reviewing",
                error=None,
            )
            return meeting
        except Exception as exc:
            meeting = self.store.update_meeting(
                meeting_id, status="failed", error=str(exc)
            )
            return meeting

    async def update_speaker_names(
        self, meeting_id: str, speaker_names: dict[str, str]
    ) -> Meeting:
        self._ensure_idle(meeting_id)
        meeting = self.store.get_meeting(meeting_id)
        if meeting.admission_started_at or meeting.memory_log_entry_id:
            raise ValueError(
                "Speaker labels cannot change after source admission starts."
            )
        if meeting.status != "reviewing":
            raise ValueError("Speaker labels can only be edited during review.")
        meeting = self.store.save_speaker_names(meeting_id, speaker_names)
        return meeting

    async def retry_diarization(self, meeting_id: str) -> Meeting:
        """Retry speaker detection using the reviewed transcript, without ASR."""
        async with self._operation(meeting_id):
            meeting = self.store.get_meeting(meeting_id)
            if (
                meeting.status != "reviewing"
                or meeting.memory_log_entry_id
                or meeting.admission_started_at
            ):
                raise ValueError(
                    "Speaker detection can only retry before source admission during review"
                )
            try:
                async with self._processing_lock:
                    segments = self.store.list_segments(meeting_id)
                    self.store.update_meeting(
                        meeting_id, status="processing", error=None
                    )
                    await self._diarize(meeting, segments)
                    return self.store.update_meeting(
                        meeting_id, status="reviewing", error=None
                    )
            except asyncio.CancelledError:
                self.store.add_warning(
                    meeting_id, "diarization", "Speaker detection was cancelled."
                )
                self.store.update_meeting(meeting_id, status="reviewing")
                raise

    async def _diarize(self, meeting, segments):
        expected = [
            (s.segment_index, s.text, s.start_seconds, s.end_seconds) for s in segments
        ]
        try:
            diarized = await finish_before_cancelling(
                asyncio.to_thread(
                    lambda: self.diarizer_factory().diarize(
                        meeting.audio_path, segments
                    ),
                )
            )
            if [
                (s.segment_index, s.text, s.start_seconds, s.end_seconds)
                for s in diarized
            ] != expected:
                raise ValueError("Speaker detection changed the transcript")
            for segment in diarized:
                segment.meeting_id = meeting.id
            self.store.replace_segments(meeting.id, diarized)
            self.store.resolve_warnings(meeting.id, "diarization")
        except Exception as exc:
            self.store.add_warning(
                meeting.id, "diarization", f"{type(exc).__name__}: {exc}"
            )

    async def update_transcript(
        self,
        meeting_id: str,
        updates: dict[int, str],
        speaker: str | None = None,
    ) -> Meeting:
        self._ensure_idle(meeting_id)
        meeting = self.store.get_meeting(meeting_id)
        if meeting.admission_started_at or meeting.memory_log_entry_id:
            raise ValueError("Transcript cannot change after source admission starts.")
        if meeting.status != "reviewing":
            raise ValueError(
                "Transcript can only be edited while the meeting is awaiting review."
            )
        self.store.update_segment_texts(meeting_id, updates, speaker=speaker)
        return self.store.get_meeting(meeting_id)

    async def delete_meeting(self, meeting_id: str) -> None:
        meeting = self.store.get_meeting(meeting_id)
        if meeting_id in self._deleting:
            raise ValueError("Meeting deletion is already in progress")
        audio_path = Path(meeting.audio_path).resolve() if meeting.audio_path else None
        if audio_path is not None and not audio_path.is_relative_to(
            self.config.audio_dir.resolve()
        ):
            raise ValueError("Meeting audio is outside the configured audio directory")
        self._deleting.add(meeting_id)
        try:
            task = self._active_tasks.get(meeting_id) or self._processing_tasks.get(
                meeting_id
            )
            if task is not None and not task.done():
                task.cancel()
                await asyncio.shield(asyncio.gather(task, return_exceptions=True))
                try:
                    self.store.get_meeting(meeting_id)
                except FileNotFoundError:
                    # A cancelled upload removes its partial file and meeting together.
                    return
            if audio_path is not None:
                audio_path.unlink(missing_ok=True)
            self.store.delete_meeting(meeting_id)
        finally:
            self._deleting.discard(meeting_id)

    async def finalize_meeting(self, meeting_id: str) -> Meeting:
        async with self._operation(meeting_id):
            try:
                return await self._finalize_meeting(meeting_id)
            except asyncio.CancelledError:
                meeting = self.store.get_meeting(meeting_id)
                if meeting.memory_log_entry_id:
                    self.store.add_warning(
                        meeting_id,
                        "summary",
                        "Summary generation was cancelled after source admission.",
                    )
                self.store.update_meeting(
                    meeting_id,
                    status="completed" if meeting.memory_log_entry_id else "reviewing",
                    error=None
                    if meeting.memory_log_entry_id
                    else "Source admission was cancelled. Retry finalization with the frozen transcript.",
                )
                raise

    async def _finalize_meeting(self, meeting_id: str) -> Meeting:
        meeting = self.store.get_meeting(meeting_id)
        if meeting.status == "completed" and meeting.summary is not None:
            return meeting
        if meeting.status not in {"reviewing", "completed"}:
            raise ValueError("Meeting must be ready for review before finalization.")
        segments = self.store.list_segments(meeting_id)
        if not segments:
            raise ValueError("Meeting has no transcript segments to finalize.")
        self.store.freeze_for_admission(meeting_id)
        self.store.update_meeting(meeting_id, status="finalizing", error=None)
        try:
            entry = await finish_before_cancelling(
                encode_meeting_into_memory(self.get_mem(), self.store, meeting_id)
            )
        except Exception as exc:
            self.store.update_meeting(meeting_id, status="reviewing", error=str(exc))
            raise
        # Source admission is durable before optional summary generation.
        meeting = self.store.update_meeting(
            meeting_id,
            memory_log_entry_id=entry.entry_id,
            error=None,
        )
        try:
            transcript = meeting_transcript_text(segments, meeting.speaker_names)
            summary = await self.summarizer_factory().summarize(
                meeting.title, transcript
            )
            self.store.save_summary(meeting_id, summary)
            self.store.resolve_warnings(meeting_id, "summary")
            return self.store.update_meeting(meeting_id, status="completed", error=None)
        except Exception as exc:
            self.store.add_warning(
                meeting_id, "summary", f"{type(exc).__name__}: {exc}"
            )
            return self.store.update_meeting(
                meeting_id,
                status="completed",
                error=None,
            )

    async def create_uploaded_meeting(
        self,
        *,
        title: str,
        audio_stream: BinaryIO,
        original_filename: str | None = None,
    ) -> Meeting:
        self.config.ensure_dirs()
        meeting = self.store.create_meeting(title)
        async with self._operation(meeting.id):
            return await self._store_upload(meeting, audio_stream, original_filename)

    async def _store_upload(self, meeting, audio_stream, original_filename):
        suffix = _audio_suffix(original_filename)
        audio_path = self.config.audio_dir / f"{meeting.id}{suffix}"

        def copy_upload():
            total = 0
            with audio_path.open("xb") as target:
                while chunk := audio_stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > self.config.max_upload_bytes:
                        raise ValueError(
                            "Audio upload exceeds the configured size limit"
                        )
                    target.write(chunk)
            if not total:
                raise ValueError("Audio upload is empty")

        try:
            await finish_before_cancelling(asyncio.to_thread(copy_upload))
            now = datetime.now()
            duration = await finish_before_cancelling(
                asyncio.to_thread(_audio_duration, audio_path)
            )
            meeting = self.store.update_meeting(
                meeting.id,
                status="ready",
                ended_at=now,
                duration_seconds=duration,
                audio_path=str(audio_path),
                error=None,
            )
        except BaseException:
            audio_path.unlink(missing_ok=True)
            self.store.delete_meeting(meeting.id)
            raise
        return meeting


def meeting_response(
    meeting: Meeting, segments: list[TranscriptSegment]
) -> dict[str, Any]:
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
        "warnings": [
            {
                **asdict(warning),
                "created_at": iso_or_none(warning.created_at),
                "resolved_at": iso_or_none(warning.resolved_at),
            }
            for warning in meeting.warnings
        ],
        "admission_started_at": iso_or_none(meeting.admission_started_at),
        "memory_log_entry_id": meeting.memory_log_entry_id,
        "summary": asdict(meeting.summary) if meeting.summary else None,
        "speaker_names": meeting.speaker_names,
        "segment_count": len(segments) if segments else meeting.segment_count,
        "segments": [
            segment_response(segment, meeting.speaker_names) for segment in segments
        ],
    }
    return response


def segment_response(
    segment: TranscriptSegment, speaker_names: dict[str, str] | None = None
) -> dict[str, Any]:
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
    return (
        suffix
        if suffix in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm", ".aac"}
        else ".wav"
    )


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
