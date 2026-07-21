from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def summarize_run(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "summary.json"
    predictions_path = run_dir / "predictions.json"
    if not summary_path.exists() or not predictions_path.exists():
        return {}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    stats = predictions[0].get("system_stats", {}) if predictions else {}
    stores = list((run_dir / "stores").glob("*")) if (run_dir / "stores").exists() else []
    wiki_files = [path for store in stores for path in (store / "wiki").glob("*.md") if path.name != "_index.md"]
    wiki_chars = sum(len(path.read_text(encoding="utf-8")) for path in wiki_files)
    coverage = dict(stats.get("artifact_coverage", {}))
    for key in ("unassigned_segment_ids", "unassigned_claim_ids", "unresolved_provenance_ids", "failed_episode_ids"):
        if isinstance(coverage.get(key), list):
            coverage[f"{key.removesuffix('_ids')}_count"] = len(coverage[key])
            del coverage[key]
    return {
        "run": run_dir.name,
        "score": summary.get("mean_score"),
        "questions": summary.get("count"),
        "wiki_pages": len(wiki_files),
        "wiki_chars": wiki_chars,
        "chars_per_page": round(wiki_chars / len(wiki_files), 1) if wiki_files else 0,
        "memory_construction_seconds": stats.get("memory_construction_seconds"),
        "errors": len(stats.get("errors", [])),
        "dream_failures": len(stats.get("dream_failures", [])),
        "artifact_coverage": coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize LoCoMo evidence-mode ablations.")
    parser.add_argument("--output-root", type=Path, default=Path("benchmark_runs"))
    parser.add_argument("--run-tag", required=True)
    args = parser.parse_args()
    rows = [
        row for path in sorted(args.output_root.glob(f"locomo-mycelium-convo-*-{args.run_tag}-*"))
        if (row := summarize_run(path))
    ]
    result = {"run_tag": args.run_tag, "runs": rows}
    output = args.output_root / f"ablation-{args.run_tag}.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
