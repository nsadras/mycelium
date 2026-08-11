from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from benchmarks.mycelium_bench.adapters import build_memory_system, run_async
from benchmarks.mycelium_bench.locomo import run_locomo
from benchmarks.mycelium_bench.mab import run_memoryagentbench


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.mycelium_bench")
    subparsers = parser.add_subparsers(dest="benchmark", required=True)

    locomo = subparsers.add_parser("locomo", help="Run LoCoMo QA benchmark.")
    add_common_args(locomo)
    locomo.add_argument("--locomo-path", type=Path, default=Path("../locomo/data/locomo10.json"))
    locomo.add_argument("--max-samples", type=int, default=None)
    locomo.add_argument("--max-questions", type=int, default=None)
    locomo.add_argument(
        "--questions-per-category",
        type=int,
        default=None,
        help="Run the first N questions in each category as a balanced diagnostic panel.",
    )
    locomo.add_argument("--sample-index", type=int, default=None, help="Run one 1-based LoCoMo sample index.")

    mab = subparsers.add_parser("mab", help="Run MemoryAgentBench through its data/metric utilities.")
    add_common_args(mab)
    mab.add_argument("--mab-root", type=Path, default=Path("../MemoryAgentBench"))
    mab.add_argument("--dataset-config", type=Path, required=True)
    mab.add_argument("--max-contexts", type=int, default=None)
    mab.add_argument("--max-queries", type=int, default=None)

    args = parser.parse_args()
    run_id = args.run_id or default_run_id(args.benchmark, args.system)
    output_dir = args.output_root / run_id
    system = build_memory_system(
        system_name=args.system,
        run_dir=output_dir,
        qa_model=args.qa_model,
        memory_model=args.memory_model or args.qa_model,
        ollama_url=args.ollama_url,
        config_path=args.config_path,
        context_budget_tokens=args.context_budget_tokens,
        dream_policy=args.dream_policy,
        replay_store=args.replay_store,
        replay_assignments=args.replay_assignments,
        frozen_store=args.frozen_store,
        include_retrieval_context=args.include_retrieval_context,
    )

    if args.benchmark == "locomo":
        summary = run_async(
            run_locomo(
                data_path=args.locomo_path,
                output_dir=output_dir,
                system=system,
                prediction_key=args.prediction_key or f"{args.system}_prediction",
                max_samples=args.max_samples,
                max_questions=args.max_questions,
                questions_per_category=args.questions_per_category,
                sample_index=args.sample_index,
            )
        )
    elif args.benchmark == "mab":
        summary = run_async(
            run_memoryagentbench(
                mab_root=args.mab_root,
                dataset_config_path=args.dataset_config,
                output_dir=output_dir,
                system=system,
                max_contexts=args.max_contexts,
                max_queries=args.max_queries,
            )
        )
    else:
        raise ValueError(f"Unsupported benchmark: {args.benchmark}")

    print(json.dumps(summary, indent=2, ensure_ascii=False))


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--system", choices=["mycelium", "null", "full_context", "full_wiki"], default="mycelium")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-root", type=Path, default=Path("benchmark_runs"))
    parser.add_argument("--qa-model", default="gemma4:latest")
    parser.add_argument("--memory-model", default=None)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--config-path", type=Path, default=None)
    parser.add_argument("--context-budget-tokens", type=int, default=32768)
    parser.add_argument("--dream-policy", choices=["none", "per-batch", "per-case"], default="per-batch")
    parser.add_argument("--prediction-key", default=None)
    parser.add_argument(
        "--replay-store",
        type=Path,
        default=None,
        help="Reuse frozen source, episode, claim, and log artifacts instead of extracting again.",
    )
    parser.add_argument(
        "--frozen-store",
        type=Path,
        default=None,
        help="Copy an exact completed store and benchmark retrieval/answering only.",
    )
    parser.add_argument(
        "--replay-assignments",
        action="store_true",
        help="Preserve fixture claim-to-page assignments and benchmark projection only.",
    )
    parser.add_argument(
        "--include-retrieval-context",
        action="store_true",
        help="Persist rendered benchmark context for qualitative inspection.",
    )


def default_run_id(benchmark: str, system: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{benchmark}-{system}-{stamp}"


if __name__ == "__main__":
    main()
