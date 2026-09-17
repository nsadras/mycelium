"""Proposed identity matching across inferred types and final source-grounded names."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.subject_identity import subject_identity_model, subject_identity_prompt


def record(kind, title, evidence):
    return {
        "entity_type": kind,
        "title": title,
        "aliases": [],
        "identity_evidence": [
            {
                "claim_id": "earlier",
                "text": evidence,
                "citations": [{"source_id": "prior", "segment_ids": ["prior-1"]}],
            }
        ],
    }


def cases():
    yield (
        "project_label_drift",
        "artifact",
        "Aurora",
        "The newly named local inventory helper",
        "I am calling that previously unnamed local inventory helper Aurora. This is the same project I started earlier.",
        {
            "e1": record(
                "project",
                "Inventory Helper Project",
                "I started developing a local inventory helper.",
            )
        },
        "existing",
        {"e1"},
        "Aurora",
    )
    yield (
        "person_label_drift",
        "organization",
        "Devon Vale",
        "Devon Vale provides instrument restoration",
        "Devon Vale, the same individual who restored my violin, is restoring the cello now.",
        {"e1": record("person", "Devon Vale", "Devon Vale restored my violin.")},
        "existing",
        {"e1"},
        "Devon Vale",
    )
    yield (
        "distinct_product",
        "artifact",
        "Digitization Handbook",
        "A reference handbook written during an ongoing digitization effort",
        "The digitization project has produced a separate handbook called Digitization Handbook. The handbook explains scanner settings.",
        {
            "e1": record(
                "project",
                "Digitization Project",
                "A continuing digitization effort to scan the museum collection.",
            )
        },
        "new",
        set(),
        "Digitization Handbook",
    )
    yield (
        "person_namesake",
        "person",
        "Nora",
        "A newly introduced colleague",
        "Nora is a new colleague. She is a person, separate from the catalog project also named Nora.",
        {"e1": record("project", "Nora", "Nora is a catalog software project.")},
        "new",
        set(),
        "Nora",
    )
    yield (
        "ambiguous_person",
        "person",
        "Alex",
        "A helper whose surname and background were not stated",
        "Alex offered to help. No surname or identifying context was supplied.",
        {
            "e1": record("person", "Alex Chen", "Alex Chen is a nurse."),
            "e2": record("person", "Alex Mercer", "Alex Mercer is a photographer."),
        },
        "review_required",
        {"e1", "e2"},
        "Alex",
    )
    yield (
        "new_name_spelling",
        "organization",
        "MetraCloud",
        "A transcription service",
        "MetroCloud offers transcription for museum interviews.",
        {},
        "new",
        set(),
        "MetroCloud",
    )
    yield (
        "existing_name_spelling",
        "organization",
        "MetraCloud",
        "A transcription service",
        "MetroCloud has added interview translation to its transcription service.",
        {
            "e1": record(
                "organization",
                "MetroCloud",
                "MetroCloud offers transcription for museum interviews.",
            )
        },
        "existing",
        {"e1"},
        "MetroCloud",
    )
    yield (
        "unknown_person",
        "person",
        "Unidentified Visitor",
        "An unidentified visitor",
        "An unidentified visitor asked about the exhibition. The source gives no name or identifying information.",
        {},
        "review_required",
        set(),
        None,
    )
    for name, title, prior, raw, expected in [
        (
            "additional_nickname",
            "Lark",
            "Lyra",
            "My chamber group Lyra is also nicknamed Lark; Lyra remains its preferred name.",
            "Lyra",
        ),
        (
            "explicit_name_correction",
            "Naveen",
            "Navin",
            "The person's name was transcribed incorrectly as Navin. The correct name is Naveen.",
            "Naveen",
        ),
        (
            "explicit_rename",
            "Larch",
            "Cedar",
            "I renamed the Cedar inventory project to Larch. It is the same project.",
            "Larch",
        ),
        (
            "unnamed_followup",
            "Inventory Tool",
            "Inventory Helper",
            "The inventory helper project now imports spreadsheet records. It still has no product name.",
            "Inventory Helper",
        ),
    ]:
        kind = "person" if name == "explicit_name_correction" else "project"
        yield (
            name,
            kind,
            title,
            raw,
            raw,
            {"e1": record(kind, prior, f"Established subject: {prior}.")},
            "existing",
            {"e1"},
            expected,
        )


async def main(trials=1):
    root = fresh_run_root("identity-boundary-contract")
    print("OUTPUT", root, flush=True)
    config = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(config.llm.model, config.llm.url, llm_config=config.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(config))
    write(root / "models.json", (await llm.client.list()).model_dump(mode="json"))
    (root / "probe.py").write_text(Path(__file__).read_text())
    llm.client = RecordingClient(llm.client, root / "requests")
    rows = []
    for trial in range(trials):
        for (
            name,
            kind,
            title,
            description,
            raw,
            registry,
            resolution,
            ids,
            expected_title,
        ) in cases():
            subject = {
                "entity_type": kind,
                "title": title,
                "description": description,
                "alternate_names": [],
                "supporting_evidence": ["C1"],
            }
            ev = {
                "claims": {
                    "C1": {
                        "text": raw,
                        "citations": [{"source_id": "S", "segment_id": "S1"}],
                    }
                },
                "sources": {"S": {"segments": {"S1": {"text": raw}}}},
            }
            schema = subject_identity_model(registry, json.dumps(ev))
            system, user = subject_identity_prompt(subject, registry, json.dumps(ev))
            row = {"trial": trial, "case": name, "status": "running", "passed": False}
            rows.append(row)
            write(root / "results.json", rows)
            d = schema.model_validate(
                await llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=2048,
                    debug_label="identity-boundary-probe",
                )
            ).model_dump()["decision"]
            actual = (
                {d["entity_id"]}
                if d["resolution"] == "existing"
                else set(d.get("candidate_entity_ids", []))
            )
            applied_title = d.get("title")
            if d["resolution"] == "existing":
                applied_title = (
                    d["preferred_name_update"] or registry[d["entity_id"]]["title"]
                )
            checks = {
                "resolution": d["resolution"] == resolution,
                "ids": actual == ids,
                "title": applied_title == expected_title
                if expected_title is not None
                else applied_title is None
                if resolution == "existing"
                else bool(applied_title),
            }
            row.update(
                status="complete",
                decision=d,
                checks=checks,
                passed=all(checks.values()),
            )
            write(root / "results.json", rows)
            print(trial, name, row["passed"], d, flush=True)
    write(
        root / "completion.json",
        {"passed": sum(r["passed"] for r in rows), "total": len(rows)},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=1)
    asyncio.run(main(parser.parse_args().trials))
