"""Replay frozen daily checkpoints with ranked claims and no generative admission.

Extraction, canonical reviews, identity metadata and source policy are shared.
This isolates retrieval/presentation; it is not an end-to-end Mem0 benchmark.
"""

import argparse
import asyncio
import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.probe_support import write
from benchmarks.shared.model_recording import RecordingClient
from benchmarks.shared.run_tracking import begin_invocation, recorded_run
from benchmarks.suites.daily_driver.eval import probe_judgment_specification
from benchmarks.suites.daily_driver.run import _run_checkpoint_probes
from mycelium import Mycelium
from mycelium.config import Config
from mycelium.operations import RetrievalResult
from mycelium.retrieval_context import RetrievedContextBuilder
from mycelium.evidence_rendering import render_memory_evidence


class ClaimContextBuilder(RetrievedContextBuilder):
    def _facts_for_claim(self, claim_id):
        # Keep canonical state, reviews, citations and source excerpts; omit the
        # generated consolidation layer in this benchmark-only control.
        return []


async def retrieve_ranked_claims(retriever, request):
    budget = request.budget_tokens
    if budget is None:
        budget = retriever.default_budget_tokens
    hits = await retriever.claim_index.search(
        await retriever._search_query(request.query)
    )
    builder = ClaimContextBuilder(retriever.context_builder.wiki, retriever.artifacts)
    current = [
        row
        for hit in hits
        if (row := builder.current_hit(hit)) is not None and row.memory_tier != "source"
    ]
    # A generated fact can bundle many claims. A five-record cap would give this
    # control less evidence by construction. Match candidate and token budgets,
    # and let ranked canonical records fill the same available context.
    selected = builder.distinct_hits(current, retriever.claim_index.candidate_limit)
    evidence = builder.build(
        selected, budget_tokens=budget, more_available=len(current) > len(selected)
    )
    return RetrievalResult(
        (),
        evidence,
        render_memory_evidence(evidence),
        {
            "strategy": "ranked_canonical_claims_without_generative_admission",
            "candidate_limit": retriever.claim_index.candidate_limit,
            "candidates": [
                dict(rank=i, claim_id=hit.claim_id, score=hit.score)
                for i, hit in enumerate(current, 1)
            ],
            "selected_claim_ids": [hit.claim_id for hit in selected],
            "rendered_claim_ids": list(evidence.claim_ids),
        },
    )


def required_digests(models, config):
    inventory = {row["model"]: row["digest"] for row in models["models"]}
    requested = (config.llm.model, config.retrieval.embedding_model)
    return {
        name: inventory[name if ":" in name else name + ":latest"] for name in requested
    }


@recorded_run
async def run(source_run, output, config_path):
    config = Config.from_toml(config_path)
    expected_config = json.loads((source_run / "configuration.json").read_text())
    if asdict(config) != expected_config:
        raise ValueError(
            "Baseline requires the original run's exact effective settings"
        )
    original = json.loads((source_run / "run_manifest.json").read_text())
    if original["execution_status"] == "running":
        raise ValueError(
            "Wait for a terminal production run before comparing snapshots"
        )
    if original.get("probe_judgment") != probe_judgment_specification():
        raise ValueError("Baseline requires the same answer judgment contract")
    fixture = json.loads((source_run / "fixture.json").read_text())
    prior_models = json.loads((source_run / "models.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "status": "running",
        "execution_status": "running",
        "qa_status": "running",
        "encoding_status": "shared",
        "source_run": str(source_run.resolve()),
        "source_run_state": original,
        "effective_config": asdict(config),
        "shared_work": "extraction, source policy, canonical reviews and identity metadata",
        "fresh_work": "claim index construction, ranking, direct claim rendering, QA and evaluation",
        "context_policy": "Same candidate and token budgets; ranked claims fill context without a generated-fact count cap.",
        "limitations": "Conditional retrieval/presentation comparison, not standalone ingestion or an external Mem0 implementation. First snapshot queries rebuild cold indexes; document/query embedding traces distinguish this work, but raw latency is not a matched warm-index comparison.",
        "probe_judgment": probe_judgment_specification(),
        "snapshots": {},
    }
    write(output / "run_manifest.json", manifest)
    write(output / "configuration.json", asdict(config))
    write(output / "fixture.json", fixture)
    begin_invocation(output)
    rows = []
    for checkpoint in sorted((source_run / "checkpoints").iterdir()):
        snapshot_path = checkpoint / "snapshot.json"
        if not snapshot_path.exists():
            continue
        directory = output / "checkpoints" / checkpoint.name
        directory.mkdir(parents=True)
        snapshot = json.loads(snapshot_path.read_text())
        write(directory / "snapshot.json", snapshot)
        manifest["snapshots"][checkpoint.name] = hashlib.sha256(
            (checkpoint / "store" / "memory.sqlite3").read_bytes()
        ).hexdigest()
        write(output / "run_manifest.json", manifest)
        shutil.copytree(
            checkpoint / "store",
            directory / "store",
            ignore=shutil.ignore_patterns("diagnostics", "indexes", ".writer.lock"),
        )
        with Mycelium(
            directory / "store", config=config, memory_profile="user"
        ) as memory:
            models = (await memory.llm.client.list()).model_dump(mode="json")
            if required_digests(models, config) != required_digests(
                prior_models, config
            ):
                raise ValueError(
                    "Configured model weights differ from the production run"
                )
            write(directory / "models.json", models)
            memory.llm.trace_path = directory / "judge-calls.jsonl"
            memory.llm.client = RecordingClient(
                memory.llm.client, directory / "judge-requests"
            )

            async def retrieve(request):
                return await retrieve_ranked_claims(memory.retriever, request)

            memory.retrieve_context = retrieve
            results = await _run_checkpoint_probes(
                fixture,
                memory,
                checkpoint.name,
                snapshot,
                run_answers=True,
                result_path=directory / "probes.json",
            )
            rows.extend(results)
            print(
                checkpoint.name,
                [(r["probe_id"], r["status"]) for r in results],
                flush=True,
            )
    failed = [r for r in rows if r["status"] != "complete"]
    manifest.update(
        status="failed" if failed else "complete",
        execution_status="failed" if failed else "complete",
        qa_status="incomplete" if failed else "complete",
        failed_probe_ids=[r["probe_id"] for r in failed],
    )
    write(output / "run_manifest.json", manifest)
    write(output / "results.json", rows)
    print("OUTPUT", output, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config-path", type=Path, default=Path("mycelium.toml"))
    args = parser.parse_args()
    asyncio.run(run(args.source_run, args.output, args.config_path))
