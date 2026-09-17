
from mycelium.config import Config
from collections import Counter
from itertools import combinations
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mycelium.budget import ContextBudgetError
from mycelium.truth_review import TruthReviewer


@pytest.mark.asyncio
@pytest.mark.parametrize("split_requests", [False, True])
async def test_each_unreviewed_pair_is_considered_once_across_all_history(
    monkeypatch, split_requests
):
    records = {f"record-{i:03d}": {"claim_id": f"record-{i:03d}"} for i in range(31)}
    incoming = sorted(records)[::2]
    expected = {
        pair
        for pair in combinations(sorted(records), 2)
        if set(pair).intersection(incoming)
    }
    excluded = set(sorted(expected)[::17])
    observed = Counter()

    async def respond(system, user, schema, **kwargs):
        payload = json.loads(user.split("\n", 1)[1])
        for alias, targets in payload["eligible_candidates"].items():
            left = payload["incoming"][alias]["claim_id"]
            for target in targets:
                right = payload["candidates"][target]["claim_id"]
                observed[tuple(sorted((left, right)))] += 1
        return {
            "decisions": {
                alias: {
                    "candidates": {target: "compare" for target in targets},
                    "reason": "Inspect every supplied pair",
                }
                for alias, targets in payload["eligible_candidates"].items()
            }
        }

    if split_requests:

        def budget(messages, **kwargs):
            payload = json.loads(messages[1]["content"].split("\n", 1)[1])
            if len(payload["incoming"]) * len(payload["candidates"]) > 8:
                raise ContextBudgetError("Exercise request splitting")

        monkeypatch.setattr("mycelium.truth_review.require_request_budget", budget)
    llm = SimpleNamespace(
        context_window_tokens=65536, call_structured=AsyncMock(side_effect=respond)
    )
    reviewer = TruthReviewer(llm, SimpleNamespace(db=object()), Config())
    selected = await reviewer._candidate_pairs(
        incoming, records, excluded_pairs=excluded
    )
    assert selected == expected - excluded
    assert observed == Counter({pair: 1 for pair in expected - excluded})


@pytest.mark.asyncio
async def test_reviewed_and_self_pairs_need_no_candidate_generation():
    llm = SimpleNamespace(context_window_tokens=65536, call_structured=AsyncMock())
    reviewer = TruthReviewer(llm, SimpleNamespace(db=object()), Config())
    records = {cid: {"claim_id": cid} for cid in ["a", "b", "c"]}
    assert (
        await reviewer._candidate_pairs(
            ["a", "c"], records, excluded_pairs=set(combinations(records, 2))
        )
        == set()
    )
    llm.call_structured.assert_not_awaited()
