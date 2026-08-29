"""Temporal normalization and interval helpers for memory evidence."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

def normalize_temporal_facets(
    facets: dict[str, Any], anchor: str | None, claim_text: str | None = None
) -> dict[str, Any]:
    """Resolve relative time into one explicit, provenance-preserving interval."""
    result = dict(facets or {})
    existing_temporal = result.get("temporal")
    deadline_expression = result.pop("deadline", None)
    role = (
        str(existing_temporal.get("role") or "event_time")
        if isinstance(existing_temporal, dict)
        else "deadline" if deadline_expression else "event_time"
    )
    expression = str(
        (existing_temporal.get("expression") if isinstance(existing_temporal, dict) else None)
        or deadline_expression
        or result.pop("when", None)
        or result.pop("time_expression", None)
        or ""
    ).strip()
    for legacy_key in ("normalized_date", "date_precision", "normalization_anchor"):
        result.pop(legacy_key, None)
    if not expression and claim_text:
        deadline_match = re.search(
            r"\b(?:by|due(?: on)?)\s+("
            r"(?:last|this|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"(?:last|this|next) (?:week|month)|"
            r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"end of (?:this|next) (?:week|month)|"
            r"in (?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+) "
            r"(?:days?|weeks?)(?: from now)?|today|tomorrow)\b",
            claim_text,
            re.I,
        )
        if deadline_match:
            expression = deadline_match.group(1)
            role = "deadline"
    if not expression and claim_text:
        match = re.search(
            r"\b(today|yesterday|tomorrow|the day before yesterday|"
            r"the day after tomorrow|last week|this week|next week|"
            r"last month|this month|next month|"
            r"early next week|late next week|later this week|sometime next week|"
            r"soon|recently|"
            r"(?:in )?(?:a few|few|several) (?:days?|weeks?) "
            r"(?:ago|later|from now)|"
            r"(?:last|this|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"(?:in (?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|\d+) (?:days?|weeks?)(?: from now)?|"
            r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|\d+) (?:days?|weeks?) (?:ago|later|from now))|"
            r"(?:(?:a|one|two|three|\d+) )?years? ago)\b",
            claim_text,
            re.I,
        )
        if match:
            expression = match.group(0)
    if anchor:
        result.setdefault("observed_at", anchor)
    if not expression:
        return result
    temporal: dict[str, Any] = {
        "expression": expression,
        "anchor": anchor,
        "role": role,
        "status": "unresolved",
        "certainty": "unknown",
    }
    result["temporal"] = temporal
    if not anchor:
        return result
    base = parse_source_datetime(anchor)
    if base is None:
        return result
    temporal["anchor_date"] = base.date().isoformat()
    lowered = expression.lower()
    if role == "deadline":
        lowered = re.sub(r"^(?:by|due(?: on)?)\s+", "", lowered).strip()
    deadline_boundary = _deadline_boundary(lowered, base) if role == "deadline" else None
    if deadline_boundary is not None:
        normalized = deadline_boundary.isoformat()
        temporal.update({
            "start": normalized,
            "end": normalized,
            "precision": "day",
            "status": "resolved",
            "certainty": "exact",
        })
        return result
    vague = _vague_temporal_interval(lowered, base)
    if vague is not None:
        temporal.update(vague)
        return result
    if lowered in {"soon", "recently"}:
        temporal.update({
            "direction": "future" if lowered == "soon" else "past",
            "certainty": "vague",
        })
        return result
    target: datetime | None = None
    if lowered == "today":
        target = base
    elif lowered == "yesterday":
        target = base - timedelta(days=1)
    elif lowered == "tomorrow":
        target = base + timedelta(days=1)
    elif lowered == "the day before yesterday":
        target = base - timedelta(days=2)
    elif lowered == "the day after tomorrow":
        target = base + timedelta(days=2)
    elif lowered in {"last week", "this week", "next week"}:
        offset = {"last week": -1, "this week": 0, "next week": 1}[lowered]
        start = base.date() - timedelta(days=base.weekday()) + timedelta(weeks=offset)
        temporal.update({
            "start": start.isoformat(),
            "end": (start + timedelta(days=6)).isoformat(),
            "precision": "week",
            "status": "resolved",
            "certainty": "exact",
        })
        return result
    elif lowered in {"last month", "this month", "next month"}:
        offset = {"last month": -1, "this month": 0, "next month": 1}[lowered]
        month_index = base.year * 12 + base.month - 1 + offset
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        last_day = calendar.monthrange(year, month)[1]
        temporal.update({
            "start": f"{year:04d}-{month:02d}-01",
            "end": f"{year:04d}-{month:02d}-{last_day:02d}",
            "precision": "month",
            "status": "resolved",
            "certainty": "exact",
        })
        return result
    offset_days = _relative_offset_days(lowered)
    if offset_days is not None:
        target = base + timedelta(days=offset_days)
    years_ago = re.fullmatch(r"(?:(a|one|two|three|\d+) )?years? ago", lowered)
    if years_ago:
        raw_years = years_ago.group(1) or "one"
        years = {"a": 1, "one": 1, "two": 2, "three": 3}.get(raw_years)
        if years is None and raw_years.isdigit():
            years = int(raw_years)
        if years is not None and 0 < years <= 100:
            year = base.year - years
            temporal.update({
                "start": f"{year:04d}-01-01",
                "end": f"{year:04d}-12-31",
                "precision": "year",
                "status": "resolved",
                "certainty": "exact",
            })
            return result
    weekday = re.fullmatch(
        r"(last|this|next) "
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        lowered,
    )
    if weekday:
        desired = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(weekday.group(2))
        if weekday.group(1) == "last":
            target = base + timedelta(days=desired - base.weekday() - 7)
        elif weekday.group(1) == "next":
            target = base + timedelta(days=desired - base.weekday() + 7)
        else:
            target = base + timedelta(days=desired - base.weekday())
    if target is not None:
        normalized = target.date().isoformat()
        temporal.update({
            "start": normalized,
            "end": normalized,
            "precision": "day",
            "status": "resolved",
            "certainty": "exact",
        })
    return result


def temporal_record(facets: dict[str, Any]) -> dict[str, Any] | None:
    value = facets.get("temporal")
    return value if isinstance(value, dict) and value.get("expression") else None


def query_temporal_record(query: str, anchor: datetime) -> dict[str, Any] | None:
    facets = normalize_temporal_facets({}, anchor.isoformat(), query)
    temporal = temporal_record(facets)
    if temporal and re.search(r"\b(?:deadline|deadlines|due)\b", query, re.I):
        temporal["role"] = "deadline"
    return temporal


def temporal_intervals_overlap(
    left: dict[str, Any], right: dict[str, Any]
) -> bool:
    left_start = str(left.get("start") or "")
    left_end = str(left.get("end") or left_start)
    right_start = str(right.get("start") or "")
    right_end = str(right.get("end") or right_start)
    if not all((left_start, left_end, right_start, right_end)):
        return False
    return left_start <= right_end and right_start <= left_end


def _relative_offset_days(expression: str) -> int | None:
    match = re.fullmatch(
        r"(?:in (a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|\d+) (days?|weeks?)(?: (from now))?|"
        r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|\d+) (days?|weeks?) (ago|later|from now))",
        expression,
    )
    if not match:
        return None
    raw_count = match.group(1) or match.group(4)
    unit = match.group(2) or match.group(5)
    direction = match.group(3) or match.group(6) or "from now"
    count = NUMBER_WORDS.get(raw_count)
    if count is None and raw_count.isdigit():
        count = int(raw_count)
    if count is None or count <= 0 or count > 3660:
        return None
    days = count * (7 if unit.startswith("week") else 1)
    return -days if direction == "ago" else days


def _deadline_boundary(expression: str, anchor: datetime) -> date | None:
    weekdays = [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]
    if expression in weekdays:
        desired = weekdays.index(expression)
        return anchor.date() + timedelta(days=(desired - anchor.weekday()) % 7)
    if expression in {"end of this week", "end of next week"}:
        week_start = anchor.date() - timedelta(days=anchor.weekday())
        return week_start + timedelta(days=6 if expression == "end of this week" else 13)
    if expression in {"end of this month", "end of next month"}:
        offset = 0 if expression == "end of this month" else 1
        month_index = anchor.year * 12 + anchor.month - 1 + offset
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        return anchor.date().replace(
            year=year,
            month=month,
            day=calendar.monthrange(year, month)[1],
        )
    return None

def _vague_temporal_interval(
    expression: str, anchor: datetime
) -> dict[str, Any] | None:
    week_start = anchor.date() - timedelta(days=anchor.weekday())
    if expression in {"early next week", "late next week", "sometime next week"}:
        next_week = week_start + timedelta(weeks=1)
        offsets = {
            "early next week": (0, 2),
            "late next week": (4, 6),
            "sometime next week": (0, 6),
        }
        start_offset, end_offset = offsets[expression]
        return {
            "start": (next_week + timedelta(days=start_offset)).isoformat(),
            "end": (next_week + timedelta(days=end_offset)).isoformat(),
            "precision": "range",
            "status": "bounded",
            "certainty": "approximate",
        }
    if expression == "later this week":
        start = min(anchor.date() + timedelta(days=1), week_start + timedelta(days=6))
        return {
            "start": start.isoformat(),
            "end": (week_start + timedelta(days=6)).isoformat(),
            "precision": "range",
            "status": "bounded",
            "certainty": "approximate",
        }
    match = re.fullmatch(
        r"(?:in )?(a few|few|several) (days?|weeks?) (ago|later|from now)",
        expression,
    )
    if not match:
        return None
    quantity, unit, direction = match.groups()
    low, high = (2, 5) if quantity in {"a few", "few"} else (3, 7)
    multiplier = 7 if unit.startswith("week") else 1
    low *= multiplier
    high *= multiplier
    if direction == "ago":
        start = anchor.date() - timedelta(days=high)
        end = anchor.date() - timedelta(days=low)
    else:
        start = anchor.date() + timedelta(days=low)
        end = anchor.date() + timedelta(days=high)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "precision": "range",
        "status": "bounded",
        "certainty": "approximate",
    }


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
