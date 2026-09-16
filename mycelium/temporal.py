"""Validate declared time semantics and apply exact calendar operations."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, TYPE_CHECKING

from mycelium.temporal_contract import ExtractedDetails, resolve_annotation

if TYPE_CHECKING:
    from mycelium.artifact_models import SourceDocument


def source_time_anchors(sources: list[SourceDocument]) -> dict[str, str | None]:
    """Use per-message dates; an undated message in a dated transcript stays unknown."""
    anchors = {}
    for source in sources:
        message_dated = any(segment.timestamp for segment in source.segments)
        for segment in source.segments:
            anchors[segment.segment_id] = segment.timestamp or (
                None if message_dated else source.occurred_at
            )
    return anchors


def normalize_temporal_facets(
    facets: dict[str, Any], anchors: dict[str, str | None]
) -> dict[str, Any]:
    details = ExtractedDetails.model_validate(facets)
    times = []
    for annotation in details.times:
        if annotation.evidence_segment_id not in anchors:
            raise ValueError("Time evidence must identify a supplied cited segment")
        times.append(
            resolve_annotation(
                annotation,
                anchors[annotation.evidence_segment_id],
                annotation.evidence_segment_id,
            ).model_dump()
        )
    return {"temporal": times, "inference_basis": details.inference_basis}


def temporal_records(facets: dict[str, Any]) -> list[dict[str, Any]]:
    times = facets.get("temporal", [])
    if not isinstance(times, list):
        raise ValueError("Temporal evidence must be a list of declared annotations")
    return times


def temporal_intervals_overlap(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_start = str(left.get("start") or "")
    left_end = str(left.get("end") or left_start)
    right_start = str(right.get("start") or "")
    right_end = str(right.get("end") or right_start)
    if not all((left_start, left_end, right_start, right_end)):
        return False
    return left_start <= right_end and right_start <= left_end


def parse_source_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in (
        "%I:%M %p on %d %B, %Y",
        "%I:%M%p on %d %B, %Y",
        "%d %B, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None
