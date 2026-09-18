from copy import deepcopy

import pytest
from pydantic import ValidationError

from mycelium.temporal_contract import TimeAnnotation, CanonicalTime, resolve_annotation


def test_calendar_date_syntax_is_exposed_to_structured_decoding():
    from mycelium.structured_outputs import ReplacementMetadata

    schema = ReplacementMetadata.model_json_schema()
    absolute = schema["$defs"]["AbsoluteInterval"]["properties"]
    for key in ("start", "end"):
        assert absolute[key]["pattern"] == r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
    with pytest.raises(ValidationError):
        annotation(
            {
                "kind": "absolute",
                "start": "2031-05-10T15:00:00",
                "end": "2031-05-10T16:30:00",
                "precision": "range",
            }
        )


def annotation(
    meaning,
    *,
    expression="Source time words",
    role="event_time",
    target="A stated action",
    segment="s1",
):
    return TimeAnnotation(
        expression=expression,
        role=role,
        target=target,
        evidence_segment_id=segment,
        meaning=meaning,
    )


@pytest.mark.parametrize(
    "meaning,anchor,start,end",
    [
        (
            {"kind": "day_offset", "days": 1},
            "2024-02-28T23:55:00-08:00",
            "2024-02-29",
            "2024-02-29",
        ),
        (
            {"kind": "day_offset", "days": -1},
            "2026-01-01T00:01:00+12:00",
            "2025-12-31",
            "2025-12-31",
        ),
        (
            {"kind": "calendar_period", "unit": "month", "offset": 1},
            "2023-12-12",
            "2024-01-01",
            "2024-01-31",
        ),
        (
            {"kind": "calendar_period", "unit": "month", "offset": -1},
            "2024-03-10",
            "2024-02-01",
            "2024-02-29",
        ),
        (
            {"kind": "calendar_period", "unit": "week", "offset": 1},
            "2026-12-31",
            "2027-01-04",
            "2027-01-10",
        ),
        (
            {"kind": "calendar_period", "unit": "year", "offset": -3},
            "2026-06-10",
            "2023-01-01",
            "2023-12-31",
        ),
        (
            {"kind": "calendar_period", "unit": "year", "offset": -250},
            "2026-06-10",
            "1776-01-01",
            "1776-12-31",
        ),
        (
            {"kind": "calendar_period", "unit": "month", "offset": -1200},
            "2026-06-10",
            "1926-06-01",
            "1926-06-30",
        ),
        (
            {"kind": "day_offset", "days": 36601},
            "1900-01-01",
            "2000-03-18",
            "2000-03-18",
        ),
        (
            {
                "kind": "absolute",
                "start": "2031-02-14",
                "end": "2031-02-14",
                "precision": "day",
            },
            None,
            "2031-02-14",
            "2031-02-14",
        ),
    ],
)
def test_declared_calendar_operations(meaning, anchor, start, end):
    resolved = resolve_annotation(annotation(meaning), anchor, "s1")
    assert (resolved.start, resolved.end, resolved.status) == (start, end, "resolved")
    assert CanonicalTime.model_validate(resolved.model_dump()) == resolved


def test_changing_expression_never_changes_numeric_resolution():
    declared = {"kind": "day_offset", "days": 2}
    values = [
        resolve_annotation(annotation(declared, expression=words), "2026-06-10", "s1")
        for words in ("in two days", "hace dos días", "arbitrary evidence wording")
    ]
    assert {value.start for value in values} == {"2026-06-12"}


@pytest.mark.parametrize(
    "words",
    ["a few days", "several weeks", "early next week", "recently", "February 14"],
)
def test_unresolved_declarations_never_gain_invented_bounds(words):
    resolved = resolve_annotation(
        annotation(
            {"kind": "unresolved", "reason": "Ambiguous or imprecise"}, expression=words
        ),
        "2026-06-10",
        "s1",
    )
    assert resolved.status == "unresolved"
    assert resolved.start is None and resolved.end is None


@pytest.mark.parametrize(
    "anchor,error",
    [
        (None, "missing_anchor"),
        ("not a timestamp", "invalid_anchor"),
        ("0001-01-01", "calendar_overflow"),
    ],
)
def test_invalid_or_absent_anchor_remains_explicit(anchor, error):
    resolved = resolve_annotation(
        annotation({"kind": "day_offset", "days": -2}), anchor, "s1"
    )
    assert resolved.resolution_error == error
    assert resolved.status == "unresolved"


def test_canonical_dates_cannot_be_forged_after_normalization():
    resolved = resolve_annotation(
        annotation({"kind": "day_offset", "days": 2}), "2026-06-10", "s1"
    ).model_dump()
    bad = deepcopy(resolved)
    bad["start"] = "2026-07-01"
    with pytest.raises(ValidationError, match="declared meaning"):
        CanonicalTime.model_validate(bad)


