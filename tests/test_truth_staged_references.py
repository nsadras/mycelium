from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from mycelium.artifacts import ClaimEntityReference
from tests.test_truth_record_reads import setup


def reference(rid, cid="c0", *, origin="scope", entity="old"):
    return ClaimEntityReference(
        rid,
        cid,
        "subject",
        None,
        entity,
        0.9,
        "Grounded identity",
        origin,
        "build",
        "active",
        "2031-05-03",
    )


def test_staged_bindings_replace_exact_scope_keep_manual_reviews_and_do_not_write():
    reviewer, claims, _, _ = setup(2)
    old = reference("old")
    reviewed = reference("reviewed", origin="manual", entity="reviewed-person")
    other = reference("other", "c1")
    stored = {"c0": [old, reviewed], "c1": [other]}
    reviewer.artifacts.list_entity_references = lambda claim_id, **_: stored[claim_id]
    fresh = reference("fresh", entity="new")
    prepared = reviewer._records(claims, {}, {}, {"c0": [fresh]})
    assert [r["reference_id"] for r in prepared["c0"]["identity_bindings"]] == [
        "reviewed",
        "fresh",
    ]
    assert prepared["c1"]["identity_bindings"][0]["reference_id"] == "other"
    empty = reviewer._records(claims, {}, {}, {"c0": []})
    assert [r["reference_id"] for r in empty["c0"]["identity_bindings"]] == ["reviewed"]
    persisted = reviewer._records(claims, {}, {})
    assert [r["reference_id"] for r in persisted["c0"]["identity_bindings"]] == [
        "old",
        "reviewed",
    ]
    assert all(r.status == "active" for refs in stored.values() for r in refs)


@pytest.mark.parametrize(
    "refs",
    [
        [reference("wrong", "c1")],
        [reference("manual", origin="manual")],
        [reference("duplicate"), reference("duplicate")],
        [
            replace(
                reference("inactive"), status="retired", retired_by_dream_run_id="later"
            )
        ],
    ],
)
def test_staged_bindings_reject_invalid_scope_or_state(refs):
    reviewer, claims, _, _ = setup(2)
    with pytest.raises(ValueError, match="Staged truth bindings"):
        reviewer._records(claims, {}, {}, {"c0": refs})


@pytest.mark.asyncio
async def test_bindings_from_another_build_fail_before_model_comparison():
    reviewer, claims, _, _ = setup(2)
    reviewer.artifacts.list_claims = lambda **_: list(claims.values())
    reviewer.llm = AsyncMock()
    result = await reviewer.review(
        {"c0"},
        {},
        {},
        dream_run_id="different",
        reference_replacements={"c0": [reference("fresh")]},
    )
    assert result.failure_claim_ids == {"c0"}
    assert "current build" in result.errors[0]
    reviewer.llm.call_structured.assert_not_awaited()
