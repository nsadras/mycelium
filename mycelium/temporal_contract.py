"""Model-declared time meaning; calendar arithmetic never interprets prose."""

import calendar
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator


class StrictTimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AbsoluteInterval(StrictTimeModel):
    kind: Literal["absolute"]
    start: str = Field(
        description="Explicit ISO calendar date YYYY-MM-DD, including the evidenced year"
    )
    end: str = Field(description="Inclusive ISO calendar date YYYY-MM-DD")
    precision: Literal["day", "week", "month", "year", "range"]

    @model_validator(mode="after")
    def valid_dates(self):
        for value in (self.start, self.end):
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("Dates must use YYYY-MM-DD")
        if self.start > self.end:
            raise ValueError("Time interval ends before it starts")
        if self.precision == "day" and self.start != self.end:
            raise ValueError("Day precision requires one date")
        start, end = date.fromisoformat(self.start), date.fromisoformat(self.end)
        if self.precision == "week" and (
            start.weekday() != 0 or (end - start).days != 6
        ):
            raise ValueError("Week precision requires a complete Monday-to-Sunday week")
        if self.precision == "month" and (
            start.day != 1
            or start.year != end.year
            or start.month != end.month
            or end.day != calendar.monthrange(end.year, end.month)[1]
        ):
            raise ValueError("Month precision requires one complete calendar month")
        if self.precision == "year" and (
            start != date(start.year, 1, 1) or end != date(start.year, 12, 31)
        ):
            raise ValueError("Year precision requires one complete calendar year")
        return self


class DayOffset(StrictTimeModel):
    kind: Literal["day_offset"]
    days: int = Field(
        strict=True,
        description="Exact signed number of days from the cited message date",
    )


class CalendarPeriod(StrictTimeModel):
    kind: Literal["calendar_period"]
    unit: Literal["week", "month", "year"]
    offset: int = Field(
        strict=True,
        description="Signed number of whole calendar periods from the cited message period",
    )


class UnresolvedTime(StrictTimeModel):
    kind: Literal["unresolved"]
    reason: str = Field(min_length=1, max_length=300)


WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
RELATIVE_TIME_KINDS = frozenset(
    {"day_offset", "calendar_period", "weekday_in_week", "weekday_occurrence"}
)


class WeekdayInWeek(StrictTimeModel):
    kind: Literal["weekday_in_week"]
    weekday: Literal.__getitem__(WEEKDAYS)
    week_offset: int = Field(
        strict=True,
        description="Signed whole weeks relative to the cited message's Monday-to-Sunday week; zero means that same calendar week.",
    )


class WeekdayOccurrence(StrictTimeModel):
    kind: Literal["weekday_occurrence"]
    weekday: Literal.__getitem__(WEEKDAYS)
    direction: Literal["next", "previous", "on_or_after", "on_or_before"]


class RecurringTime(StrictTimeModel):
    kind: Literal["recurring"]


TimeMeaning = (
    AbsoluteInterval
    | DayOffset
    | CalendarPeriod
    | UnresolvedTime
    | WeekdayInWeek
    | WeekdayOccurrence
    | RecurringTime
)


class TimeAnnotation(StrictTimeModel):
    expression: str = Field(
        min_length=1,
        max_length=300,
        description="Verbatim time words from the cited evidence",
    )
    target: str = Field(
        min_length=1,
        max_length=300,
        description="The action or state these time words actually constrain",
    )
    role: Literal["event_time", "deadline", "condition_time"]
    evidence_segment_id: str = Field(min_length=1)
    meaning: TimeMeaning


class ExtractedDetails(StrictTimeModel):
    times: list[TimeAnnotation] = Field(max_length=8)
    inference_basis: str | None


def temporal_details_model(segment_ids):
    ids = tuple(sorted(set(segment_ids)))
    if not ids:
        raise ValueError("Temporal decisions require evidence IDs")
    annotation = create_model(
        "CitedTimeAnnotation",
        __base__=TimeAnnotation,
        evidence_segment_id=(Literal.__getitem__(ids), ...),
    )
    return create_model(
        "CitedExtractedDetails",
        __base__=ExtractedDetails,
        times=(list[annotation], Field(max_length=8)),
    )


