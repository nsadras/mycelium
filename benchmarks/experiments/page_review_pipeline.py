"""Native reviewed page exclusions through identity, routing and wiki projection."""

import argparse
import asyncio
from dataclasses import asdict

from benchmarks.experiments.page_review_probes import cases
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimPlacement,
    ClaimProvenance,
    ConsolidatedFact,
    EntityRecord,
    EntityResolutionDecision,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation import ClaimRouter, placement_from_route
from mycelium.consolidation_models import ClaimEvidence
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.organization import IdentityReviewService
from mycelium.snapshots import snapshot_store
from mycelium.telemetry import trace_operation


async def run_case(root, definition):
    name, texts, state, kind, subject_id, title = definition
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        memory.llm.trace_path = root / "calls.jsonl"
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        artifacts = memory.artifacts
        source = SourceDocument(
            "source",
            "agent_conversation",
            "source",
            "2031-05-06",
            "2031-05-06",
            ["user"],
            [
                SourceSegment(cid, i, text, "user", "user")
                for i, (cid, text) in enumerate(texts.items())
            ],
        )
        artifacts.save_source(source)
        claims = [
            MemoryClaim(cid, text, [], [ClaimProvenance("source", [cid])], "2031-05-06")
            for cid, text in texts.items()
        ]
        for claim in claims:
            artifacts.save_claim(claim)
        materializer = PageMaterializer(memory.wiki, artifacts, memory.config)
        if state == "materialized":
            artifacts.save_entity(
                EntityRecord(
                    subject_id,
                    kind,
                    title,
                    subject_id,
                    [],
                    "active",
                    "2031-05-06",
                    "2031-05-06",
                )
            )
            for cid in ["C001", "C002"]:
                artifacts.save_placement(
                    ClaimPlacement(
                        cid,
                        subject_id,
                        "overview",
                        [],
                        "placed",
                        "Prior placement",
                        "2031-05-06",
                        "2031-05-06",
                        page_sections={subject_id: "overview"},
                    )
                )
            artifacts.save_consolidated_fact(
                ConsolidatedFact(
                    "prior",
                    " ".join(texts[c] for c in ["C001", "C002"]),
                    ["C001", "C002"],
                    subject_id,
                    "overview",
                    "current",
                    [],
                    "model",
                    0.8,
                    "Prior combined presentation",
                    "2031-05-06",
                    "2031-05-06",
                )
            )
            materializer.regenerate({subject_id})
            snapshot_store(memory.store_path, root / "before_review")
        record = EntityResolutionDecision(
            "review",
            "entity_creation",
            subject_id if state == "materialized" else None,
            kind,
            title,
            ["source"],
            ["C001"],
            ["C001"],
            0.8,
            "Incidental occurrence reviewed by user",
            "review_required",
            "test",
            "2031-05-06",
            proposed_scope="context",
            proposed_page_state="no_page",
        )
        artifacts.save_entity_resolution_decision(record)
        accepted = IdentityReviewService(artifacts).review("review", "approve")
        write(root / "review.json", asdict(accepted))
        subject_id = accepted.entity_id
        with trace_operation("page_review_pipeline_routing", case=name):
            routed = await ClaimRouter(memory.llm, artifacts, memory.config).route(
                [ClaimEvidence(c, source) for c in claims]
            )
        write(root / "routing.json", asdict(routed))
        assert not routed.failures, routed.failures
        for entity in routed.new_entities:
            artifacts.save_entity(entity)
        for decision in routed.entity_decisions:
            artifacts.save_entity_resolution_decision(decision)
        for reference in routed.entity_references:
            artifacts.save_entity_reference(reference)
        placements = [placement_from_route(r) for r in routed.routes]
        selected = {
            p.claim_id: {p.owner_entity_id, *p.page_sections} for p in placements
        }
        assert subject_id not in selected["C001"] and "you" in selected["C001"], (
            selected
        )
        with trace_operation("page_review_pipeline_facts", case=name):
            resolved = await FactResolver(memory.llm, artifacts).resolve(
                placements,
                affected_entity_ids={e.entity_id for e in artifacts.list_entities()},
                incoming_claim_ids={c.claim_id for c in claims},
                dream_run_id="test",
            )
        write(root / "facts.json", asdict(resolved))
        assert not resolved.failures, resolved.failures
        for proposal in resolved.proposals:
            artifacts.save_reconsolidation_proposal(proposal)
        staged = materializer.stage(
            routed.routes,
            routed.new_entities,
            resolved.facts,
            resolved.deleted_fact_ids,
            resolved.placements,
        )
        materializer.persist(staged)
        snapshot_store(memory.store_path, root / "after_review")
        pages = {page.entity_id: page for page in memory.wiki.list_all()}
        target_page = pages.get(subject_id)
        if target_page:
            assert all(
                "C001" not in item.get("claim_ids", [])
                for section in target_page.sections
                for item in section["items"]
            )
        if name in {"independent_project_support", "existing_page"}:
            assert target_page is not None, pages.keys()
            assert any(
                "C002" in item.get("claim_ids", [])
                for section in target_page.sections
                for item in section["items"]
            )
        if name == "only_reviewed_support":
            assert target_page is None, target_page
        assert (
            subject_id == artifacts.get_entity_resolution_decision("review").entity_id
        )
        return {
            "page_entity_id": subject_id,
            "page_exists": target_page is not None,
            "selected": {cid: sorted(ids - {None}) for cid, ids in selected.items()},
        }


async def main(args):
    root = fresh_run_root("page-review-pipeline")
    print("OUTPUT", root, flush=True)
    results = []
    for trial in range(args.trials):
        for definition in cases():
            if definition[0] == "independent_support":
                continue
            record = {"trial": trial, "case": definition[0]}
            try:
                record.update(
                    await run_case(root / f"{trial}-{definition[0]}", definition),
                    passed=True,
                )
            except Exception as exc:
                record.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            results.append(record)
            write(root / "results.json", results)
            print(record, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in results), "total": len(results)},
    )
    if not all(r["passed"] for r in results):
        raise SystemExit("Native page review acceptance failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    asyncio.run(main(parser.parse_args()))
