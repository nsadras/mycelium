"""Rerouting changes bookkeeping, while evidence changes invalidate inference."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from mycelium.config import Config
from mycelium.truth_review import TruthReviewer
from tests.test_decision_cache import client
from tests.test_truth_scope import fixture
from tests.test_truth_staged_references import reference


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["evidence", "role", "identity", "time", "review"])
async def test_rerouting_reuses_truth_decision_but_changed_meaning_does_not(
    tmp_path, change
):
    artifacts, _, placements, entities = fixture(tmp_path)
    llm = client()
    llm.client.chat.return_value = SimpleNamespace(
        message=SimpleNamespace(
            content='{"comparisons":{"P001":{"scope":"same",'
            '"relation":"no_change","reason":"Compatible evidence."}}}'
        ),
        done_reason="stop",
    )
    reviewer = TruthReviewer(llm, artifacts, Config())
    claims = {c.claim_id: c for c in artifacts.list_claims()}
    old = reference("old-ref", "left", entity="person-mara")
    artifacts.save_entity_reference(old)
    prior = reviewer._records(claims)
    await reviewer._compare_pairs([("left", "right")], prior)

    # A successful reroute creates new reference IDs and audit times. Exact
    # duplicate reference meaning and view ownership do not change truth scope.
    fresh = replace(
        old, reference_id="new-ref", dream_run_id="new-build", created_at="2032-01-01"
    )
    presentation = replace(
        fresh, reference_id="owner-ref", role="canonical_owner", entity_id="you"
    )
    staged = {
        "left": [fresh, replace(fresh, reference_id="duplicate-meaning"), presentation]
    }
    rerouted = reviewer._records(claims, staged)
    assert rerouted == prior
    await reviewer._compare_pairs([("left", "right")], rerouted)
    assert llm.client.chat.await_count == 1
    assert llm._call_log[-1]["metadata"]["cache_hit"]

    if change == "evidence":
        source = artifacts.get_source("source-left")
        source.segments[0].content = "A revised source assertion."
        artifacts.save_source(source)
    elif change == "role":
        staged["left"] = [replace(fresh, role="object")]
    elif change == "identity":
        staged["left"] = [replace(fresh, entity_id="person-suri")]
    elif change == "time":
        claims["left"].temporal_status = "historical"
    else:
        artifacts.save_entity_reference(
            replace(
                old,
                reference_id="human-review",
                origin="manual",
                role="identity_subject",
                identity_decision_id="review-1",
            )
        )
    revised = reviewer._records(claims, staged)
    assert revised != rerouted
    await reviewer._compare_pairs([("left", "right")], revised)
    assert llm.client.chat.await_count == 2
