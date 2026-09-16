"""Neutral direct tests of occurrence-scoped human identity bindings."""

import asyncio
import json
from pathlib import Path

import httpx

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from mycelium.config import Config
from mycelium.reviewed_identity_contract import reviewed_identity_model, reviewed_identity_prompt


CASES = [
    ("person_and_new_project", "Rin Patel leads Orchard, an ongoing toolchain upgrade project.",
     {"person-rin": ("person", "Rin Patel")}, [("person-rin", "Rin Patel")], {"person-rin"}, {"project"}),
    ("two_reviewed_subjects", "Rin Patel leads Orchard, an ongoing toolchain upgrade project.",
     {"person-rin": ("person", "Rin Patel"), "project-orchard": ("project", "Orchard")},
     [("person-rin", "Rin Patel"), ("project-orchard", "Orchard")], {"person-rin", "project-orchard"}, set()),
    ("person_and_colleague", "Rin Patel and Casey Wells organize a workshop together.",
     {"person-rin": ("person", "Rin Patel")}, [("person-rin", "Rin Patel")], {"person-rin"}, {"person"}),
    ("shared_surface_different_kinds", "Nora, the person, maintains a software project also called Nora.",
     {"project-nora": ("project", "Nora")}, [("project-nora", "software project called Nora")], {"project-nora"}, {"person"}),
]


async def main():
    root = fresh_run_root("reviewed-identity")
    config = Config.from_toml(Path("mycelium.toml")).llm
    qa = OllamaQaClient(config.model, config.url, llm_config=config)
    qa.llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", vars(config))
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(config.url.rstrip("/") + "/api/tags")
        response.raise_for_status()
        write(root / "models.json", response.json())
    results = []
    for trial in range(3):
        for name, text, registry, reviews, expected_existing, expected_new_types in CASES:
            bindings = {f"R{i:03d}": {"reference_id": f"review-{i}", "entity_id": entity_id,
                "surface": surface, "claim_alias": "C001"} for i, (entity_id, surface) in enumerate(reviews, 1)}
            schema = reviewed_identity_model(["C001"], {}, {eid: value[0] for eid, value in registry.items()}, bindings)
            evidence = json.dumps({"claims": {"C001": {"text": text, "citations": [{"source_id": "S", "segment_id": "S1"}]}},
                                   "sources": {"S": {"segments": {"S1": {"text": text}}}}})
            system, user = reviewed_identity_prompt(json.dumps({eid: {"entity_type": kind, "title": title}
                for eid, (kind, title) in registry.items()}), evidence, "none", "none", "none", bindings)
            record = {"trial": trial, "case": name, "system": system, "user": user, "schema": schema.model_json_schema()}
            results.append(record)
            write(root / "results.json", results)
            response = schema.model_validate(await qa.llm.call_structured(system, user, schema,
                num_predict=4096, debug_label="reviewed-identity-probe")).model_dump()
            existing = {n["entity_id"] for n in response["subjects"] if n["resolution"] == "existing"}
            new_types = {n["entity_type"] for n in response["subjects"] if n["resolution"] == "new"}
            passed = existing == expected_existing and new_types >= expected_new_types
            record.update(response=response, passed=passed)
            write(root / "results.json", results)
            print(trial, name, passed, response, flush=True)
    print("OUTPUT", root, flush=True)
    if not all(r["passed"] for r in results):
        raise SystemExit("Reviewed identity contract failed a neutral case")


if __name__ == "__main__":
    asyncio.run(main())
