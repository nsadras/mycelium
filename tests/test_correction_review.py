from copy import deepcopy
from datetime import datetime

import pytest

from mycelium.artifacts import ClaimProvenance
from mycelium.correction_review import CorrectionPreview
from tests.extraction_support import time_details, stored_time
from tests.lifecycle_support import lifecycle_response
from tests.test_claim_lifecycle import setup_service, add_source, add_claim


TEXT = "The user will deliver the sculpture in two days, provided payment arrives tomorrow."


def setup_review(tmp_path, *, timed=True):
    artifacts, wiki, service = setup_service(tmp_path)
    first = add_source(artifacts, "event")
    second = add_source(artifacts, "payment")
    for sid, timestamp in [
        ("event", "2026-06-10T23:55:00-07:00"),
        ("payment", "2026-06-11T08:00:00-07:00"),
    ]:
        source = artifacts.get_source(sid)
        source.segments[0].timestamp = timestamp
        artifacts.save_source(source)
    original = add_claim(
        artifacts,
        "original",
        [ClaimProvenance("event", [first]), ClaimProvenance("payment", [second])],
    )
    original.text = "The user will deliver the sculpture in three days, provided payment arrives tomorrow."
    if timed:
        original.facets = {
            "temporal": [
                stored_time(
                    first,
                    "in three days",
                    {"kind": "day_offset", "days": 3},
                    "2026-06-10T23:55:00-07:00",
                    target="Delivery",
                )["temporal"][0],
                stored_time(
                    second,
                    "tomorrow",
                    {"kind": "day_offset", "days": 1},
                    "2026-06-11T08:00:00-07:00",
                    target="Payment",
                    role="condition_time",
                )["temporal"][0],
            ]
        }
    artifacts.save_claim(original)
    details = time_details(
        "replacement",
        "in two days",
        {"kind": "day_offset", "days": 2},
        target="Delivery",
    )
    details["times"].extend(
        time_details(
            "replacement",
            "tomorrow",
            {"kind": "day_offset", "days": 1},
            target="Payment",
            role="condition_time",
        )["times"]
    )

    def response(system, user, schema, **kwargs):
        value = lifecycle_response(system, user, schema, **kwargs)
        if kwargs.get("debug_label") == "memory-correction":
            value["facets"] = deepcopy(details)
        return value

    service.resolver.llm.call_structured.side_effect = response
    return artifacts, wiki, service, original, first, second


@pytest.mark.asyncio
@pytest.mark.parametrize("timed", [True, False])
async def test_relative_correction_requires_review_and_reuses_metadata(tmp_path, timed):
    artifacts, _, service, original, first, second = setup_review(tmp_path, timed=timed)
    review = await service.correct_claim(original.claim_id, TEXT)
    assert isinstance(review, CorrectionPreview)
    assert artifacts.get_claim(original.claim_id).status == "active"
    assert len(artifacts.list_claims()) == 1
    assert len(artifacts.list_sources()) == 2
    calls = service.resolver.llm.call_structured.call_count
    assert await service.correct_claim(original.claim_id, TEXT) == review
    assert service.resolver.llm.call_structured.call_count == calls
    prefix = "T" if timed else "E"
    choices = {"0": prefix + "001", "1": prefix + "002"}
    result = await service.correct_claim(
        original.claim_id, TEXT, draft_id=review.draft_id, time_references=choices
    )
    replacement = artifacts.get_claim(result.claim_ids[0])
    assert [t["start"] for t in replacement.facets["temporal"]] == [
        "2026-06-12",
        "2026-06-12",
    ]
    assert [t["anchor_segment_id"] for t in replacement.facets["temporal"]] == [
        first,
        second,
    ]
    assert all(
        t["reference_reason"].startswith("User selected")
        for t in replacement.facets["temporal"]
    )
    assert {p.source_id for p in replacement.provenance} == {
        "event",
        "payment",
        result.source_ids[0],
    }
    metadata_calls = [
        c
        for c in service.resolver.llm.call_structured.call_args_list
        if c.kwargs.get("debug_label") == "memory-correction"
    ]
    assert len(metadata_calls) == 1
    service.resolver.llm.call_structured.reset_mock()
    assert (
        await service.correct_claim(
            original.claim_id, TEXT, draft_id=review.draft_id, time_references=choices
        )
        == result
    )
    assert await service.correct_claim(original.claim_id, TEXT) == result
    service.resolver.llm.call_structured.assert_not_called()


@pytest.mark.asyncio
async def test_review_retains_independent_dates_across_successive_corrections(tmp_path):
    artifacts, _, service, original, first, second = setup_review(tmp_path)
    current = original
    for _ in range(2):
        review = await service.correct_claim(current.claim_id, TEXT)
        result = await service.correct_claim(
            current.claim_id,
            TEXT,
            draft_id=review.draft_id,
            time_references={"0": "T001", "1": "T002"},
        )
        current = artifacts.get_claim(result.claim_ids[0])
        assert [t["anchor_segment_id"] for t in current.facets["temporal"]] == [
            first,
            second,
        ]
        assert [t["start"] for t in current.facets["temporal"]] == [
            "2026-06-12",
            "2026-06-12",
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "choices",
    [
        None,
        {},
        {"0": "T001"},
        {"0": "unknown", "1": "T002"},
        {"0": "T001", "1": "T002", "2": "submission"},
    ],
)
async def test_review_rejects_missing_extra_or_unknown_choices(tmp_path, choices):
    artifacts, _, service, original, _, _ = setup_review(tmp_path)
    review = await service.correct_claim(original.claim_id, TEXT)
    with pytest.raises(ValueError, match="reference"):
        await service.correct_claim(
            original.claim_id, TEXT, draft_id=review.draft_id, time_references=choices
        )
    assert artifacts.get_claim(original.claim_id).status == "active"
    assert len(artifacts.list_claims()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["claim", "source"])
