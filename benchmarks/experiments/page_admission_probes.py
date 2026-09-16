"""Neutral admission and entity-specific section decisions with the host model."""

import asyncio
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from mycelium.artifacts import EntityRecord
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
    EntityResolutionDecision,
)
from mycelium.consolidation_models import ClaimEvidence
from mycelium.config import Config
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.page_admission import (
    NO_PAGE_BASIS,
    page_admission_model,
    page_admission_prompt,
)
from benchmarks.experiments.attribution_contract_probes import decide


CASES = [
    (
        "project_responsibility",
        {
            "person": ("person", "Rin Patel", "materialized"),
            "project": ("project", "Orchard", "provisional"),
        },
        [
            "Rin Patel leads Orchard, an ongoing toolchain upgrade with a staged rollout and responsibility for the release checklist."
        ],
        {"project": True},
        {"person", "project"},
    ),
    (
        "incidental_owned_object",
        {
            "person": ("person", "Rin Patel", "materialized"),
            "object": ("artifact", "Blue notebook", "provisional"),
        },
        ["Rin Patel uses a blue notebook to write meeting notes."],
        {"object": False},
        {"person"},
    ),
    (
        "routine_activity",
        {
            "person": ("person", "Rin Patel", "materialized"),
            "event": ("event", "Morning walk", "provisional"),
        },
        ["Rin Patel enjoyed a routine morning walk."],
        {"event": False},
        {"person"},
    ),
    (
        "substantial_event",
        {
            "person": ("person", "Rin Patel", "materialized"),
            "event": ("event", "Water-system field trial", "provisional"),
        },
        [
            "Rin Patel coordinated the water-system field trial with the facilities team on 2031-05-08.",
            "The field trial found a faulty valve and the team agreed to replace it before reopening the system.",
            "Rin Patel will report the retest results to the facilities team on 2031-05-12.",
        ],
        {"event": True},
        {"person", "event"},
    ),
    (
        "useful_artifact",
        {
            "person": ("person", "Rin Patel", "materialized"),
            "artifact": ("artifact", "Calibration handbook", "provisional"),
        },
        [
            "Rin Patel wrote the Calibration handbook, a reference manual explaining instrument setup, accuracy limits and calibration procedures.",
            "The handbook is the facilities team's standard reference and is revised after each instrument upgrade.",
        ],
        {"artifact": True},
        {"person", "artifact"},
    ),
]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", action="store_true")
    args = parser.parse_args()
    root = fresh_run_root(
        "page-admission-pipeline" if args.pipeline else "separate-page-admission"
    )
    config = Config.from_toml(Path("mycelium.toml"))
    qa = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm)
    qa.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await qa.llm.client.list()).model_dump())
    results = []
    for trial in range(3):
        for name, definitions, statements, expected, destinations in CASES:
            entities = {
                eid: EntityRecord(
                    eid,
                    kind,
                    title,
                    eid,
                    [],
                    "active",
                    "2031-01-01",
                    "2031-01-01",
                    materialization_state=state,
                )
                for eid, (kind, title, state) in definitions.items()
            }
            if args.pipeline:
                memory = Mycelium(root / f"{trial}-{name}" / "store", config=config)
                memory.llm.trace_path = root / "calls.jsonl"
                for entity in entities.values():
                    memory.artifacts.save_entity(entity)
                source = SourceDocument(
                    "source",
                    "agent_conversation",
                    "source",
                    "2031-05-08",
                    None,
                    [],
                    [
                        SourceSegment(f"segment-{i}", i, text)
                        for i, text in enumerate(statements, 1)
                    ],
                )
                memory.artifacts.save_source(source)
                claims = [
                    MemoryClaim(
                        f"claim-{i}",
                        text,
                        [],
                        [ClaimProvenance("source", [f"segment-{i}"])],
                        "2031-05-08",
                    )
                    for i, text in enumerate(statements, 1)
                ]
                for claim in claims:
                    memory.artifacts.save_claim(claim)
                # These identities are pre-established from source evidence.
                # Bare names alone are not a sound identity-matching control.
                for entity in entities.values():
                    memory.artifacts.save_entity_resolution_decision(
                        EntityResolutionDecision(
                            f"established-{entity.entity_id}",
                            "entity_creation",
                            entity.entity_id,
                            entity.entity_type,
                            entity.title,
                            [source.source_id],
                            [claim.claim_id for claim in claims],
                            [segment.segment_id for segment in source.segments],
                            1.0,
                            "Source-established fixture identity",
                            "accepted",
                            "initial",
                            "2031-05-08",
                            identity_evidence_claim_ids=[
                                claim.claim_id for claim in claims
                            ],
                        )
                    )
                result = await memory.consolidator.router.route(
                    [ClaimEvidence(claim, source) for claim in claims]
                )
                pages = {eid for route in result.routes for eid in route.page_sections}
                passed = not result.failures and destinations <= pages
                prohibited_types = {
                    entities[eid].entity_type
                    for eid, admitted in expected.items()
                    if not admitted
                }
                resolved_entities = {
                    **entities,
                    **{e.entity_id: e for e in result.new_entities},
                    "you": memory.artifacts.get_entity("you"),
                }
                passed = passed and all(
                    resolved_entities[eid].entity_type not in prohibited_types
                    for eid in pages
                )
                record = {
                    "trial": trial,
                    "case": name,
                    "passed": passed,
                    "result": asdict(result),
                    "plan": memory.artifacts.list_identity_work_units()[0].entity_plan,
                }
                results.append(record)
                write(root / "results.json", results)
                print(trial, name, passed, pages, result.failures, flush=True)
                memory.close()
                continue
            claims = {
                f"C{i:03d}": {
                    "text": statement,
                    "citations": [
                        {"source_id": "source", "segment_id": f"segment-{i}"}
                    ],
                }
                for i, statement in enumerate(statements, 1)
            }
            evidence = {
                "claims": claims,
                "sources": {
                    "source": {
                        "segments": {
                            f"segment-{i}": {"text": text}
                            for i, text in enumerate(statements, 1)
                        }
                    }
                },
            }
            schema = page_admission_model(claims, entities)
            system, user = page_admission_prompt(
                RoutingFormatter.entity_catalog(
                    entities.values(), include_sections=True
                ),
                json.dumps(
                    {
                        eid: {"entity_type": e.entity_type, "title": e.title}
                        for eid, e in entities.items()
                    }
                ),
                json.dumps(evidence),
            )
            record = {
                "case": name,
                "trial": trial,
                "system": system,
                "user": user,
                "schema": schema.model_json_schema(),
            }
            results.append(record)
            write(root / "results.json", results)
            response = schema.model_validate(
                await qa.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=4096,
                    debug_label="page-admission-probe",
                )
            ).model_dump()
            admitted = {
                eid: value["basis"] != NO_PAGE_BASIS
                for eid, value in response["page_admissions"].items()
            }
            eligible = {
                eid: entity
                for eid, entity in entities.items()
                if entity.materialization_state == "materialized" or admitted.get(eid)
            }
            subjects = [
                {
                    "entity_id": eid,
                    "entity_type": e.entity_type,
                    "title": e.title,
                    "participant_bindings": [],
                }
                for eid, e in entities.items()
            ]
            attribution, presentation, _ = await decide(
                qa.llm, subjects, evidence, eligible, {}
            )
            response.update(attribution=attribution, decisions=presentation)
            selected = {
                eid
                for decision in response["decisions"].values()
                for eid in decision["pages"]
            }
            passed = admitted == expected and selected == destinations
            record.update(response=response, passed=passed)
            write(root / "results.json", results)
            print(trial, name, passed, response, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Page admission contract failed")


if __name__ == "__main__":
    asyncio.run(main())
