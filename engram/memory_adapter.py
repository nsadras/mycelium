from __future__ import annotations

from engram.models import TranscriptSegment
from engram.store import EngramStore
from mycelium.models import LogEntry
from mycelium.artifacts import SourceSegment


def resolved_speaker_name(speaker: str | None, speaker_names: dict[str, str] | None = None) -> str:
    if not speaker:
        return "Speaker ?"
    if speaker_names and speaker_names.get(speaker):
        return speaker_names[speaker]
    return speaker


def meeting_transcript_text(segments: list[TranscriptSegment], speaker_names: dict[str, str] | None = None) -> str:
    lines = []
    for segment in segments:
        speaker = resolved_speaker_name(segment.speaker, speaker_names)
        lines.append(
            f"[{_fmt_time(segment.start_seconds)}-{_fmt_time(segment.end_seconds)}] "
            f"{speaker}: {segment.text}"
        )
    return "\n".join(lines)


async def encode_meeting_into_memory(mem, store: EngramStore, meeting_id: str) -> LogEntry:
    """Encode a meeting through the source→episode→claim pipeline."""
    meeting = store.get_meeting(meeting_id)
    if meeting.memory_log_entry_id:
        return mem.log_store.get(meeting.memory_log_entry_id)
    transcript_segments = store.list_segments(meeting_id)
    explicit_segments = [
        SourceSegment(
            segment_id=segment.id,
            index=segment.segment_index,
            speaker=resolved_speaker_name(segment.speaker, meeting.speaker_names),
            content=segment.text,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            metadata={"engram_segment_id": segment.id},
        )
        for segment in transcript_segments
    ]
    transcript = meeting_transcript_text(transcript_segments, meeting.speaker_names)
    entries = await mem.encoder.encode_session(
        transcript,
        f"meeting-{meeting.id}",
        source_type="meeting_transcript",
        occurred_at=meeting.started_at,
        participants=list(dict.fromkeys(segment.speaker for segment in explicit_segments if segment.speaker)),
        segments=explicit_segments,
        metadata={
            "meeting_id": meeting.id,
            "title": meeting.title,
            "ended_at": meeting.ended_at.isoformat() if meeting.ended_at else None,
            "summary": meeting.summary.summary if meeting.summary else None,
        },
    )
    if not entries:
        raise ValueError("Meeting transcript was empty")
    store.update_meeting(meeting_id, memory_log_entry_id=entries[0].entry_id)
    return entries[0]


def _fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"
