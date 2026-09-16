"""Probe the production evidence representation without whole-claim identity metadata."""

import asyncio
import json

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.experiments.identity_review_cases import CASES
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimEntityReference,
    ClaimProvenance,
    EntityRecord,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt
from mycelium.subject_review_bindings import subject_review_model, subject_review_prompt


async def main():
    root = fresh_run_root("source-then-reviewed-bindings")
    memory = Mycelium(root / "store", config_path="mycelium.toml")
    llm = memory.llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", vars(memory.config.llm))
    write(root / "models.json", (await llm.client.list()).model_dump())
    artifacts = memory.artifacts
    results = []
    for trial in range(3):
        for name, text, registry, reviews, _, _ in CASES:
            for eid, (kind, title) in registry.items():
                artifacts.save_entity(
                    EntityRecord(
                        eid, kind, title, eid, [], "active", "2031-01-01", "2031-01-01"
                    )
                )
            source = SourceDocument(
                f"{name}-{trial}",
                "agent_conversation",
                "source",
                "2031-01-01",
                None,
                [],
                [SourceSegment("segment", 0, text)],
            )
            claim = MemoryClaim(
                source.source_id,
                text,
                [],
                [ClaimProvenance(source.source_id, ["segment"])],
                "2031-01-01",
            )
            artifacts.save_source(source)
            artifacts.save_claim(claim)
            bindings = {
                f"R{i:03d}": {
                    "reference_id": f"review-{name}-{trial}-{i}",
                    "entity_id": eid,
                    "claim_alias": "C001",
                    "surface": surface,
                    "entity_type": registry[eid][0],
                    "title": registry[eid][1],
                }
                for i, (eid, surface) in enumerate(reviews, 1)
            }
            for binding in bindings.values():
                artifacts.save_entity_reference(
                    ClaimEntityReference(
                        binding["reference_id"],
                        claim.claim_id,
                        "identity_subject",
                        binding["surface"],
                        binding["entity_id"],
                        1.0,
                        "Explicit review",
                        "manual",
                        "review",
                        "active",
                        "2031-01-01",
                        identity_decision_id=binding["reference_id"],
                    )
                )
            evidence = json.loads(
                RoutingFormatter(artifacts).format_evidence(
                    {"C001": ClaimEvidence(claim, source)}, {}
                )
            )
            for item in evidence["claims"].values():
                del item["identity_references"]
            schema = subject_discovery_model(["C001"], {}, {})
            system, user = subject_discovery_prompt(
                json.dumps(evidence, ensure_ascii=False), "none"
            )
            record = {
                "trial": trial,
                "case": name,
                "system": system,
                "user": user,
                "schema": schema.model_json_schema(),
            }
            results.append(record)
            write(root / "results.json", results)
            response = schema.model_validate(
                await llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=8192,
                    debug_label="source-identity-evidence-probe",
                )
            ).model_dump()
            subjects = {f"S{i:03d}": s for i, s in enumerate(response["subjects"], 1)}
            review_schema = subject_review_model(subjects, bindings)
            review_system, review_user = subject_review_prompt(
                subjects, bindings, json.dumps(evidence, ensure_ascii=False)
            )
            assignments = review_schema.model_validate(
                await llm.call_structured(
                    review_system,
                    review_user,
                    review_schema,
                    num_predict=2048,
                    debug_label="subject-review-bindings-probe",
                )
            ).model_dump()["assignments"]
            passed = len(response["subjects"]) >= 2 and all(
                a["subject_alias"] in subjects
                and subjects[a["subject_alias"]]["entity_type"]
                == bindings[r]["entity_type"]
                for r, a in assignments.items()
            )
            record.update(response=response, assignments=assignments, passed=passed)
            write(root / "results.json", results)
            print(trial, name, record["passed"], response, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(row["passed"] for row in results):
        raise SystemExit("Identity evidence representation failed")


if __name__ == "__main__":
    asyncio.run(main())