class CanonicalTime(TimeAnnotation):
    anchor: str | None
    anchor_segment_id: str | None
    reference_reason: str | None = Field(min_length=1, max_length=300)
    start: str | None
    end: str | None
    precision: Literal["day", "week", "month", "year", "range"] | None
    status: Literal["resolved", "unresolved", "recurring"]
    resolution_error: (
        Literal["missing_anchor", "invalid_anchor", "calendar_overflow"] | None
    )

    @model_validator(mode="after")
    def dates_match_declaration(self):
        if self.anchor is not None and self.anchor_segment_id is None:
            raise ValueError("A reference date must identify its evidence segment")
        expected = resolved_fields(self.meaning, self.anchor)
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError(
                "Canonical time does not match its declared meaning and anchor"
            )
        return self


def resolved_fields(meaning: TimeMeaning, anchor: str | None) -> dict:
    """Apply only declared calendar operations. Never inspect time expressions."""
    from datetime import timedelta
    from mycelium.temporal import parse_source_datetime

    empty = dict(
        start=None, end=None, precision=None, status="unresolved", resolution_error=None
    )
    if isinstance(meaning, UnresolvedTime):
        return empty
    if isinstance(meaning, RecurringTime):
        return {**empty, "status": "recurring"}
    if isinstance(meaning, AbsoluteInterval):
        return dict(
            start=meaning.start,
            end=meaning.end,
            precision=meaning.precision,
            status="resolved",
            resolution_error=None,
        )
    if not anchor:
        return {**empty, "resolution_error": "missing_anchor"}
    parsed = parse_source_datetime(anchor)
    if parsed is None:
        return {**empty, "resolution_error": "invalid_anchor"}
    base = parsed.date()
    try:
        if isinstance(meaning, DayOffset):
            start = end = base + timedelta(days=meaning.days)
            precision = "day"
        elif isinstance(meaning, WeekdayInWeek):
            start = end = base + timedelta(
                days=-base.weekday() + WEEKDAYS.index(meaning.weekday),
                weeks=meaning.week_offset,
            )
            precision = "day"
        elif isinstance(meaning, WeekdayOccurrence):
            offset = (WEEKDAYS.index(meaning.weekday) - base.weekday()) % 7
            if meaning.direction == "next":
                offset = offset or 7
            elif meaning.direction == "previous":
                offset = offset - 7 if offset else -7
            elif meaning.direction == "on_or_before":
                offset = offset - 7 if offset else 0
            start = end = base + timedelta(days=offset)
            precision = "day"
        elif meaning.unit == "week":
            start = (
                base - timedelta(days=base.weekday()) + timedelta(weeks=meaning.offset)
            )
            end = start + timedelta(days=6)
            precision = "week"
        elif meaning.unit == "month":
            year, month_index = divmod(
                base.year * 12 + base.month - 1 + meaning.offset, 12
            )
            month = month_index + 1
            start = date(year, month, 1)
            end = date(year, month, calendar.monthrange(year, month)[1])
            precision = "month"
        else:
            start, end = (
                date(base.year + meaning.offset, 1, 1),
                date(base.year + meaning.offset, 12, 31),
            )
            precision = "year"
    except (ValueError, OverflowError):
        return {**empty, "resolution_error": "calendar_overflow"}
    return dict(
        start=start.isoformat(),
        end=end.isoformat(),
        precision=precision,
        status="resolved",
        resolution_error=None,
    )


def resolve_annotation(
    annotation: TimeAnnotation,
    anchor: str | None,
    anchor_segment_id: str | None,
    *,
    reference_reason: str | None = None,
) -> CanonicalTime:
    return CanonicalTime.model_validate(
        {
            **annotation.model_dump(),
            "anchor": anchor,
            "anchor_segment_id": anchor_segment_id,
            "reference_reason": reference_reason,
            **resolved_fields(annotation.meaning, anchor),
        }
    )
