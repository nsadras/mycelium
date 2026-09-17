"""Structural search bounds; model relevance is covered by native experiments."""

from collections import Counter
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mycelium.config import Config
from mycelium.truth_review import TruthReviewer


@pytest.mark.asyncio
@pytest.mark.parametrize("history_count", [100, 1000, 10000])
async def test_truth_model_work_stays_bounded_and_preserves_asymmetric_batch_hits(
    history_count,
):
    incoming = ["new-a", "new-z"]
    records = {
        cid: {
            "claim_id": cid,
            "identity_bindings": [{"entity_id": "shared-subject"}],
        }
        for cid in [*incoming, *(f"old-{i:05d}" for i in range(history_count))]
    }
    observed = Counter()
    domains = []

    async def search(documents, queries, *, limit, eligible_ids):
        cid = json.loads(queries[0])["claim_id"]
        eligible = set(eligible_ids)
        domains.append((cid, limit, eligible))
        # Only the later incoming side retrieves the earlier one. An orientation
        # filter after search would silently drop this same-batch relationship.
        preferred = ["new-a"] if cid == "new-z" else []
        return [
            item
            for item in [*preferred, *sorted(eligible - set(incoming))]
            if item in eligible
        ][:limit]

    async def respond(_system, user, _schema, **_kwargs):
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
                    "reason": "Exercise each eligible comparison.",
                }
                for alias, targets in payload["eligible_candidates"].items()
            }
        }

    llm = SimpleNamespace(
        context_window_tokens=65536, call_structured=AsyncMock(side_effect=respond)
    )
    reviewer = TruthReviewer(llm, SimpleNamespace(db=object()), Config())
    reviewer.candidates = SimpleNamespace(select=AsyncMock(side_effect=search))
    excluded = {("new-a", "old-00000")}
    pairs = await reviewer._candidate_pairs(incoming, records, excluded_pairs=excluded)
    assert ("new-a", "new-z") in pairs
    assert pairs.isdisjoint(excluded)
    assert len(pairs) <= len(incoming) * 48
    assert observed == Counter({pair: 1 for pair in pairs})
    assert len(domains) == 4
    for cid in incoming:
        global_domain, entity_domain = [row for row in domains if row[0] == cid]
        assert global_domain[1] == 32 and entity_domain[1] == 16
        assert cid not in global_domain[2] | entity_domain[2]
    assert "old-00000" not in domains[0][2]


@pytest.mark.asyncio
async def test_unknown_identity_keeps_global_search_route():
    records = {str(i): {"claim_id": str(i), "identity_bindings": []} for i in range(60)}
    reviewer = TruthReviewer(None, SimpleNamespace(db=object()), Config())
    reviewer.candidates = SimpleNamespace(select=AsyncMock(return_value=["59"]))
    pools = await reviewer._candidate_pools(["0"], records, frozenset())
    assert pools == {"0": {"59"}}
    first = reviewer.candidates.select.call_args_list[0]
    assert first.kwargs["eligible_ids"] == records.keys() - {"0"}
