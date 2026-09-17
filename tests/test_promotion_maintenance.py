"""Exact dependency scope and durable failure accounting during page promotion."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from benchmarks.shared.adapters import MyceliumMemorySystem
from mycelium.artifacts import ClaimEntityReference, ClaimPlacement, ConsolidatedFact
from mycelium.consolidation_models import ClaimRoute, RoutingFailure, RoutingResult
from mycelium.dream_policy import DreamPolicy
from mycelium.facts import FactResolutionFailure, FactResolutionResult
from tests.test_dream import add_claim, add_source, build_dream


def route(claim, source, entity_id=None, *, described=()):
    return ClaimRoute(
        claim.claim_id,
        entity_id,
        "current_context" if entity_id else None,
        (),
        source.raw_log_entry_id,
        "Explicit model decision for the test.",
        disposition="canonical" if entity_id else "deferred",
        described_entity_ids=described,
        page_sections={entity_id: "current_context"} if entity_id else {},
    )


def test_partial_revision_retains_failures_outside_its_scope():
    outstanding = RoutingFailure("unrelated", "source", "Invalid first response")
    resolved = RoutingFailure("resolved", "source", "Earlier attempt")
    repeated = RoutingFailure("repeated", "source", "Earlier attempt")
    latest = RoutingFailure("repeated", "source", "Latest failed attempt")
    success = ClaimRoute(
        "resolved", None, None, (), "source", "Resolved", disposition="deferred"
    )
    result = DreamPolicy.merge_revision_routing(
        RoutingResult(failures=[outstanding, resolved, repeated]),
        RoutingResult(routes=[success], failures=[latest]),
    )
    assert result.failures == [outstanding, latest]


@pytest.mark.asyncio
async def test_within_build_promotion_revisits_only_missing_page(tmp_path):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    early, later, unrelated = [
        add_claim(artifacts, source, claim_id=cid)
        for cid in ("early", "later", "unrelated")
    ]
    entity = artifacts.create_entity(
        "person", "Rae", materialization_state="provisional"
    )
    promoted = replace(entity, materialization_state="materialized")
    initial = RoutingResult(
        routes=[
            route(early, source, described=(entity.entity_id,)),
            route(later, source, entity.entity_id, described=(entity.entity_id,)),
            route(unrelated, source, "you"),
        ],
        new_entities=[promoted],
    )
    dream.router.route = AsyncMock(
        side_effect=[
            initial,
            RoutingResult(routes=[route(early, source, entity.entity_id)]),
        ]
    )
    dream.fact_resolver.resolve = AsyncMock(return_value=FactResolutionResult())

    report = await dream.run()

    assert report.failures == []
    assert dream.router.route.await_count == 2
    assert [item.claim.claim_id for item in dream.router.route.await_args.args[0]] == [
        "early"
    ]
    assert artifacts.placement_for_claim("early").owner_entity_id == entity.entity_id
    assert artifacts.placement_for_claim("later").owner_entity_id == entity.entity_id
    assert artifacts.placement_for_claim("unrelated").owner_entity_id == "you"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", ["routing", "fact_resolution"])
async def test_failed_old_dependency_remains_visible_retryable_and_published(
    tmp_path, failed_stage
):
    dream, _, wiki, logs, artifacts = build_dream(tmp_path, llm_response={})
    entry, old_source = add_source(logs, artifacts, suffix="old")
    old = add_claim(
        artifacts, old_source, claim_id="old", text="Rae prefers a quiet workspace."
    )
    artifacts.save_claim(replace(old, dream_disposition="routed"))
    old_placement = ClaimPlacement(
        old.claim_id,
        "you",
        "current_context",
        [],
        "placed",
        "Prior view",
        "now",
        "now",
        page_sections={"you": "current_context"},
    )
    artifacts.save_placement(old_placement)
    old_fact = ConsolidatedFact(
        "prior-fact",
        old.text,
        [old.claim_id],
        "you",
        "current_context",
        "current",
        [],
        "claim",
        0.9,
        "Prior source-backed view",
        "now",
        "now",
    )
    artifacts.save_consolidated_fact(old_fact)
    entity = artifacts.create_entity(
        "person", "Rae", materialization_state="provisional"
    )
    artifacts.save_entity_reference(
        ClaimEntityReference(
            "prior-reference",
            old.claim_id,
            "subject",
            None,
            entity.entity_id,
            0.9,
            "Source-established subject",
            "scope",
            "prior-build",
            "active",
            "now",
        )
    )
    dream.materializer.regenerate({"you"})
    logs.mark_consolidated([entry.entry_id])
    fresh_entry, source = add_source(logs, artifacts, suffix="fresh")
    fresh = add_claim(artifacts, source, claim_id="fresh")
    promoted = replace(entity, materialization_state="materialized")
    initial = RoutingResult(
        routes=[route(fresh, source, entity.entity_id, described=(entity.entity_id,))],
        new_entities=[promoted],
    )
    failure = RoutingFailure(
        old.claim_id, entry.entry_id, "Rejected maintenance output"
    )
    dream.router.route = AsyncMock(
        side_effect=[initial, RoutingResult(failures=[failure])]
    )
    dream.fact_resolver.resolve = AsyncMock(return_value=FactResolutionResult())
    if failed_stage == "fact_resolution":
        dream.router.route.side_effect = [
            initial,
            RoutingResult(routes=[route(old, old_source, "you")]),
        ]
        dream.fact_resolver.resolve.return_value = FactResolutionResult(
            failures=[
                FactResolutionFailure(
                    "you",
                    [old.claim_id],
                    [entry.entry_id],
                    failure.reason,
                    partial=True,
                ),
            ]
        )

    report = await dream.run()

    assert report.failures == [
        {
            "stage": failed_stage,
            "source_id": entry.entry_id if failed_stage == "routing" else "you",
            "reason": failure.reason,
        }
    ]
    assert [item.claim.claim_id for item in dream.router.route.await_args.args[0]] == [
        old.claim_id
    ]
    assert artifacts.get_claim(old.claim_id).dream_disposition == "routing_failed"
    assert artifacts.placement_for_claim(old.claim_id) == old_placement
    assert artifacts.list_consolidated_facts() == [old_fact]
    assert old.text in wiki.get("you").content
    assert artifacts.memory_tier(old.claim_id) == "canonical"
    assert logs.get(fresh_entry.entry_id).consolidated
    assert dream.short_term.status().retryable_failures == 1
    assert [
        c.claim_id for c in dream.prepare(include_deferred=False).queued_claims
    ] == [old.claim_id]
    benchmark = MyceliumMemorySystem(
        run_dir=tmp_path / "benchmark",
        qa_client=object(),
        memory_model="test",
        ollama_url="http://localhost:11434",
    )
    benchmark.mem = SimpleNamespace(
        wiki=wiki,
        log_store=logs,
        artifacts=artifacts,
        db=artifacts.db,
        consolidation_status=dream.short_term.status,
    )
    assert benchmark.stats()["encoding_status"] == "incomplete"

    # The existing retry queue clears the failure after a successful next build.
    dream.router.route = AsyncMock(
        return_value=RoutingResult(
            routes=[route(old, old_source, "you")],
        )
    )
    dream.fact_resolver.resolve.return_value = FactResolutionResult()
    retry = await dream.run()
    assert retry.failures == []
    assert artifacts.get_claim(old.claim_id).dream_disposition == "routed"
    assert dream.short_term.status().retryable_failures == 0
    assert benchmark.stats()["encoding_status"] == "complete"
    assert old.text in wiki.get("you").content
