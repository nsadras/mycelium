"""Public benchmark command routing without model calls."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from benchmarks import __main__ as cli
from benchmarks.shared.cli import default_run_id
from benchmarks.suites.daily_driver import run as daily_run


def test_timestamped_run_name():
    name = default_run_id("locomo", "mycelium")
    datetime.strptime(name.removeprefix("locomo-mycelium-"), "%Y%m%d-%H%M%S")


@pytest.mark.parametrize("command", [
    [], ["locomo"], ["mab"], ["daily-driver"],
    ["daily-driver", "validate"], ["daily-driver", "run"],
    ["daily-driver", "compare"],
])
def test_help(command, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([*command, "--help"])
    assert exc.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_locomo_dispatch(monkeypatch, tmp_path):
    system = object()
    monkeypatch.setattr(cli, "build_memory_system", lambda **kwargs: system)
    runner = AsyncMock(return_value={})
    monkeypatch.setattr(cli, "run_locomo", runner)
    cli.main(["locomo", "--output-root", str(tmp_path), "--run-id", "chosen",
              "--sample-index", "3", "--max-sessions", "2", "--snapshot-sessions"])
    args = runner.call_args.kwargs
    assert args["output_dir"] == tmp_path / "chosen"
    assert args["sample_index"] == 3
    assert args["max_sessions"] == 2
    assert args["snapshot_sessions"] is True
    assert args["system"] is system


def test_mab_dispatch(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "build_memory_system", lambda **kwargs: object())
    runner = AsyncMock(return_value={})
    monkeypatch.setattr(cli, "run_memoryagentbench", runner)
    cli.main(["mab", "--dataset-config", "dataset.yaml", "--max-contexts", "1",
              "--max-queries", "3", "--output-root", str(tmp_path)])
    args = runner.call_args.kwargs
    assert args["dataset_config_path"] == Path("dataset.yaml")
    assert args["max_contexts"] == 1
    assert args["max_queries"] == 3
    assert args["output_dir"].parent == tmp_path


@pytest.mark.parametrize("custom", [False, True])
def test_daily_trials_output_and_replay(monkeypatch, tmp_path, custom):
    runner = AsyncMock(return_value={})
    monkeypatch.setattr(daily_run, "run_daily_driver_trials", runner)
    args = ["daily-driver", "run", "scenario", "--output-root", str(tmp_path),
            "--trials", "3", "--replay-extraction-store", "saved/store", "--skip-probe-answers"]
    if custom:
        args += ["--run-id", "chosen"]
    cli.main(args)
    call = runner.call_args
    assert call.args[0] == Path("scenario")
    assert call.args[1].parent == tmp_path
    if custom:
        assert call.args[1].name == "chosen"
    else:
        assert call.args[1].name.startswith("daily-driver-scenario-")
    assert call.kwargs["trials"] == 3
    assert call.kwargs["replay_extraction_store"] == Path("saved/store")
    assert call.kwargs["run_probe_answers"] is False


def test_daily_compare_existing_directory(monkeypatch, tmp_path):
    calls = []
    def compare(*args, **kwargs):
        calls.append(args)
        return {"comparison": {"source_accounting": {}, "projection": {}}, "evaluation": {"summary": {}}}
    monkeypatch.setattr(daily_run, "refresh_daily_driver_comparison", compare)
    cli.main(["daily-driver", "compare", "scenario", "--output-dir", str(tmp_path)])
    assert calls == [(Path("scenario"), tmp_path)]
