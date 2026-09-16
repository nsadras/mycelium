"""Exercise configuration through public constructors and command routing."""

import json
import sys
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from benchmarks import __main__ as cli
from benchmarks.shared.adapters import build_memory_system
from benchmarks.shared.provenance import effective_configuration
from benchmarks.suites import locomo, mab
from benchmarks.suites.daily_driver import run as daily_run
from mycelium import Mycelium
from mycelium.config import Config, LLMConfig


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "mycelium.toml"
    path.write_text(
        '[llm]\nmodel="file-model"\nurl="http://file-host:11434"\n'
        'temperature=0.6\ntop_p=0.8\ntop_k=32\ntimeout_seconds=111\n'
        'context_window_tokens=12345\nreasoning_enabled=false\n'
        'reasoning_output_tokens=321\nreasoning_format="native"\n'
        '[session]\ncontext_budget_tokens=1234\n'
        '[retrieval]\nembedding_model="file-embedding"\ncandidate_limit=11\n'
    )
    return path


@pytest.mark.parametrize("name", ["model", "url"])
@pytest.mark.parametrize("value", [None, 0, False, [], "", "   "])
def test_model_settings_reject_non_string_and_blank_values(name, value):
    with pytest.raises(ValueError):
        LLMConfig(**{name: value})


@pytest.mark.parametrize("value", [True, 1.5, 0, -1, "1024"])
def test_library_validates_overrides_before_creating_store(tmp_path, value):
    store = tmp_path / "store"
    with pytest.raises(ValueError):
        Mycelium(store, context_budget_tokens=value)
    assert not store.exists()


def test_library_copies_and_validates_explicit_configuration(tmp_path, config_path):
    config = Config.from_toml(config_path)
    memory = Mycelium(tmp_path / "store", config=config, ollama_model="override")
    try:
        config.llm.temperature = 0.2
        config.retrieval.candidate_limit = 2
        assert memory.llm.model == "override"
        assert memory.llm.temperature == 0.6
        assert memory.config.retrieval.candidate_limit == 11
        assert config.llm.model == "file-model"
    finally:
        memory.close()
    with pytest.raises(ValueError, match="config.*config_path"):
        Mycelium(tmp_path / "invalid", config=config, config_path=config_path)


@pytest.mark.parametrize("command", ["locomo", "mab"])
@pytest.mark.parametrize("overrides", [False, True])
def test_benchmark_cli_effective_configuration(monkeypatch, tmp_path, config_path, command, overrides):
    async def inspect(**kwargs):
        system = kwargs["system"]
        expected = Config.from_toml(config_path)
        if overrides:
            expected.llm.model = "cli-memory"
            expected.llm.url = "http://cli-host:11434"
            expected.context_budget_tokens = 777
        qa_model = "cli-qa" if overrides else expected.llm.model
        captured = effective_configuration(system)
        assert captured["memory"] == asdict(expected)
        assert captured["qa"] == {**asdict(expected.llm), "model": qa_model}
        # A run owns its settings even if the input file is removed or edited.
        config_path.unlink()
        for case in ("one", "two"):
            await system.reset(case)
            memory = system.mem
            assert system.stats()["effective_config"] == captured["memory"]
            assert memory.llm.model == expected.llm.model
            assert memory.llm.url == expected.llm.url
            assert memory.llm.timeout == 111
            assert memory.llm.reasoning_enabled is False
            assert memory.retriever.claim_index.embedder.model == "file-embedding"
            assert memory.retriever.default_budget_tokens == expected.context_budget_tokens
        system.mem.close()
        assert effective_configuration(system) == captured
        return {}

    monkeypatch.setattr(cli, "run_locomo" if command == "locomo" else "run_memoryagentbench", inspect)
    args = [command, "--config-path", str(config_path), "--output-root", str(tmp_path)]
    if command == "mab":
        args += ["--dataset-config", "unused.yaml"]
    if overrides:
        args += ["--qa-model", "cli-qa", "--memory-model", "cli-memory",
                 "--ollama-url", "http://cli-host:11434", "--context-budget-tokens", "777"]
    cli.main(args)


@pytest.mark.parametrize("system_name", ["mycelium", "full_wiki", "null", "full_context", "gold_evidence"])
def test_benchmark_defaults_and_invalid_qa_override(tmp_path, monkeypatch, system_name):
    monkeypatch.chdir(tmp_path)  # No implicit dependency on the repository TOML.
    options = dict(system_name=system_name, run_dir=tmp_path, qa_model=None,
                   memory_model=None, ollama_url=None, config_path=None,
                   context_budget_tokens=None, dream_policy="none")
    system = build_memory_system(**options)
    assert effective_configuration(system)["qa"] == asdict(LLMConfig())
    for name in ("qa_model", "memory_model", "ollama_url"):
        with pytest.raises(ValueError):
            build_memory_system(**{**options, name: ""})


@pytest.mark.asyncio
async def test_locomo_resume_rejects_changed_effective_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(locomo, "model_inventory", AsyncMock(return_value={}))
    data = tmp_path / "data.json"
    data.write_text("[]")
    output = tmp_path / "run"
    options = dict(system_name="null", run_dir=output, qa_model=None,
                   memory_model=None, ollama_url="http://first-host:11434", config_path=None,
                   context_budget_tokens=None, dream_policy="none")
    await locomo.run_locomo(data_path=data, output_dir=output,
                            system=build_memory_system(**options), prediction_key="test")
    manifest = json.loads((output / "run_manifest.json").read_text())
    assert manifest["settings"]["effective_config"]["qa"]["url"] == options["ollama_url"]
    journal = (output / "invocations.jsonl").read_bytes()
    options["ollama_url"] = "http://second-host:11434"
    with pytest.raises(ValueError, match="settings differ"):
        await locomo.run_locomo(data_path=data, output_dir=output,
                                system=build_memory_system(**options), prediction_key="test")
    assert (output / "invocations.jsonl").read_bytes() == journal


