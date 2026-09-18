"""One bounded production lifecycle check; inspect artifacts, not a perfect score.

Run explicitly with the configured host Ollama server already available:
  .venv/bin/python -m benchmarks.experiments.compact_product_check
"""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.compact_probe import BudgetClient, metrics
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.adapters import OllamaQaClient
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.artifact_integrity import artifact_integrity
from mycelium.claim_lifecycle import ClaimLifecycleService
from mycelium.correction_review import CorrectionPreview
from mycelium.memory_tools import MemoryToolset
from mycelium.operations import ConsolidationRequest, RetrievalRequest, SourceInput
from mycelium.snapshots import export_records, snapshot_store
from mycelium.telemetry import trace_operation


BASELINE = Path("benchmark_runs/compact-comparison-20260917T225514Z-6b46ab03")
SECONDS, ATTEMPTS = 600, 18
QUALIFIER = "This is a provisional working note, subject to confirmation by the group."


def copy_seed(source, destination):
    """Read the frozen seed without publishing or opening it as a live store."""
    destination.mkdir(parents=True)
    original = sqlite3.connect((source.resolve() / "memory.sqlite3").as_uri() + "?mode=ro", uri=True)
    copied = sqlite3.connect(destination / "memory.sqlite3")
    try:
        original.backup(copied)
    finally:
        copied.close()
        original.close()


def snapshot(memory, root, name):
    target = root / "snapshots" / name
    snapshot_store(memory.store_path, target / "store")
    export_records(target / "store", target / "records")
    claims = memory.artifacts.list_claims()
    result = {"claims": len(claims), "active_claims": sum(c.status == "active" for c in claims),
              "pages": len(memory.wiki.list_all()), "build_incomplete": memory.artifacts.build_incomplete(),
              "integrity": artifact_integrity(memory)}
    write(target / "summary.json", result)
    return result


