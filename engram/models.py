from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

MeetingStatus = Literal["ready", "transcribing", "processing", "reviewing", "completed", "failed"]
SegmentStatus = Literal["live", "final", "diarized"]


@dataclass
class TranscriptSegment:
    id: int | None
    meeting_id: str
    segment_index: int
    start_seconds: float
    end_seconds: float
    text: str
    speaker: str | None = None
    status: SegmentStatus = "final"
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class MeetingSummary:
    summary: str
    decisions: list[str] = field(default_factory=list)
    action_items: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)


@dataclass
class Meeting:
    id: str
    title: str
    status: MeetingStatus
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    audio_path: str | None = None
    error: str | None = None
    memory_log_entry_id: str | None = None
    summary: MeetingSummary | None = None
    speaker_names: dict[str, str] = field(default_factory=dict)
    segment_count: int = 0


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