@pytest.mark.asyncio
async def test_daily_driver_trials_share_captured_config(tmp_path, config_path, monkeypatch):
    configs = []

    async def run(fixture_dir, output_dir, **kwargs):
        configs.append(asdict(kwargs["config"]))
        config_path.write_text('[llm]\nmodel="changed"\n')
        return {"run": {"scenario_id": "test", "extraction_mode": "fresh"},
                "evaluation": {"dimensions": [], "gates": []}, "output_dir": str(output_dir)}

    monkeypatch.setattr(daily_run, "run_daily_driver", run)
    expected = asdict(Config.from_toml(config_path))
    await daily_run.run_daily_driver_trials(tmp_path / "fixture", tmp_path / "trials",
                                            config_path=config_path, trials=3)
    assert configs == [expected] * 3


def test_server_runtime_uses_requested_file_and_store(tmp_path, config_path, monkeypatch):
    from server import runtime

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MYCELIUM_STORE", str(tmp_path / "server-store"))
    monkeypatch.setattr(runtime, "_mem", None)
    memory = runtime.get_mem()
    try:
        assert memory.store_path == tmp_path / "server-store"
        assert asdict(memory.config) == asdict(Config.from_toml(config_path))
        assert memory.llm.model == "file-model"
        assert memory.llm.reasoning_enabled is False
        assert runtime.get_mem() is memory
    finally:
        memory.close()


@pytest.mark.parametrize("override_summary", [False, True])
def test_server_engram_config_reaches_summary_client(tmp_path, config_path, monkeypatch, override_summary):
    from engram.config import EngramConfig
    from server import runtime

    with config_path.open("a") as stream:
        stream.write('[engram]\nstore_path="recordings"\nmax_upload_bytes=4321\n'
                     '[engram.whisper]\nmodel="tiny"\nbatch_size=2\n'
                     '[engram.diarization]\nhf_token="file-test-token"\n')
        if override_summary:
            stream.write('[engram.summary]\nmodel="summary-model"\n'
                         'url="http://summary-host:11434"\n'
                         'context_window_tokens=5678\ntemperature=0.7\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HF_TOKEN", "environment-test-token")
    monkeypatch.setattr(runtime, "_engram", None)
    service = runtime.get_engram()
    config = service.config
    assert config == EngramConfig.from_toml(config_path)
    assert config.hf_token == "environment-test-token"
    assert config.audio_dir == config.store_path / "audio"
    assert config.max_upload_bytes == 4321
    assert config.whisper_model == "tiny"
    assert config.whisper_batch_size == 2
    llm = service.summarizer_factory().llm
    assert llm.model == ("summary-model" if override_summary else "file-model")
    assert llm.url == ("http://summary-host:11434" if override_summary else "http://file-host:11434")
    assert llm.context_window_tokens == (5678 if override_summary else 12345)
    assert llm.temperature == (0.7 if override_summary else EngramConfig.summary_temperature)


@pytest.mark.asyncio
async def test_daily_run_records_configuration_and_closes_store(tmp_path, config_path, monkeypatch):
    fixture = {"scenario": {"scenario_id": "test", "user": {"name": "User"}, "episodes": []}}
    monkeypatch.setattr(daily_run, "validate_fixture", lambda _: None)
    monkeypatch.setattr(daily_run, "load_fixture", lambda _: fixture)
    monkeypatch.setattr(daily_run, "compare_final", lambda *_: {})
    monkeypatch.setattr(daily_run, "evaluate_run", lambda *_: {})
    monkeypatch.setattr(daily_run, "_report_markdown", lambda *_: "")
    instances = []

    def memory(*args, **kwargs):
        instances.append(Mycelium(*args, **kwargs))
        return instances[-1]

    monkeypatch.setattr(daily_run, "Mycelium", memory)
    output = tmp_path / "run"
    result = await daily_run.run_daily_driver(tmp_path, output, config_path=config_path)
    expected = asdict(Config.from_toml(config_path))
    assert result["run"]["effective_config"] == expected
    assert json.loads((output / "configuration.json").read_text()) == expected
    assert json.loads((output / "run.json").read_text())["effective_config"] == expected
    assert instances[0]._closed


@pytest.mark.asyncio
async def test_mab_records_effective_configuration(tmp_path, config_path, monkeypatch):
    monkeypatch.setattr(mab, "install_editdistance_shim", lambda: None)
    monkeypatch.setattr(mab, "ensure_nltk_tokenizers", lambda: None)
    creator = SimpleNamespace(get_chunks=lambda: [], get_query_and_answers=lambda: [])
    monkeypatch.setitem(sys.modules, "conversation_creator", SimpleNamespace(ConversationCreator=lambda *_: creator))
    monkeypatch.setitem(sys.modules, "utils.eval_other_utils", SimpleNamespace(metrics_summarization=None))
    dataset = tmp_path / "data.yaml"
    dataset.write_text("{}")
    output = tmp_path / "run"
    system = build_memory_system(system_name="mycelium", run_dir=output,
                                 qa_model="qa-model", memory_model=None, ollama_url=None,
                                 config_path=config_path, context_budget_tokens=None, dream_policy="none")
    await mab.run_memoryagentbench(mab_root=tmp_path, dataset_config_path=dataset,
                                   output_dir=output, system=system)
    assert json.loads((output / "configuration.json").read_text()) == effective_configuration(system)
