"""Checkpoint scoring consumes the same grouped proposals as production snapshots."""

from dataclasses import asdict, replace

import pytest

from benchmarks.suites.daily_driver import eval as daily_eval
from mycelium.artifacts import ReconsolidationProposal


@pytest.fixture
def checkpoint_review(monkeypatch):
    pairs = {
        "gold-new-a": "new-a",
        "gold-new-b": "new-b",
        "gold-old-a": "old-a",
        "gold-old-b": "old-b",
        "gold-other": "other",
    }
    match = {
        "claim_rows": [
            {"gold_claim_id": gold, "generated_claim_id": generated}
            for gold, generated in pairs.items()
        ],
        "fact_rows": [],
        "entity_map": {},
    }
    monkeypatch.setattr(daily_eval, "match_snapshot", lambda *_: match)
    proposal = ReconsolidationProposal(
        proposal_id="review",
        incoming_claim_ids=["new-a", "new-b"],
        target_claim_ids=["old-a", "old-b"],
        proposed_relation="supersedes",
        explanation="The new evidence replaces the earlier schedule.",
        confidence=1.0,
        dream_run_id="build",
        created_at="2031-05-06T00:00:00Z",
        affected_entity_ids=[],
    )
    gold = {
        "id": "review-checkpoint",
        "needs_review": list(pairs)[:-1],
        "reconciliation": [
            {
                "id": "first-pair",
                "incoming_claim": "gold-new-a",
                "target_claim": "gold-old-a",
                "relation": "supersedes",
                "status": "pending",
            },
            {
                "id": "last-pair",
                "incoming_claim": "gold-new-b",
                "target_claim": "gold-old-b",
                "relation": "supersedes",
                "status": "pending",
            },
        ],
    }

    def evaluate(proposals, checkpoint=None):
        fixture = {"gold_checkpoints": {"checkpoints": [checkpoint or gold]}}
        snapshot = {"reconsolidation_proposals": [asdict(p) for p in proposals]}
        return daily_eval._checkpoint_results(fixture, {gold["id"]: snapshot})[0]

    return proposal, gold, match, evaluate


def test_grouped_review_covers_each_incoming_and_target_member(checkpoint_review):
    proposal, _, _, evaluate = checkpoint_review
    result = evaluate([proposal])
    assert result["passed"]
    assert result["checks_total"] == 6
    assert result["checks_passed"] == 6


@pytest.mark.parametrize(
    "change",
    [
        {"incoming_claim_ids": ["other"]},
        {"target_claim_ids": ["other"]},
        {"proposed_relation": "contradicts"},
        {"status": "applied"},
    ],
)
def test_review_pair_requires_matching_members_relation_and_status(
    checkpoint_review, change
):
    proposal, _, _, evaluate = checkpoint_review
    result = evaluate([replace(proposal, **change)])
    assert not result["passed"]
    assert all(
        not row["passed"] for row in result["checks"] if row["kind"] == "reconciliation"
    )


def test_unrelated_claim_and_applied_review_are_not_pending(checkpoint_review):
    proposal, gold, _, evaluate = checkpoint_review
    result = evaluate([proposal], {**gold, "needs_review": ["gold-other"]})
    assert not next(row for row in result["checks"] if row["kind"] == "needs_review")[
        "passed"
    ]
    result = evaluate([replace(proposal, status="applied")])
    assert all(
        not row["passed"] for row in result["checks"] if row["kind"] == "needs_review"
    )


def test_unmatched_claims_cannot_match_a_review(checkpoint_review):
    proposal, _, match, evaluate = checkpoint_review
    for row in match["claim_rows"]:
        row["generated_claim_id"] = None
    for proposals in [[], [proposal]]:
        assert evaluate(proposals)["checks_passed"] == 0


def test_duplicate_matching_reviews_are_reported_as_ambiguous(checkpoint_review):
    proposal, _, _, evaluate = checkpoint_review
    result = evaluate([proposal, replace(proposal, proposal_id="duplicate")])
    checks = [row for row in result["checks"] if row["kind"] == "reconciliation"]
    assert not result["passed"]
    assert all(not row["passed"] and len(row["actual"]) == 2 for row in checks)
