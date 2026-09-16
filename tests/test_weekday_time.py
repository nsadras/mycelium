from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from mycelium.temporal_contract import CanonicalTime, resolve_annotation
from tests.test_temporal_contract import annotation


@pytest.mark.parametrize(
    "direction", ["next", "previous", "on_or_after", "on_or_before"]
)
def test_declared_weekday_is_nearest_day_in_the_declared_direction(direction):
    names = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )
    for base in [date(2024, 2, 28), date(2026, 12, 31), date(2031, 5, 11)]:
        for weekday, name in enumerate(names):
            result = resolve_annotation(
                annotation(
                    {
                        "kind": "weekday_occurrence",
                        "weekday": name,
                        "direction": direction,
                    }
                ),
                base.isoformat(),
                "s1",
            )
            day = date.fromisoformat(result.start)
            assert day.weekday() == weekday
            offset = (day - base).days
            if direction == "next":
                assert 1 <= offset <= 7
            elif direction == "previous":
                assert -7 <= offset <= -1
            elif direction == "on_or_after":
                assert 0 <= offset <= 6
            else:
                assert -6 <= offset <= 0
            assert result.start == result.end and result.precision == "day"
            assert CanonicalTime.model_validate(result.model_dump()) == result


@pytest.mark.parametrize("offset", [-2, 0, 1])
def test_weekday_in_calendar_week_handles_year_boundary(offset):
    base = date(2031, 1, 1)
    result = resolve_annotation(
        annotation(
            {"kind": "weekday_in_week", "weekday": "tuesday", "week_offset": offset}
        ),
        base.isoformat(),
        "s1",
    )
    day = date.fromisoformat(result.start)
    assert day.weekday() == 1
    assert day.isocalendar()[:2] == (base + timedelta(weeks=offset)).isocalendar()[:2]


@pytest.mark.parametrize(
    "meaning",
    [
        {"kind": "weekday_occurrence", "weekday": "friday", "direction": "next"},
        {"kind": "weekday_in_week", "weekday": "friday", "week_offset": 1},
    ],
)
def test_relative_weekdays_require_anchors_and_do_not_resolve_from_expression(meaning):
    unknown = resolve_annotation(
        annotation(meaning, expression="2031-01-01"), None, "s1"
    )
    assert unknown.status == "unresolved" and unknown.start is None
    assert unknown.resolution_error == "missing_anchor"
    invalid = resolve_annotation(annotation(meaning), "invalid", "s1")
    assert invalid.resolution_error == "invalid_anchor"
    overflow = resolve_annotation(annotation(meaning), "9999-12-31", "s1")
    assert overflow.resolution_error == "calendar_overflow"
    valid = resolve_annotation(annotation(meaning), "2031-05-06", "s1").model_dump()
    with pytest.raises(ValidationError, match="declared meaning"):
        CanonicalTime.model_validate({**valid, "start": "2031-05-01"})


def test_weekday_contract_rejects_invalid_declared_values():
    for meaning in [
        {"kind": "weekday_occurrence", "weekday": "invented", "direction": "next"},
        {"kind": "weekday_occurrence", "weekday": "friday", "direction": "sometime"},
        {"kind": "weekday_in_week", "weekday": "friday", "week_offset": True},
        {"kind": "weekday_in_week", "weekday": "friday", "week_offset": 1.5},
    ]:
        with pytest.raises(ValidationError):
            annotation(meaning)


def test_recurring_schedule_preserves_pattern_without_inventing_a_date():
    for anchor in [None, "2031-05-06", "invalid"]:
        result = resolve_annotation(
            annotation({"kind": "recurring"}, expression="every Thursday"), anchor, "s1"
        )
        assert result.status == "recurring"
        assert (
            result.start
            is result.end
            is result.precision
            is result.resolution_error
            is None
        )
        assert result.expression == "every Thursday"
        with pytest.raises(ValidationError, match="declared meaning"):
            CanonicalTime.model_validate({**result.model_dump(), "status": "resolved"})