def test_huge_declared_offsets_stay_explicitly_unresolved():
    value = resolve_annotation(
        annotation({"kind": "day_offset", "days": 10**50}), "2026-06-10", "s1"
    )
    assert value.start is None and value.resolution_error == "calendar_overflow"


@pytest.mark.parametrize(
    "meaning",
    [
        {
            "kind": "absolute",
            "start": "2031-02-30",
            "end": "2031-02-30",
            "precision": "day",
        },
        {
            "kind": "absolute",
            "start": "2031-03-01",
            "end": "2031-02-28",
            "precision": "range",
        },
        {"kind": "day_offset", "days": True},
        {"kind": "calendar_period", "unit": "fortnight", "offset": 1},
        {"kind": "unresolved", "reason": "", "start": "2031-01-01"},
    ],
)
def test_invalid_time_declarations_fail(meaning):
    with pytest.raises(ValidationError):
        annotation(meaning)


@pytest.mark.parametrize(
    "start,end,precision",
    [
        ("2024-02-01", "2024-02-29", "month"),
        ("2026-12-28", "2027-01-03", "week"),
        ("2024-01-01", "2024-12-31", "year"),
    ],
)
def test_absolute_precision_matches_calendar_boundaries(start, end, precision):
    from datetime import date, timedelta

    meaning = dict(kind="absolute", start=start, end=end, precision=precision)
    assert annotation(meaning).meaning.end == end
    meaning["end"] = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
    with pytest.raises(ValidationError, match="precision requires"):
        annotation(meaning)


def test_time_anchors_preserve_message_dates_and_unknowns():
    from mycelium.artifacts import SourceDocument, SourceSegment
    from mycelium.temporal import source_time_anchors

    dated = SourceDocument(
        "dated",
        "chat",
        "session",
        "2026-08-31",
        "2026-08-31",
        [],
        [
            SourceSegment(
                "known", 0, "A statement", timestamp="2026-06-10T23:55:00-07:00"
            ),
            SourceSegment("unknown", 1, "A reply"),
        ],
    )
    undated = SourceDocument(
        "undated",
        "chat",
        "session",
        "2026-08-31",
        "2026-06-12",
        [],
        [
            SourceSegment("source-date", 0, "A dated conversation"),
        ],
    )
    assert source_time_anchors([dated, undated]) == {
        "known": "2026-06-10T23:55:00-07:00",
        "unknown": None,
        "source-date": "2026-06-12",
    }






def test_schema_two_rejects_old_store_without_changing_database(tmp_path):
    import sqlite3
    from mycelium import Mycelium

    root = tmp_path / "old"
    root.mkdir()
    with sqlite3.connect(root / "memory.sqlite3") as connection:
        connection.execute("PRAGMA user_version=1")
    original_bytes = (root / "memory.sqlite3").read_bytes()
    with pytest.raises(ValueError, match="select a fresh store"):
        Mycelium(root, memory_profile="none")
    assert (root / "memory.sqlite3").read_bytes() == original_bytes
    with sqlite3.connect(root / "memory.sqlite3") as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_fresh_temporal_store_round_trips_through_export(tmp_path):
    import json
    from mycelium import Mycelium
    from mycelium.artifacts import (
        SourceDocument,
        SourceSegment,
        MemoryClaim,
        ClaimProvenance,
    )
    from mycelium.snapshots import export_records, snapshot_store
    from tests.extraction_support import stored_time

    root = tmp_path / "new"
    with Mycelium(root, memory_profile="none") as mem:
        mem.artifacts.save_source(
            SourceDocument(
                "s",
                "agent_conversation",
                "session",
                "2026-06-10",
                "2026-06-10",
                [],
                [SourceSegment("s1", 0, "I will leave in a few days.")],
            )
        )
        mem.artifacts.save_claim(
            MemoryClaim(
                "c",
                "Niko will leave in a few days.",
                [{"entity": "Niko", "role": "subject"}],
                [ClaimProvenance("s", ["s1"])],
                "2026-06-10",
                facets=stored_time(
                    "s1",
                    "a few days",
                    {"kind": "unresolved", "reason": "Imprecise quantity"},
                    "2026-06-10",
                ),
            )
        )
        snapshot_store(root, tmp_path / "snapshot")
        export_records(root, tmp_path / "export")
    record = json.loads((tmp_path / "export" / "claims.jsonl").read_text())["record"]
    assert record["facets"]["temporal"][0]["status"] == "unresolved"
    with Mycelium(tmp_path / "snapshot", memory_profile="none") as copied:
        assert (
            copied.artifacts.get_claim("c").facets["temporal"][0]["expression"]
            == "a few days"
        )
