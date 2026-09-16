from copy import deepcopy

import pytest
from pydantic import ValidationError

from mycelium.temporal_contract import TimeAnnotation, CanonicalTime, resolve_annotation


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


def test_pipeline_retains_multiple_targets_with_independent_cited_anchors(tmp_path):
    from mycelium import Mycelium
    from mycelium.artifacts import SourceDocument, SourceSegment
    from mycelium.claim_index import ClaimSearchHit
    from mycelium.retrieval_context import (
        RetrievedContextBuilder,
        render_memory_evidence,
    )
    from tests.extraction_support import time_details

    old = SourceDocument(
        "s-old",
        "agent_conversation",
        "session",
        "2026-08-31",
        "2026-08-31",
        [],
        [
            SourceSegment(
                "old",
                0,
                "The delivery is in three days.",
                timestamp="2026-06-10T23:55:00-07:00",
            )
        ],
    )
    new = SourceDocument(
        "s-new",
        "agent_conversation",
        "session",
        "2026-08-31",
        "2026-08-31",
        [],
        [
            SourceSegment(
                "new",
                0,
                "Yes, provided payment arrives tomorrow.",
                timestamp="2026-06-11T08:00:00-07:00",
            )
        ],
    )
    event = time_details(
        "old",
        "in three days",
        {"kind": "day_offset", "days": 3},
        target="Niko delivers the sculpture",
    )
    condition = time_details(
        "new",
        "tomorrow",
        {"kind": "day_offset", "days": 1},
        role="condition_time",
        target="Payment arrives",
    )
    event["times"].extend(condition["times"])
    raw = {
        "claims": [
            {
                "text": "Niko will deliver the sculpture in three days, provided payment arrives tomorrow.",
                "segment_ids": ["new"],
                "context_segment_ids": ["old"],
                "about": [{"entity": "Niko", "role": "subject"}],
                "facets": event,
                "claim_type": "commitment",
                "evidence_modality": "speech",
                "temporal_status": "future",
            }
        ]
    }
    with Mycelium(tmp_path, memory_profile="none") as mem:
        mem.artifacts.save_source(old)
        mem.artifacts.save_source(new)
        claim = mem.encoder._build_extracted_claims(
            new, raw, "batch", context_sources=[old]
        )[0]
        mem.artifacts.save_claim(claim)
        times = mem.artifacts.get_claim(claim.claim_id).facets["temporal"]
        assert [(t["role"], t["start"], t["evidence_segment_id"]) for t in times] == [
            ("event_time", "2026-06-13", "old"),
            ("condition_time", "2026-06-12", "new"),
        ]
        hit = ClaimSearchHit(
            claim.claim_id, claim.text, "short_term", None, None, None, None, None
        )
        evidence = RetrievedContextBuilder(mem.wiki, mem.artifacts).build(
            [hit], budget_tokens=3000
        )
        assert len(evidence.records[0].temporal) == 2
        context = render_memory_evidence(evidence)
        assert "Niko delivers the sculpture" in context
        assert "Payment arrives" in context
        assert "2026-06-13" in context and "2026-06-12" in context


def test_time_schema_requires_exact_cited_evidence_for_every_annotation():
    from mycelium.structured_outputs import extraction_output_model
    from tests.extraction_support import extraction_response, time_details

    schema = extraction_output_model(["new"], ["old"])
    claim = {
        "text": "A declaration.",
        "about": [{"entity": "Niko", "role": "subject"}],
        "segment_ids": ["new"],
        "context_segment_ids": [],
        "claim_type": "event",
        "temporal_status": "future",
        "evidence_modality": "speech",
        "facets": time_details("old", "in two days", {"kind": "day_offset", "days": 2}),
    }
    with pytest.raises(ValidationError, match="cited evidence"):
        schema.model_validate(extraction_response([claim]))
    claim["context_segment_ids"] = ["old"]
    assert schema.model_validate(extraction_response([claim]))
    del claim["facets"]["times"][0]["evidence_segment_id"]
    with pytest.raises(ValidationError, match="evidence_segment_id"):
        schema.model_validate(extraction_response([claim]))


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
