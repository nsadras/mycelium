from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from engram.models import Meeting, MeetingSummary, SegmentStatus, TranscriptSegment


def _now() -> datetime:
    return datetime.now()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


class EngramStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meetings (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_seconds REAL,
                    audio_path TEXT,
                    error TEXT,
                    summary_json TEXT,
                    speaker_names_json TEXT,
                    memory_log_entry_id TEXT
                )
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(meetings)").fetchall()}
            if "speaker_names_json" not in columns:
                conn.execute("ALTER TABLE meetings ADD COLUMN speaker_names_json TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meeting_id TEXT NOT NULL,
                    segment_index INTEGER NOT NULL,
                    start_seconds REAL NOT NULL,
                    end_seconds REAL NOT NULL,
                    text TEXT NOT NULL,
                    speaker TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(meeting_id) REFERENCES meetings(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_segments_meeting ON transcript_segments(meeting_id, segment_index)"
            )

    def create_meeting(self, title: str | None = None) -> Meeting:
        meeting_id = str(uuid.uuid4())[:8]
        now = _now()
        meeting = Meeting(
            id=meeting_id,
            title=(title or "Untitled meeting").strip() or "Untitled meeting",
            status="ready",
            created_at=now,
            started_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO meetings (id, title, status, created_at, started_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (meeting.id, meeting.title, meeting.status, now.isoformat(), now.isoformat()),
            )
        return meeting

    def list_meetings(self) -> list[Meeting]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.*, COUNT(s.id) AS segment_count
                FROM meetings m
                LEFT JOIN transcript_segments s ON s.meeting_id = m.id
                GROUP BY m.id
                ORDER BY COALESCE(m.started_at, m.created_at) DESC
                """
            ).fetchall()
        return [self._meeting_from_row(row) for row in rows]

    def get_meeting(self, meeting_id: str) -> Meeting:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT m.*, COUNT(s.id) AS segment_count
                FROM meetings m
                LEFT JOIN transcript_segments s ON s.meeting_id = m.id
                WHERE m.id = ?
                GROUP BY m.id
                """,
                (meeting_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Meeting {meeting_id} not found.")
        return self._meeting_from_row(row)

    def update_meeting(self, meeting_id: str, **fields: Any) -> Meeting:
        if not fields:
            return self.get_meeting(meeting_id)
        allowed = {
            "title",
            "status",
            "started_at",
            "ended_at",
            "duration_seconds",
            "audio_path",
            "error",
            "memory_log_entry_id",
        }
        assignments = []
        values = []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unsupported meeting field: {key}")
            assignments.append(f"{key} = ?")
            values.append(value.isoformat() if isinstance(value, datetime) else value)
        values.append(meeting_id)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE meetings SET {', '.join(assignments)} WHERE id = ?", values)
            if cur.rowcount == 0:
                raise FileNotFoundError(f"Meeting {meeting_id} not found.")
        return self.get_meeting(meeting_id)

    def save_speaker_names(self, meeting_id: str, speaker_names: dict[str, str]) -> Meeting:
        normalized = {
            str(label).strip(): str(name).strip()
            for label, name in speaker_names.items()
            if str(label).strip() and str(name).strip()
        }
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE meetings SET speaker_names_json = ? WHERE id = ?",
                (json.dumps(normalized, sort_keys=True), meeting_id),
            )
            if cur.rowcount == 0:
                raise FileNotFoundError(f"Meeting {meeting_id} not found.")
        return self.get_meeting(meeting_id)

    def save_summary(self, meeting_id: str, summary: MeetingSummary) -> Meeting:
        payload = json.dumps(
            {
                "summary": summary.summary,
                "decisions": summary.decisions,
                "action_items": summary.action_items,
                "open_questions": summary.open_questions,
            },
            indent=2,
        )
        with self._connect() as conn:
            cur = conn.execute("UPDATE meetings SET summary_json = ? WHERE id = ?", (payload, meeting_id))
            if cur.rowcount == 0:
                raise FileNotFoundError(f"Meeting {meeting_id} not found.")
        return self.get_meeting(meeting_id)

    def add_segment(
        self,
        meeting_id: str,
        *,
        start_seconds: float,
        end_seconds: float,
        text: str,
        speaker: str | None = None,
        status: SegmentStatus = "final",
        segment_index: int | None = None,
    ) -> TranscriptSegment:
        if segment_index is None:
            segment_index = self.next_segment_index(meeting_id)
        created_at = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO transcript_segments (
                    meeting_id, segment_index, start_seconds, end_seconds, text, speaker, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meeting_id,
                    segment_index,
                    start_seconds,
                    end_seconds,
                    text.strip(),
                    speaker,
                    status,
                    created_at.isoformat(),
                ),
            )
            segment_id = cur.lastrowid
        return TranscriptSegment(
            id=segment_id,
            meeting_id=meeting_id,
            segment_index=segment_index,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            text=text.strip(),
            speaker=speaker,
            status=status,
            created_at=created_at,
        )

    def replace_segments(self, meeting_id: str, segments: list[TranscriptSegment]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,))
            for idx, segment in enumerate(segments):
                conn.execute(
                    """
                    INSERT INTO transcript_segments (
                        meeting_id, segment_index, start_seconds, end_seconds, text, speaker, status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        meeting_id,
                        idx,
                        segment.start_seconds,
                        segment.end_seconds,
                        segment.text.strip(),
                        segment.speaker,
                        segment.status,
                        segment.created_at.isoformat(),
                    ),
                )

    def list_segments(self, meeting_id: str) -> list[TranscriptSegment]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM transcript_segments
                WHERE meeting_id = ?
                ORDER BY segment_index ASC, id ASC
                """,
                (meeting_id,),
            ).fetchall()
        return [self._segment_from_row(row) for row in rows]

    def update_segment_texts(
        self,
        meeting_id: str,
        updates: dict[int, str],
        *,
        speaker: str | None = None,
    ) -> list[TranscriptSegment]:
        if not updates:
            return self.list_segments(meeting_id)

        normalized = {segment_id: text.strip() for segment_id, text in updates.items()}
        if any(not text for text in normalized.values()):
            raise ValueError("Transcript segment text cannot be empty.")
        normalized_speaker = speaker.strip() if speaker is not None else None
        if speaker is not None and not normalized_speaker:
            raise ValueError("Speaker label cannot be empty.")

        with self._connect() as conn:
            placeholders = ", ".join("?" for _ in normalized)
            rows = conn.execute(
                f"SELECT id FROM transcript_segments WHERE meeting_id = ? AND id IN ({placeholders})",
                (meeting_id, *normalized),
            ).fetchall()
            found_ids = {int(row["id"]) for row in rows}
            if found_ids != set(normalized):
                raise ValueError("One or more transcript segments do not belong to this meeting.")
            conn.executemany(
                "UPDATE transcript_segments SET text = ? WHERE meeting_id = ? AND id = ?",
                [(text, meeting_id, segment_id) for segment_id, text in normalized.items()],
            )
            if normalized_speaker is not None:
                conn.executemany(
                    "UPDATE transcript_segments SET speaker = ?, status = 'diarized' WHERE meeting_id = ? AND id = ?",
                    [(normalized_speaker, meeting_id, segment_id) for segment_id in normalized],
                )

        return self.list_segments(meeting_id)

    def delete_meeting(self, meeting_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,))
            cur = conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            if cur.rowcount == 0:
                raise FileNotFoundError(f"Meeting {meeting_id} not found.")

    def next_segment_index(self, meeting_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(segment_index), -1) + 1 AS next_idx FROM transcript_segments WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
        return int(row["next_idx"])

    def _meeting_from_row(self, row: sqlite3.Row) -> Meeting:
        summary_json = row["summary_json"]
        speaker_names_json = row["speaker_names_json"] if "speaker_names_json" in row.keys() else None
        summary = None
        if summary_json:
            data = json.loads(summary_json)
            summary = MeetingSummary(
                summary=data.get("summary", ""),
                decisions=list(data.get("decisions", [])),
                action_items=list(data.get("action_items", [])),
                open_questions=list(data.get("open_questions", [])),
            )
        return Meeting(
            id=row["id"],
            title=row["title"],
            status=row["status"],
            created_at=_parse_dt(row["created_at"]) or _now(),
            started_at=_parse_dt(row["started_at"]),
            ended_at=_parse_dt(row["ended_at"]),
            duration_seconds=row["duration_seconds"],
            audio_path=row["audio_path"],
            error=row["error"],
            memory_log_entry_id=row["memory_log_entry_id"],
            summary=summary,
            speaker_names=json.loads(speaker_names_json) if speaker_names_json else {},
            segment_count=int(row["segment_count"]) if "segment_count" in row.keys() else 0,
        )

    def _segment_from_row(self, row: sqlite3.Row) -> TranscriptSegment:
        return TranscriptSegment(
            id=row["id"],
            meeting_id=row["meeting_id"],
            segment_index=row["segment_index"],
            start_seconds=row["start_seconds"],
            end_seconds=row["end_seconds"],
            text=row["text"],
            speaker=row["speaker"],
            status=row["status"],
            created_at=_parse_dt(row["created_at"]) or _now(),
        )
