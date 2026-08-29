"""Source transcript segmentation for artifact ingestion."""

from __future__ import annotations

import re

from mycelium.artifact_models import SourceSegment

_LABELED_TRANSCRIPT_LINE = re.compile(
    r"^\[(?P<label>[^]]+)]\s*(?:\((?P<time>[^)]+)\)\s*)?(?P<speaker>[^:]+):\s*(?P<text>.*)$"
)
_ROLE_LINE = re.compile(r"^(?P<role>USER|ASSISTANT|SYSTEM|TOOL)(?:\s*\([^)]*\))?:\s*(?P<text>.*)$", re.I)


def segment_transcript(transcript: str, source_id: str) -> list[SourceSegment]:
    """Split common transcript formats while preserving every nonempty line."""
    segments: list[SourceSegment] = []
    current: SourceSegment | None = None
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not segments and re.match(r"^(Session|Timestamp|Sample):\s*", line, re.I):
            continue
        labeled_turn = _LABELED_TRANSCRIPT_LINE.match(line)
        role_match = _ROLE_LINE.match(line)
        if labeled_turn:
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments),
                speaker=labeled_turn.group("speaker").strip(),
                timestamp=labeled_turn.group("time"),
                content=labeled_turn.group("text").strip(),
                metadata={"source_label": labeled_turn.group("label")},
            )
            segments.append(current)
        elif role_match:
            role = role_match.group("role").lower()
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments), role=role, speaker=role,
                content=role_match.group("text").strip(),
            )
            segments.append(current)
        elif current is not None:
            current.content = f"{current.content}\n{line}".strip()
        else:
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments), content=line,
            )
            segments.append(current)
    return segments
