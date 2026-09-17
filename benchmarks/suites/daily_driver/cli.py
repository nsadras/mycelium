"""Daily-driver commands for the benchmark CLI."""

import argparse
import json
from pathlib import Path

from benchmarks.suites.daily_driver.fixture import validate_fixture


def add_args(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("fixture_dir", type=Path)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("fixture_dir", type=Path)
    run_parser.add_argument("--output-root", type=Path, default=Path("benchmark_runs"))
    run_parser.add_argument(
        "--run-id", help="Run name (default: daily-driver-<fixture>-YYYYMMDD-HHMMSS)."
    )
    run_parser.add_argument("--config-path", type=Path, default=Path("mycelium.toml"))
    run_parser.add_argument(
        "--replay-extraction-store",
        type=Path,
        help=(
            "Reuse only source, episode, claim, and raw-log extraction artifacts; "
            "rerun Dream, review actions, projection, retrieval, and answers."
        ),
    )
    run_parser.add_argument(
        "--skip-probe-answers",
        action="store_true",
        help="Run deterministic retrieval probes but skip answer generation and judging.",
    )
    run_parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Run independent end-to-end trials into trial-NN subdirectories.",
    )
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("fixture_dir", type=Path)
    compare_parser.add_argument("--output-dir", type=Path, required=True)
    compare_parser.add_argument(
        "--config-path", type=Path, default=Path("mycelium.toml")
    )
    review_parser = subparsers.add_parser(
        "review",
        help="Export source-linked inputs and successive snapshot changes for review.",
    )
    review_parser.add_argument("fixture_dir", type=Path)
    review_parser.add_argument("--run-dir", type=Path, required=True)
    review_parser.add_argument("--output-dir", type=Path, required=True)


def dispatch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.command == "review":
        from benchmarks.suites.daily_driver.source_review import export_source_review

        print(
            json.dumps(
                export_source_review(args.fixture_dir, args.run_dir, args.output_dir),
                indent=2,
            )
        )
        return
    if args.command == "run":
        from benchmarks.shared.cli import default_run_id

        args.output_dir = args.output_root / (
            args.run_id or default_run_id("daily-driver", args.fixture_dir.name)
        )
    if args.command == "validate":
        print(
            json.dumps(validate_fixture(args.fixture_dir), indent=2, ensure_ascii=False)
        )
    elif args.command == "run":
        import asyncio

        from benchmarks.suites.daily_driver.run import (
            run_daily_driver,
            run_daily_driver_trials,
        )

        if args.trials < 1:
            parser.error("--trials must be at least 1")
        if args.trials > 1:
            summary = asyncio.run(
                run_daily_driver_trials(
                    args.fixture_dir,
                    args.output_dir,
                    trials=args.trials,
                    config_path=args.config_path,
                    replay_extraction_store=args.replay_extraction_store,
                    run_probe_answers=not args.skip_probe_answers,
                )
            )
            summary = {"output_dir": str(args.output_dir), **summary}
        else:
            result = asyncio.run(
                run_daily_driver(
                    args.fixture_dir,
                    args.output_dir,
                    config_path=args.config_path,
                    replay_extraction_store=args.replay_extraction_store,
                    run_probe_answers=not args.skip_probe_answers,
                )
            )
            summary = {
                "output_dir": result["output_dir"],
                "model": result["run"]["model"],
                "source_accounting": result["comparison"]["source_accounting"],
                "claim_comparison": {
                    key: value
                    for key, value in result["comparison"]["claim_comparison"].items()
                    if key != "rows"
                },
                "evaluation": result["evaluation"]["summary"],
            }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    elif args.command == "compare":
        from benchmarks.suites.daily_driver.run import (
            refresh_daily_driver_comparison,
        )

        refreshed = refresh_daily_driver_comparison(
            args.fixture_dir,
            args.output_dir,
            config_path=args.config_path,
        )
        print(
            json.dumps(
                {
                    "output_dir": str(args.output_dir),
                    "source_accounting": refreshed["comparison"]["source_accounting"],
                    "projection": refreshed["comparison"]["projection"],
                    "evaluation": refreshed["evaluation"]["summary"],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
