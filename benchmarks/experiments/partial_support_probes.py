"""Direct proof that withdrawn support does not hide remaining active evidence."""

import asyncio
from dataclasses import asdict
from pathlib import Path

from benchmarks.experiments.identity_boundary_pipeline import source_claim
from benchmarks.experiments.probe_support import fresh_run_root, write
from benchmarks.shared.model_recording import RecordingClient
from mycelium import Mycelium
from mycelium.truth_review import TruthReviewer


async def main():
    root = fresh_run_root("partial-support-contract")
    print("OUTPUT", root, flush=True)
    root.mkdir(parents=True)
    (root / "probe.py").write_text(Path(__file__).read_text())
    results = []
    with Mycelium(root / "store", config_path="mycelium.toml") as memory:
        memory.llm.client = RecordingClient(memory.llm.client, root / "requests")
        memory.llm.trace_path = root / "calls.jsonl"
        write(root / "config.json", asdict(memory.config))
        write(root / "models.json", (await memory.llm.client.list()).model_dump())
        for name, original, corroboration, updated, expected in [
            (
                "retained_corroboration",
                "Mara will deliver the sculpture Friday.",
                "Mara will deliver the sculpture Friday.",
                "Mara corrected the sculpture delivery: Monday replaces Friday.",
                "right_supersedes_left",
            ),
            (
                "withdrawn_detail",
                "The museum opens Tuesday.",
                "The museum has a sculpture courtyard.",
                "The museum opens Wednesday.",
                "no_change",
            ),
            (
                "independent_support",
                "Mara is restoring a violin.",
                "Mara is restoring a violin.",
                "Mara bought a bicycle.",
                "no_change",
            ),
        ]:
            old, left = source_claim(memory.artifacts, name + "-old", original)
            active, support = source_claim(
                memory.artifacts, name + "-active", corroboration
            )
            _, right = source_claim(memory.artifacts, name + "-new", updated)
            old.status = "retracted"
            old.retracted_at = "2031-05-07"
            old.retraction_reason = "Withdrawn source; independent support remains."
            memory.artifacts.save_source(old)
            left.provenance.extend(support.provenance)
            memory.artifacts.save_claim(left)
            reviewer = TruthReviewer(memory.llm, memory.artifacts)
            records = reviewer._records({c.claim_id: c for c in (left, right)}, {}, {})
            write(root / f"{name}-inputs.json", records)
            pair = (left.claim_id, right.claim_id)
            decision = (await reviewer._compare_pairs([pair], records))[pair]
            row = dict(
                case=name,
                expected=expected,
                decision=decision,
                passed=decision["relation"] == expected,
            )
            results.append(row)
            write(root / "results.json", results)
            print(row, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