async def test_stale_review_is_rejected_and_prepare_can_refresh_it(tmp_path, change):
    artifacts, _, service, original, _, _ = setup_review(tmp_path)
    review = await service.correct_claim(original.claim_id, TEXT)
    if change == "claim":
        original.text += " The statement is uncertain."
        artifacts.save_claim(original)
    else:
        source = artifacts.get_source("event")
        source.segments[0].timestamp = "2026-06-12T08:00:00-07:00"
        artifacts.save_source(source)
    with pytest.raises(ValueError, match="Memory changed"):
        await service.correct_claim(
            original.claim_id,
            TEXT,
            draft_id=review.draft_id,
            time_references={"0": "T001", "1": "T002"},
        )
    refreshed = await service.correct_claim(original.claim_id, TEXT)
    assert refreshed.draft_id != review.draft_id
    assert artifacts.get_claim(original.claim_id).status == "active"


@pytest.mark.asyncio
async def test_review_can_leave_dates_unresolved_or_use_submission(tmp_path):
    artifacts, _, service, original, _, _ = setup_review(tmp_path)
    review = await service.correct_claim(original.claim_id, TEXT)
    expected = next(
        option
        for option in review.times[0]["options"]
        if option["reference_id"] == "submission"
    )
    result = await service.correct_claim(
        original.claim_id,
        TEXT,
        draft_id=review.draft_id,
        time_references={"0": "submission", "1": "unresolved"},
    )
    replacement = artifacts.get_claim(result.claim_ids[0])
    event, condition = replacement.facets["temporal"]
    assert event["start"] == expected["start"]
    assert event["anchor_segment_id"] == event["evidence_segment_id"]
    assert condition["status"] == "unresolved" and condition["start"] is None
    assert condition["anchor_segment_id"] is None


@pytest.mark.asyncio
async def test_reviewed_submission_date_survives_midnight_before_apply(
    tmp_path, monkeypatch
):
    from mycelium import claim_lifecycle

    class Clock(datetime):
        current = datetime.fromisoformat("2026-06-10T23:59:00-07:00")

        @classmethod
        def now(cls):
            return cls.current

    monkeypatch.setattr(claim_lifecycle, "datetime", Clock)
    artifacts, _, service, original, _, _ = setup_review(tmp_path)
    review = await service.correct_claim(original.claim_id, TEXT)
    expected = next(
        option
        for option in review.times[0]["options"]
        if option["reference_id"] == "submission"
    )
    Clock.current = datetime.fromisoformat("2026-06-11T00:01:00-07:00")
    result = await service.correct_claim(
        original.claim_id,
        TEXT,
        draft_id=review.draft_id,
        time_references={"0": "submission", "1": "submission"},
    )
    replacement = artifacts.get_claim(result.claim_ids[0])
    source = artifacts.get_source(result.source_ids[0])
    assert replacement.facets["temporal"][0]["start"] == expected["start"]
    assert source.occurred_at == expected["anchor"]
    assert source.segments[0].timestamp == expected["anchor"]
    assert source.recorded_at == Clock.current.astimezone().isoformat()
    assert source.recorded_at != source.occurred_at


@pytest.mark.asyncio
async def test_review_is_bound_to_the_replacement_text(tmp_path):
    artifacts, _, service, original, _, _ = setup_review(tmp_path)
    review = await service.correct_claim(original.claim_id, TEXT)
    with pytest.raises(ValueError, match="replacement changed"):
        await service.correct_claim(
            original.claim_id,
            "A different replacement",
            draft_id=review.draft_id,
            time_references={"0": "T001", "1": "T002"},
        )
    assert artifacts.get_claim(original.claim_id).status == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize('meaning,expected', [
    ({'kind': 'weekday_occurrence', 'weekday': 'monday', 'direction': 'next'}, '2026-06-15'),
    ({'kind': 'weekday_in_week', 'weekday': 'monday', 'week_offset': 1}, '2026-06-15'),
])
async def test_weekday_correction_waits_for_exact_reference_choice(tmp_path, meaning, expected):
    artifacts, _, service, original, first, _ = setup_review(tmp_path)
    details = time_details('replacement', 'next Monday', meaning, target='Delivery')
    def response(system, user, schema, **kwargs):
        result = lifecycle_response(system, user, schema, **kwargs)
        if kwargs.get('debug_label') == 'memory-correction':
            result['facets'] = details
        return result
    service.resolver.llm.call_structured.side_effect = response
    text = 'The user will deliver the sculpture next Monday.'
    review = await service.correct_claim(original.claim_id, text)
    assert isinstance(review, CorrectionPreview)
    assert len(artifacts.list_claims()) == 1
    assert artifacts.get_claim(original.claim_id).status == 'active'
    choice = next(row for row in review.times[0]['options'] if row['reference_id'] == 'T001')
    assert choice['start'] == expected
    result = await service.correct_claim(original.claim_id, text, draft_id=review.draft_id, time_references={'0': 'T001'})
    stored = artifacts.get_claim(result.claim_ids[0]).facets['temporal'][0]
    assert stored['start'] == expected and stored['anchor_segment_id'] == first
    assert stored['reference_reason'] == 'User selected the stored reference date'
    calls = service.resolver.llm.call_structured.call_count
    assert await service.correct_claim(original.claim_id, text, draft_id=review.draft_id, time_references={'0': 'T001'}) == result
    assert service.resolver.llm.call_structured.call_count == calls
