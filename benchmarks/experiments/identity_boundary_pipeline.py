"""Native source discovery, identity candidates, naming and routing boundaries."""

import asyncio
import argparse
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.identity_boundary_probes import cases
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimProvenance,
    EntityRecord,
    EntityResolutionDecision,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.snapshots import snapshot_store


def source_claim(artifacts, sid, text, *, current=False):
    source = SourceDocument(
        sid,
        "agent_conversation" if current else "document",
        sid,
        "2031-05-06",
        "2031-05-06",
        ["Rae"] if current else [],
        [
            SourceSegment(
                f"{sid}-1",
                0,
                text,
                "Rae" if current else None,
                "user" if current else None,
            )
        ],
    )
    claim = MemoryClaim(
        f"claim-{sid}", text, [], [ClaimProvenance(sid, [f"{sid}-1"])], "2031-05-06"
    )
    artifacts.save_source(source)
    artifacts.save_claim(claim)
    return source, claim


async def main(trials=1):
    root = fresh_run_root("identity-boundary-pipeline")
    print("OUTPUT", root, flush=True)
    root.mkdir(parents=True, exist_ok=True)
    (root / "probe.py").write_text(Path(__file__).read_text())
    rows = []
    wanted = {
        "project_label_drift",
        "distinct_product",
        "person_namesake",
        "new_name_spelling",
        "explicit_name_correction",
        "explicit_rename",
        "additional_nickname",
        "unnamed_followup",
    }
    for trial in range(trials):
        for (
            name,
            kind,
            title,
            description,
            text,
            registry,
            resolution,
            expected_ids,
            expected_title,
        ) in cases():
            if name not in wanted:
                continue
            directory = root / f"{trial}-{name}"
            row = {"trial": trial, "case": name, "status": "running", "passed": False}
            rows.append(row)
            write(root / "results.json", rows)
            with Mycelium(directory / "store", config_path="mycelium.toml") as memory:
                memory.llm.trace_path = directory / "calls.jsonl"
                write(directory / "config.json", asdict(memory.config))
                write(
                    directory / "models.json",
                    (await memory.llm.client.list()).model_dump(mode="json"),
                )
                memory.llm.client = RecordingClient(
                    memory.llm.client, directory / "requests"
                )
                for eid, definition in registry.items():
                    entity = EntityRecord(
                        eid,
                        definition["entity_type"],
                        definition["title"],
                        eid,
                        [],
                        "active",
                        "2031-01-01",
                        "2031-01-01",
                    )
                    memory.artifacts.save_entity(entity)
                    prior_source, prior_claim = source_claim(
                        memory.artifacts,
                        f"prior-{eid}",
                        definition["identity_evidence"][0]["text"],
                    )
                    memory.artifacts.save_entity_resolution_decision(
                        EntityResolutionDecision(
                            f"prior-{eid}",
                            "entity_creation",
                            eid,
                            entity.entity_type,
                            entity.title,
                            [prior_source.source_id],
                            [prior_claim.claim_id],
                            [prior_source.segments[0].segment_id],
                            0.9,
                            "Established source-backed identity",
                            "accepted",
                            "prior",
                            "2031-01-01",
                            identity_evidence_claim_ids=[prior_claim.claim_id],
                            proposed_scope="independent",
                            proposed_page_state="materialized",
                        )
                    )
                source, claim = source_claim(
                    memory.artifacts, "current", text, current=True
                )
                result = await ClaimRouter(
                    memory.llm, memory.artifacts, memory.config
                ).route([ClaimEvidence(claim, source)])
                write(directory / "routing.json", asdict(result))
                for entity in result.new_entities:
                    memory.artifacts.save_entity(entity)
                for decision in result.entity_decisions:
                    memory.artifacts.save_entity_resolution_decision(decision)
                snapshot_store(memory.store_path, directory / "snapshot_store")
                entities = {e.entity_id: e for e in memory.artifacts.list_entities()}
                work = memory.artifacts.list_identity_work_units()[0]
                write(directory / "work_unit.json", asdict(work))
                checks = {"no_failures": not result.failures}
                if name == "project_label_drift":
                    checks.update(
                        same_identity=any(
                            node["resolution"] == "existing"
                            and node.get("entity_id") == "e1"
                            for node in work.entity_plan["subjects"]
                        ),
                        renamed=entities["e1"].title == "Aurora",
                        canonical_type=entities["e1"].entity_type == "project",
                        no_duplicate=not any(
                            e.entity_id not in {"e1", "you"} for e in entities.values()
                        ),
                    )
                elif name == "distinct_product":
                    checks["separate_product"] = any(
                        e.entity_type == "artifact"
                        and e.title == "Digitization Handbook"
                        and e.entity_id != "e1"
                        for e in entities.values()
                    )
                    checks["project_retained"] = entities["e1"].entity_type == "project"
                elif name == "person_namesake":
                    checks["separate_person"] = any(
                        e.entity_type == "person" and e.entity_id != "e1"
                        for e in entities.values()
                    )
                    checks["project_retained"] = entities["e1"].entity_type == "project"
                elif resolution == "existing":
                    checks["same_identity"] = any(
                        node["resolution"] == "existing"
                        and node.get("entity_id") == "e1"
                        for node in work.entity_plan["subjects"]
                    )
                    checks["preferred_name"] = entities["e1"].title == expected_title
                    checks["no_duplicate"] = not any(
                        e.entity_id not in {"e1", "you"} for e in entities.values()
                    )
                else:
                    checks["source_spelling"] = any(
                        e.title == "MetroCloud" and e.entity_type == "organization"
                        for e in entities.values()
                    )
                row.update(
                    status="complete", checks=checks, passed=all(checks.values())
                )
            write(root / "results.json", rows)
            print(trial, name, row["passed"], checks, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in rows), "total": len(rows)},
    )
    if not all(r["passed"] for r in rows):
        raise SystemExit("Identity boundary pipeline failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1)
    asyncio.run(main(parser.parse_args().trials))
