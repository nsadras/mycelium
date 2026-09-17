"""Publication must commit both sides of a canonical ownership transfer."""

from collections import Counter
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from mycelium.artifacts import ClaimPlacement, ConsolidatedFact
from mycelium.consolidation_models import RoutingResult
from mycelium.facts import FactResolutionResult
from mycelium.truth_review import TruthReviewer, TruthReviewResult
from tests.test_dream import add_claim, add_source, build_dream
from tests.test_promotion_maintenance import route


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_owner", ["a", "b", "c", None])
async def test_transfer_chain_commits_together_and_preserves_independent_work(
    tmp_path, monkeypatch, failed_owner
):
    dream, _, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    entities = {
        key: artifacts.create_entity("person", key, materialization_state="materialized")
        for key in ("a", "b", "c", "independent")
    }
    original_owners = {
        "a-moving": "a", "a-staying": "a",
        "b-moving": "b", "b-staying": "b",
        "c-staying": "c", "independent-old": "independent",
    }
    proposed_owners = {
        **original_owners, "a-moving": "b", "b-moving": "c",
        "independent-new": "independent",
    }
    claims, sources, old_placements, old_facts = {}, {}, {}, {}
    for cid, owner in proposed_owners.items():
        _, sources[cid] = add_source(logs, artifacts, suffix=cid)
        claims[cid] = add_claim(artifacts, sources[cid], claim_id=cid, text=cid)
        if cid not in original_owners:
            continue
        old_owner = entities[original_owners[cid]].entity_id
        old_placements[cid] = ClaimPlacement(
            cid, old_owner, "current_context", [], "placed", "Prior decision",
            "before", "before", page_sections={old_owner: "current_context"},
        )
        artifacts.save_placement(old_placements[cid])
        # Published evidence can still be queued for a failed maintenance retry.
        artifacts.save_claim(replace(claims[cid], dream_disposition="routing_failed"))
    for key, entity in entities.items():
        members = [cid for cid, owner in original_owners.items() if owner == key]
        old_facts[key] = ConsolidatedFact(
            f"prior-{key}", "; ".join(members), members, entity.entity_id,
            "current_context", "current", [], "model", .9, "Prior view",
            "before", "before",
        )
        artifacts.save_consolidated_fact(old_facts[key])
    dream.materializer.regenerate({e.entity_id for e in entities.values()})
    prior_pages = {key: wiki.get(entity.slug) for key, entity in entities.items()}
    dream.router.route = AsyncMock(return_value=RoutingResult(routes=[
        route(claims[cid], sources[cid], entities[owner].entity_id)
        for cid, owner in proposed_owners.items()
    ]))
    monkeypatch.setattr(
        TruthReviewer, "review", AsyncMock(return_value=TruthReviewResult())
    )

    async def grouping_step(owner_id, members, placements, *args, **kwargs):
        if failed_owner and owner_id == entities[failed_owner].entity_id:
            raise ValueError("Injected grouping failure")
        # Supply valid singleton decisions at the model boundary. Exercise the
        # real owner resolver, Build commit, database and page materialization.
        facts, updates = [], []
        owner = artifacts.get_entity(owner_id)
        for claim in members:
            fact, placement = dream.fact_resolver._direct_projection(
                owner, claim, placements[claim.claim_id]
            )
            facts.append(fact)
            updates.append(placement)
        return FactResolutionResult(facts=facts, placements=updates)

    monkeypatch.setattr(dream.fact_resolver, "_resolve_owner_step", grouping_step)
    report = await dream.run()
    facts = artifacts.list_consolidated_facts()
    counts = Counter(cid for fact in facts for cid in fact.member_claim_ids)
    assert counts == Counter({cid: 1 for cid in claims})
    for fact in facts:
        assert all(
            artifacts.placement_for_claim(cid).owner_entity_id == fact.owner_entity_id
            for cid in fact.member_claim_ids
        )
    if failed_owner:
        assert report.failures
        for cid, key in original_owners.items():
            if key == "independent":
                continue
            assert artifacts.placement_for_claim(cid) == old_placements[cid]
            assert artifacts.get_claim(cid).dream_disposition == "routing_failed"
        for key in ("a", "b", "c"):
            assert artifacts.get_consolidated_fact(old_facts[key].fact_id) == old_facts[key]
            assert wiki.get(entities[key].slug).sections == prior_pages[key].sections
    else:
        assert not report.failures
        for cid, key in proposed_owners.items():
            assert artifacts.placement_for_claim(cid).owner_entity_id == entities[key].entity_id
    assert artifacts.get_claim("independent-new").dream_disposition == "routed"
    assert "independent-new" in wiki.get(entities["independent"].slug).content
    if failed_owner:
        failed_owner = None
        queued = {
            item.claim_id
            for item in dream.prepare(include_deferred=False).queued_claims
        }
        assert queued == {cid for cid, owner in original_owners.items() if owner != "independent"}
        dream.router.route.return_value = RoutingResult(routes=[
            route(claims[cid], sources[cid], entities[proposed_owners[cid]].entity_id)
            for cid in sorted(queued)
        ])
        retry = await dream.run()
        assert not retry.failures
        assert dream.short_term.status().retryable_failures == 0
        assert Counter(
            cid for fact in artifacts.list_consolidated_facts()
            for cid in fact.member_claim_ids
        ) == Counter({cid: 1 for cid in claims})
        for cid, owner in proposed_owners.items():
            assert artifacts.placement_for_claim(cid).owner_entity_id == entities[owner].entity_id


@pytest.mark.asyncio
async def test_failed_truth_review_holds_older_ownership_maintenance(tmp_path, monkeypatch):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    old = add_claim(artifacts, source, claim_id="old")
    new = add_claim(artifacts, source, claim_id="new")
    target = artifacts.create_entity("person", "Rae", materialization_state="materialized")
    prior = ClaimPlacement(
        old.claim_id, "you", "current_context", [], "placed", "Prior view",
        "before", "before", page_sections={"you": "current_context"},
    )
    artifacts.save_placement(prior)
    monkeypatch.setattr(TruthReviewer, "review", AsyncMock(return_value=TruthReviewResult(
        failure_claim_ids={new.claim_id}, errors=["Injected failed truth comparison"]
    )))
    result = await dream.fact_resolver.resolve(
        [replace(prior, owner_entity_id=target.entity_id,
                 page_sections={target.entity_id: "current_context"})],
        affected_entity_ids={"you", target.entity_id},
        incoming_claim_ids={new.claim_id}, dream_run_id="test",
    )
    assert {cid for failure in result.failures for cid in failure.claim_ids} == {"old", "new"}
    assert not result.placements and not result.deleted_fact_ids
    assert artifacts.placement_for_claim(old.claim_id) == prior
