"""Native identity continuity, pending review preservation and unchanged rebuilds."""

import asyncio
from dataclasses import asdict

from benchmarks.experiments.probe_support import fresh_run_root, write
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimProvenance,
    EntityResolutionDecision,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation import placement_from_route
from mycelium.consolidation_models import ClaimEvidence


CASES = [
    (
        "known_unnamed",
        "The traveler",
        "accepted",
        "A traveler at the station repaired a radio on Monday.",
        "That same traveler also explained how the antenna works.",
    ),
    (
        "pending_sender",
        "Unidentified sender",
        "review_required",
        "An unidentified person sent an offer to help carry the equipment.",
        "That same unidentified sender offered to bring a trolley as well.",
    ),
]


async def main():
    root = fresh_run_root("identity-continuity-pipeline")
    results = []
    for trial in range(3):
        for name, title, state, first, second in CASES:
            memory = Mycelium(
                root / f"{trial}-{name}" / "store", config_path="mycelium.toml"
            )
            memory.llm.trace_path = root / "calls.jsonl"
            write(root / "config.json", asdict(memory.config))
            if not (root / "models.json").exists():
                write(
                    root / "models.json", (await memory.llm.client.list()).model_dump()
                )
            artifacts = memory.artifacts
            entity = artifacts.create_entity(
                "person", title, materialization_state="provisional"
            )
            source = SourceDocument(
                "source",
                "agent_conversation",
                "source",
                "2031-01-01",
                None,
                [],
                [SourceSegment("S1", 0, first), SourceSegment("S2", 1, second)],
            )
            artifacts.save_source(source)
            claims = [
                MemoryClaim(
                    f"claim-{i}",
                    text,
                    [],
                    [ClaimProvenance("source", [f"S{i}"])],
                    "2031-01-01",
                )
                for i, text in enumerate([first, second], 1)
            ]
            for claim in claims:
                artifacts.save_claim(claim)
            artifacts.save_entity_resolution_decision(
                EntityResolutionDecision(
                    "initial",
                    "entity_creation",
                    entity.entity_id,
                    "person",
                    entity.title,
                    ["source"],
                    ["claim-1"],
                    ["S1"],
                    0.9,
                    "Source-established particular person",
                    state,
                    "initial",
                    "2031-01-01",
                    identity_evidence_claim_ids=["claim-1"],
                    proposed_scope="independent",
                    proposed_page_state="provisional",
                )
            )
            builds = []
            for build in range(3):
                before = len(memory.llm._call_log)
                result = await memory.consolidator.router.route(
                    [ClaimEvidence(claims[1], source)]
                )
                calls = list(memory.llm._call_log)[before:]
                new_generations = sum(
                    not row.get("metadata", {}).get("cache_hit", False) for row in calls
                )
                for value in result.new_entities:
                    artifacts.save_entity(value)
                for value in result.entity_decisions:
                    artifacts.save_entity_resolution_decision(value)
                for route in result.routes:
                    artifacts.save_placement(placement_from_route(route))
                plan = artifacts.list_identity_work_units()[0].entity_plan
                person_ids = {
                    value.entity_id
                    for value in result.new_entities
                    if value.entity_type == "person"
                }
                passed = not result.failures and person_ids == {entity.entity_id}
                if state == "review_required":
                    passed = (
                        passed
                        and artifacts.get_entity_resolution_decision(
                            "initial"
                        ).review_state
                        == state
                    )
                    passed = passed and all(
                        "initial" in route.identity_blocker_ids
                        for route in result.routes
                    )
                if build == 2:
                    passed = passed and new_generations == 0
                builds.append(
                    {
                        "build": build,
                        "passed": passed,
                        "new_generations": new_generations,
                        "plan": plan,
                        "result": asdict(result),
                    }
                )
                print(
                    trial,
                    name,
                    build,
                    passed,
                    new_generations,
                    result.failures,
                    flush=True,
                )
            results.append(
                {
                    "trial": trial,
                    "case": name,
                    "passed": all(b["passed"] for b in builds),
                    "builds": builds,
                }
            )
            write(root / "results.json", results)
            memory.close()
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Identity continuity pipeline failed")


if __name__ == "__main__":
    asyncio.run(main())