async def exercise(memory, root, inputs, rows, *, resume=False):
    budget = memory.llm.client

    async def build(name):
        started, before = time.monotonic(), budget.calls
        with trace_operation("compact_product", step=name, stage="build"):
            result = await memory.consolidate(ConsolidationRequest())
        row = {"step": name, "seconds": time.monotonic() - started,
               "attempts": budget.calls - before, "result": asdict(result),
               "snapshot": snapshot(memory, root, name)}
        rows.append(row)
        write(root / "steps.json", rows)
        print("BUILD", name, row["seconds"], row["attempts"], result.report.failures, flush=True)
        return result

    async def answer(name, question):
        started, before = time.monotonic(), budget.calls
        with trace_operation("compact_product", step=name, stage="answer"):
            retrieved = await memory.retrieve_context(RetrievalRequest(question))
            write(root / f"{name}-retrieval.json", asdict(retrieved))
            settings = memory.config.retrieval
            toolset = MemoryToolset(memory.retriever, result_limit=settings.tool_result_limit,
                search_limit=settings.tool_search_limit, evidence_budget_tokens=settings.tool_evidence_budget_tokens,
                request=question, initial_evidence=retrieved.evidence)
            qa = OllamaQaClient(memory.config.llm.model, memory.config.llm.url, llm_config=memory.config.llm)
            await qa.llm.client._client.aclose()
            qa.llm = memory.llm
            result = await qa.answer_with_memory_tools(question, toolset)
        row = {"step": name, "question": question, "seconds": time.monotonic() - started,
               "attempts": budget.calls - before, "result": asdict(result)}
        rows.append(row)
        write(root / "steps.json", rows)
        print("ANSWER", name, result.output, flush=True)
        return retrieved

    if resume:
        captured = json.loads((root / "capture-2.json").read_text())
        episode = memory.artifacts.get_episode(captured["episode_ids"][0])
    else:
        first = await memory.ingest_source(SourceInput(**inputs[0]))
        write(root / "capture-1.json", asdict(first))
        result = await build("build-1")
        assert not result.report.failures, "First Build did not complete"

        second = await memory.ingest_source(SourceInput(**inputs[1]))
        write(root / "capture-2.json", asdict(second))
        before_facts = [asdict(f) for f in memory.artifacts.list_consolidated_facts()]
        persist = memory.consolidator.views.persist

        def fail_publication(*args, **kwargs):
            raise OSError("Injected view publication failure for recovery check")

        memory.consolidator.views.persist = fail_publication
        try:
            result = await build("build-2-injected-failure")
        finally:
            memory.consolidator.views.persist = persist
        assert result.report.failures, "Fault injection was not exercised"
        assert [asdict(f) for f in memory.artifacts.list_consolidated_facts()] == before_facts
        episode = memory.artifacts.get_episode(second.episode_ids[0])
        assert episode.extraction_status == "complete" and episode.claim_ids
        retained = [asdict(memory.artifacts.get_claim(cid)) for cid in episode.claim_ids]
        retrieved = await answer("answer-pending", "Why did the Harbor Room opening date change, and who is handling the inspection?")
        assert retrieved.evidence.build_incomplete, "Incomplete Build was not exposed to the agent"

        result = await build("build-2-recovery")
        assert not result.report.failures, "View recovery did not complete"
        assert [memory.artifacts.get_claim(c["claim_id"]).text for c in retained] == [c["text"] for c in retained]
        assert memory.artifacts.get_episode(second.episode_ids[0]).extraction_batches == episode.extraction_batches

    # A frozen structural selection rule exercises a human edit without a model
    # judge or fixture-specific target lookup. Preserve the statement, qualify it.
    claim = memory.artifacts.get_claim(sorted(episode.claim_ids)[0])
    replacement = claim.text + " " + QUALIFIER
    write(root / "correction-input.json", {"claim_id": claim.claim_id, "before": claim.text, "replacement": replacement})
    service = ClaimLifecycleService(memory.artifacts, memory.consolidator.materializer, memory.consolidator.views)
    started, before = time.monotonic(), budget.calls
    with trace_operation("compact_product", step="correction", stage="correction"):
        corrected = await service.correct_claim(claim.claim_id, replacement, reason="Review: qualify this working note")
        if isinstance(corrected, CorrectionPreview):
            write(root / "correction-preview.json", asdict(corrected))
            corrected = await service.correct_claim(claim.claim_id, replacement, reason="Review: qualify this working note",
                draft_id=corrected.draft_id, time_references={t["time_id"]: "unresolved" for t in corrected.times})
    assert memory.artifacts.get_claim(claim.claim_id).status == "superseded"
    assert memory.artifacts.get_claim(corrected.claim_ids[0]).text == replacement
    rows.append({"step": "correction", "seconds": time.monotonic() - started,
                 "attempts": budget.calls - before, "result": asdict(corrected),
                 "snapshot": snapshot(memory, root, "correction")})
    write(root / "steps.json", rows)
    print("CORRECTION", corrected.claim_ids, flush=True)
    retrieved = await answer("answer-current", "What commitments and constraints should we remember when arranging the Harbor Room opening?")
    assert not retrieved.evidence.build_incomplete, "Recovered Build is still reported as incomplete"
    before = budget.calls
    result = await build("build-noop")
    assert not result.report.failures and budget.calls == before, "No-op Build repeated model work"


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", type=Path, help="Resume only the correction/answer after a recorded structural failure")
    args = parser.parse_args()
    prior = json.loads((args.resume / "completion.json").read_text()) if args.resume else None
    seconds = SECONDS - prior["seconds"] if prior else SECONDS
    attempts = ATTEMPTS - prior["metrics"]["attempts"] if prior else ATTEMPTS
    if seconds <= 0 or attempts <= 0:
        raise ValueError("The original allowance is exhausted")
    if args.resume:
        prior_plan = json.loads((args.resume / "plan.json").read_text())
        if prior_plan.get("resume_from") or prior["status"] != "incomplete":
            raise ValueError("Resume is limited to one incomplete original run")
        steps = json.loads((args.resume / "steps.json").read_text())
        if [row["step"] for row in steps] != ["build-1", "build-2-injected-failure", "answer-pending", "build-2-recovery"]:
            raise ValueError("Resume requires completed Build recovery and an unfinished correction")
    original = json.loads((BASELINE / "plan.json").read_text())
    root = fresh_run_root("compact-product-resume" if args.resume else "compact-product")
    root.mkdir(parents=True)
    print("OUTPUT", root, flush=True)
    files = [*Path("mycelium").rglob("*.py"), *Path("mycelium/prompt_templates").rglob("*.jinja"),
             Path(__file__), Path("benchmarks/shared/adapters.py"), Path("benchmarks/shared/model_recording.py")]
    hashes = {}
    for path in files:
        if path.is_absolute():
            path = path.relative_to(Path.cwd())
        target = root / "code" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    write(root / "plan.json", {"seed": original["seed"], "inputs": original["inputs"][:2],
        "budget_seconds": seconds, "max_attempts": attempts, "resume_from": str(args.resume) if args.resume else None,
        "original_completion": prior, "aggregate_budget_seconds": SECONDS, "aggregate_max_attempts": ATTEMPTS,
        "correction": {"target": "First retained claim ID in second episode, sorted", "append": QUALIFIER,
                       "relative_date_review": "Explicitly leave relative anchors unresolved in this simulated edit"},
        "assessment": "Coherent artifacts, durable evidence, visible pending work, practical cost; source review, no judge",
        "limits": "Repeated known inputs, changed pipeline/segmentation, no matched control or fresh holdout; simulated edit and failure",
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "code_sha256": hashes})
    if args.resume:
        copy_seed(args.resume / "snapshots/final/store", root / "store")
        shutil.copyfile(args.resume / "capture-2.json", root / "capture-2.json")
    else:
        copy_seed(Path(original["seed"]), root / "store")
    os.environ["MYCELIUM_LLM_DEBUG_DIR"] = str(root / "structured")
    rows, status = [], "incomplete"
    with Mycelium(root / "store", config_path="mycelium.toml", memory_profile="none") as memory:
        write(root / "config.json", asdict(memory.config))
        if args.resume and asdict(memory.config) != json.loads((args.resume / "config.json").read_text()):
            raise ValueError("Resuming requires identical model configuration")
        write(root / "models.json", (await memory.llm.client.list()).model_dump(mode="json"))
        snapshot(memory, root, "seed")
        sdk = memory.llm.client
        memory.llm.client = BudgetClient(RecordingClient(sdk, root / "requests"), seconds, attempts)
        started = time.monotonic()
        try:
            async with asyncio.timeout(seconds):
                await exercise(memory, root, original["inputs"][:2], rows, resume=bool(args.resume))
            status = "complete"
        except (Exception, asyncio.CancelledError) as exc:
            write(root / "error.json", {"error": f"{type(exc).__name__}: {exc}"})
            print("ERROR", type(exc).__name__, str(exc), flush=True)
        finally:
            elapsed = time.monotonic() - started
            snapshot(memory, root, "final")
            await sdk._client.aclose()
            write(root / "completion.json", {"status": status, "seconds": elapsed,
                "steps_completed": len(rows), "metrics": metrics(root), "assessment": "requires_source_review",
                "aggregate_seconds": elapsed + (prior["seconds"] if prior else 0),
                "aggregate_attempts": memory.llm.client.calls + (prior["metrics"]["attempts"] if prior else 0)})
            print("COMPLETE", status, metrics(root), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
