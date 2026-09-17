"""Configured-model identity decisions after bounded vector candidate discovery."""

import asyncio
import argparse
import json
from dataclasses import asdict
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EntityRecord,
    EntityResolutionDecision,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.claim_index import OllamaEmbedder
from mycelium.config import Config
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.identity_candidates import identity_documents, identity_records
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt
from mycelium.subject_identity import subject_identity_model, subject_identity_prompt
from mycelium.semantic_candidates import SemanticCandidates


CASES = [
    (
        "known_alias",
        "Rin is still coordinating the toolchain upgrade.",
        "existing",
        {"person-rin"},
    ),
    (
        "known_project",
        "Orchard needs a release checklist before the toolchain rollout.",
        "existing",
        {"project-orchard"},
    ),
    (
        "person_not_project",
        "Nora is a new colleague who joined the museum team.",
        "new",
        set(),
    ),
    (
        "ambiguous_person",
        "Alex offered to help. The source gives no surname or other identifying information.",
        "review_required",
        {"person-alex-a", "person-alex-b"},
    ),
]


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", action="store_true")
    args = parser.parse_args()
    root = fresh_run_root(
        "source-first-identity-pipeline" if args.pipeline else "source-first-identity"
    )
    config = Config.from_toml(Path("mycelium.toml"))
    write(root / "config.json", asdict(config))
    qa = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm)
    qa.llm.trace_path = root / "calls.jsonl"
    embedder = OllamaEmbedder(
        config.llm.url,
        config.retrieval.embedding_model,
        timeout=config.llm.timeout_seconds,
        trace_path=root / "embedding-calls.jsonl",
    )
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(config.llm.url.rstrip("/") + "/api/tags")
        response.raise_for_status()
        write(root / "models.json", response.json())
    artifacts = ArtifactStore(root / "store" / "artifacts")
    artifacts.create_entity("you", "You")
    definitions = [
        (
            "person-rin",
            "person",
            "Rin Patel",
            ["Rin"],
            "Coordinates the toolchain upgrade.",
        ),
        (
            "project-orchard",
            "project",
            "Orchard",
            ["toolchain upgrade"],
            "An ongoing compiler and build-tool upgrade.",
        ),
        (
            "project-nora",
            "project",
            "Nora",
            [],
            "A software project for museum catalogs.",
        ),
        (
            "person-alex-a",
            "person",
            "Alex Chen",
            ["Alex"],
            "A nurse in a regional clinic.",
        ),
        (
            "person-alex-b",
            "person",
            "Alex Mercer",
            ["Alex"],
            "A freelance photographer.",
        ),
    ]
    occupations = [
        "restores furniture",
        "teaches swimming",
        "manages a bookstore",
        "studies geology",
        "coordinates a garden",
    ]
    names = [
        "Ivo Reed",
        "Tessa Cole",
        "Bruno Hart",
        "Kira Bell",
        "Soren Vale",
        "Elena Moss",
        "Hugo Lane",
        "Ada Finch",
        "Malik Snow",
        "Rhea Stone",
        "Luca West",
        "Mina Grey",
        "Omar Lake",
        "Zoe Field",
        "Niko Rose",
        "Leah Shaw",
        "Theo Grant",
        "Iris Wood",
        "Amir Reed",
        "Maya Cross",
        "Leon Park",
        "Nina Ford",
        "Otis Hill",
        "Alma Fox",
        "Finn Day",
        "Vera Nash",
        "Sami Brooks",
        "Cleo Dawn",
        "Evan Duke",
        "Lila Frost",
        "Noel Green",
        "Ruth Hayes",
        "Wade King",
        "Esme Long",
        "Dara North",
    ]
    for i, name in enumerate(names):
        definitions.append(
            (
                f"person-{i:03d}",
                "person",
                name,
                [],
                f"{name} {occupations[i % len(occupations)]}.",
            )
        )
    for eid, kind, title, aliases, text in definitions:
        artifacts.save_entity(
            EntityRecord(
                eid, kind, title, eid, aliases, "active", "2031-01-01", "2031-01-01"
            )
        )
        source_id, claim_id = f"source-{eid}", f"claim-{eid}"
        segment_id = source_id + "#1"
        artifacts.save_source(
            SourceDocument(
                source_id,
                "agent_conversation",
                source_id,
                "2031-01-01",
                None,
                [],
                [SourceSegment(segment_id, 0, text)],
            )
        )
        artifacts.save_claim(
            MemoryClaim(
                claim_id,
                text,
                [],
                [ClaimProvenance(source_id, [segment_id])],
                "2031-01-01",
            )
        )
        artifacts.save_entity_resolution_decision(
            EntityResolutionDecision(
                f"decision-{eid}",
                "entity_creation",
                eid,
                kind,
                title,
                [source_id],
                [claim_id],
                [segment_id],
                1.0,
                "Declared neutral identity",
                "accepted",
                "seed",
                "2031-01-01",
                identity_evidence_claim_ids=[claim_id],
            )
        )
    records = identity_records(artifacts, artifacts.list_entities())
    write(root / "registry.json", records)
    documents = identity_documents(records)
    candidates = SemanticCandidates(root / "index", embedder, artifacts.db)
    results = []
    for trial in range(3):
        for name, statement, expected_resolution, expected_ids in CASES:
            if args.pipeline:
                source_id = f"input-{trial}-{name}"
                source = SourceDocument(
                    source_id,
                    "agent_conversation",
                    source_id,
                    "2031-01-01",
                    None,
                    [],
                    [SourceSegment(source_id + "#1", 0, statement)],
                )
                claim = MemoryClaim(
                    source_id,
                    statement,
                    [],
                    [ClaimProvenance(source_id, [source_id + "#1"])],
                    "2031-01-01",
                )
                artifacts.save_source(source)
                artifacts.save_claim(claim)
                result = await ClaimRouter(qa.llm, artifacts, config).route(
                    [ClaimEvidence(claim, source)]
                )
                plan = next(
                    u.entity_plan
                    for u in artifacts.list_identity_work_units()
                    if u.claim_ids == [claim.claim_id]
                )
                subjects = plan.get("subjects", [])
                if expected_resolution == "existing":
                    passed = expected_ids <= {
                        s["entity_id"]
                        for s in subjects
                        if s["resolution"] == "existing"
                    }
                elif expected_resolution == "review_required":
                    passed = any(
                        s["resolution"] == "review_required"
                        and set(s["candidate_entity_ids"]) == expected_ids
                        for s in subjects
                    )
                else:
                    passed = any(
                        s["resolution"] == "new" and s["entity_type"] == "person"
                        for s in subjects
                    )
                    passed = passed and all(
                        s.get("entity_id") != "project-nora" for s in subjects
                    )
                record = {
                    "trial": trial,
                    "case": name,
                    "plan": plan,
                    "result": asdict(result),
                    "passed": passed and not result.failures,
                }
                results.append(record)
                write(root / "results.json", results)
                print(trial, name, record["passed"], result.failures, flush=True)
                continue
            evidence = json.dumps(
                {
                    "claims": {
                        "C001": {
                            "text": statement,
                            "citations": [
                                {"source_id": "source", "segment_id": "segment"}
                            ],
                        }
                    },
                    "sources": {
                        "source": {"segments": {"segment": {"text": statement}}}
                    },
                }
            )
            discovery_schema = subject_discovery_model(["C001"], {}, {})
            system, user = subject_discovery_prompt(evidence, "none")
            discovered = discovery_schema.model_validate(
                await qa.llm.call_structured(
                    system,
                    user,
                    discovery_schema,
                    num_predict=4096,
                    debug_label="subject-discovery-probe",
                )
            ).model_dump()
            decisions, selections = [], []
            for subject in discovered["subjects"]:
                ids = await candidates.select(
                    documents,
                    [json.dumps(subject)],
                    limit=24,
                    required_ids={"you"} if "you" in documents else set(),
                )
                registry = {eid: records[eid] for eid in ids}
                schema = subject_identity_model(ids)
                system, user = subject_identity_prompt(subject, registry, evidence)
                response = schema.model_validate(
                    await qa.llm.call_structured(
                        system,
                        user,
                        schema,
                        num_predict=2048,
                        debug_label="subject-identity-probe",
                    )
                ).model_dump()["decision"]
                decisions.append({**subject, **response})
                selections.extend(ids)
            ids = list(dict.fromkeys(selections))
            record = {
                "case": name,
                "trial": trial,
                "candidate_ids": ids,
                "system": system,
                "user": user,
                "candidate_trace": candidates.last_trace,
                "schema": schema.model_json_schema(),
                "discovered": discovered,
            }
            results.append(record)
            write(root / "results.json", results)
            response = {"subjects": decisions}
            subjects = decisions
            if expected_resolution == "existing":
                passed = expected_ids <= {
                    s["entity_id"] for s in subjects if s["resolution"] == "existing"
                }
            elif expected_resolution == "review_required":
                passed = any(
                    s["resolution"] == "review_required"
                    and set(s["candidate_entity_ids"]) == expected_ids
                    for s in subjects
                )
            else:
                passed = any(
                    s["resolution"] == "new" and s["entity_type"] == "person"
                    for s in subjects
                )
                passed = passed and all(
                    s.get("entity_id") != "project-nora" for s in subjects
                )
            record.update(response=response, passed=passed and expected_ids <= set(ids))
            write(root / "results.json", results)
            print(trial, name, record["passed"], response, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Bounded identity candidates failed a neutral case")


if __name__ == "__main__":
    asyncio.run(main())
