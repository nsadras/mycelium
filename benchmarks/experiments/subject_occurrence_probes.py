"""Direct participant-evidence contract checks, with optional retained-request replay."""

import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import time


from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium.config import Config
from mycelium.artifacts import ArtifactStore, ClaimProvenance, MemoryClaim, SourceDocument, SourceSegment
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.subject_discovery import subject_discovery_model, subject_discovery_prompt
from mycelium.telemetry import trace_operation


def neutral_cases():
    rows = [
        ("Dara", "user", "I coordinate the community garden and manage the seed budget."),
        ("Ellis", "participant", "I maintain the watering equipment for the garden."),
        ("Kai", "participant", "I organize a separate repair club and will teach soldering there."),
        ("Dara", "user", "I prefer paper receipts for the garden expenses."),
        ("Ellis", "participant", "Our garden work continues throughout the year."),
        ("Kai", "participant", "The repair club accepts broken household appliances."),
        ("Dara", "user", "The garden has six raised beds and needs two more."),
        ("Ellis", "participant", "I am replacing the garden hose because its connector leaks."),
        ("Kai", "participant", "I will buy a soldering station for the repair club."),
        ("Dara", "user", "Keep the repair club's expenses separate from the garden budget."),
        ("Ellis", "participant", "No pesticides are permitted in the garden."),
        ("Kai", "participant", "Visitors to the repair club must wear eye protection."),
    ]
    for name, selected in [("small_roster", rows[:3]), ("larger_cohort", rows)]:
        participants = {f"P{i:03d}": {"name": person, "role": role, "source_id": "source"}
                        for i, (person, role, _) in enumerate(rows[:3], 1)}
        evidence = {"participants": participants, "claims": {}, "sources": {
            "source": {"source_type": "meeting_transcript", "occurred_at": "2031-05-06T10:00:00",
                       "segments": {}}
        }}
        for i, (speaker, role, text) in enumerate(selected, 1):
            sid, cid = f"segment-{i}", f"C{i:03d}"
            evidence["sources"]["source"]["segments"][sid] = {
                "speaker": speaker, "role": role, "text": text, "timestamp": "2031-05-06T10:00:00"}
            evidence["claims"][cid] = {"text": f"{speaker} said: {text}", "claim_id": cid,
                "claim_type": "observation", "about": [{"entity": speaker, "role": "subject"}],
                "temporal_status": "current", "facets": {}, "evidence_modality": "speech",
                "citations": [{"source_id": "source", "segment_id": sid}]}
        yield name, evidence, None
    evidence = {"claims": {
        "C001": {"text": "Morgan, the teacher, and Morgan, the architect, are different people. The teacher runs a pottery club.",
                 "citations": [{"source_id": "source", "segment_id": "s1"}]},
        "C002": {"text": "Morgan the architect designs bridges and does not run the pottery club.",
                 "citations": [{"source_id": "source", "segment_id": "s2"}]},
    }, "participants": {
        "P001": {"name": "Morgan the teacher", "role": "user", "source_id": "source"},
        "P002": {"name": "Morgan the architect", "role": "participant", "source_id": "source"},
    }, "sources": {"source": {"source_type": "meeting_transcript", "segments": {
        "s1": {"speaker": "Morgan the teacher", "role": "user", "text": "I run a pottery club. The architect and I are different people."},
        "s2": {"speaker": "Morgan the architect", "role": "participant", "text": "I design bridges, not the pottery club."},
    }}}}
    yield "different_people_same_name", evidence, None


def replay_case(path):
    dump = json.loads(path.read_text())
    user = next(m["content"] for m in dump["messages"] if m["role"] == "user")
    user = user.split("\n\nOUTPUT CONTRACT (JSON Schema)\n", 1)[0]
    payload = user.split("\n", 1)[1].split("\n\nHUMAN-REVIEWED IDENTITY OCCURRENCES", 1)[0]
    return path.stem, json.loads(payload), str(path)


async def route_case(root, evidence, llm, settings):
    artifacts = ArtifactStore(root / "artifacts")
    try:
        artifacts.create_entity("you", "You")
        sources = {}
        for sid, source in evidence["sources"].items():
            sources[sid] = SourceDocument(sid, source["source_type"], sid, "2031-05-06",
                source.get("occurred_at"), [], [
                    SourceSegment(key, index, segment["text"], segment.get("speaker"),
                                  segment.get("role"), segment.get("timestamp"))
                    for index, (key, segment) in enumerate(source["segments"].items())])
            artifacts.save_source(sources[sid])
        items = []
        for cid, value in evidence["claims"].items():
            citations = value["citations"]
            claim = MemoryClaim(cid, value["text"], value.get("about", []),
                [ClaimProvenance(c["source_id"], [c["segment_id"]]) for c in citations], "2031-05-06",
                claim_type=value.get("claim_type", "unknown"), facets=value.get("facets", {}),
                temporal_status=value.get("temporal_status", "unknown"),
                evidence_modality=value.get("evidence_modality", "unknown"))
            artifacts.save_claim(claim)
            items.append(ClaimEvidence(claim, sources[citations[0]["source_id"]]))
        router = ClaimRouter(llm, artifacts, settings)
        result = await router.route(items, dream_run_id="probe")
        if result.failures:
            raise ValueError(f"Native routing failed: {result.failures}")
        work = artifacts.list_identity_work_units()[0]
        return work.entity_plan["discovery"], asdict(result)
    finally:
        artifacts.db.close()


async def main(args):
    root = fresh_run_root("subject-occurrence-pipeline" if args.pipeline else "subject-occurrence-contract")
    settings = Config.from_toml(Path("mycelium.toml"))
    llm = OllamaQaClient(settings.llm.model, settings.llm.url, llm_config=settings.llm).llm
    llm.trace_path = root / "calls.jsonl"
    write(root / "config.json", asdict(settings))
    write(root / "models.json", (await llm.client.list()).model_dump())
    llm.client = RecordingClient(llm.client, root / "requests")
    write(root / "experiment.json", {"concurrent_benchmark": args.concurrent_benchmark,
        "latencies_comparable": not bool(args.concurrent_benchmark), "started_at": time.time()})
    print("OUTPUT", root, flush=True)
    results = []
    cases = [*neutral_cases(), *(replay_case(p) for p in args.replay_failure)]
    for trial in range(args.trials):
        for name, evidence, replay in cases:
            roles = {p: value["role"] for p, value in evidence["participants"].items()}
            schema = subject_discovery_model(evidence["claims"], roles, {})
            system, user = subject_discovery_prompt(json.dumps(evidence, ensure_ascii=False), "none")
            record = {"trial": trial, "case": name, "replay": replay, "system": system, "user": user,
                      "schema": schema.model_json_schema()}
            try:
                with trace_operation("subject_occurrence_probe", trial=trial, case=name):
                    if args.pipeline:
                        output, record["routing"] = await route_case(root / f"{trial}-{name}", evidence, llm, settings)
                    else:
                        output = schema.model_validate(await llm.call_structured(
                            system, user, schema, num_predict=8192, debug_label="subject-occurrence-probe"
                        )).model_dump()
                ids = set(evidence["claims"]) | set(roles)
                misplaced = [alias for subject in output["subjects"] for alias in subject["alternate_names"] if alias in ids]
                assignments = [row["subject_id"] for row in output["participant_subjects"].values()]
                distinct = bool(replay) or len(assignments) == len(set(assignments))
                record.update(output=output, passed=not misplaced and distinct)
            except Exception as exc:
                record.update(passed=False, error=f"{type(exc).__name__}: {exc}")
            results.append(record)
            write(root / "results.json", results)
            print(trial, name, record["passed"], flush=True)
    write(root / "completion.json", {"completed_at": time.time(), "passed": sum(r["passed"] for r in results), "total": len(results)})
    if not all(r["passed"] for r in results):
        raise SystemExit("Subject occurrence contract failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--pipeline", action="store_true")
    parser.add_argument("--replay-failure", type=Path, action="append", default=[])
    parser.add_argument("--concurrent-benchmark")
    asyncio.run(main(parser.parse_args()))
