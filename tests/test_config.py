from engram.config import EngramConfig
from mycelium.config import Config


def test_store_paths_are_owned_by_runtime_and_engram_config(tmp_path):
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text("", encoding="utf-8")

    config = Config.from_toml(config_path)
    engram_config = EngramConfig.from_toml(config_path)

    assert not hasattr(config, "store_path")
    assert engram_config.store_path == EngramConfig().store_path


def test_retrieval_embedding_and_candidate_limit_are_configurable(tmp_path):
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text(
        '[retrieval]\nembedding_model = "embeddinggemma:test"\ncandidate_limit = 12\n',
        encoding="utf-8",
    )

    config = Config.from_toml(config_path)

    assert config.retrieval.embedding_model == "embeddinggemma:test"
    assert config.retrieval.candidate_limit == 12


def test_agentic_retrieval_bounds_are_configurable(tmp_path):
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text(
        "[retrieval]\n"
        "initial_result_limit = 3\n"
        "tool_result_limit = 4\n"
        "tool_search_limit = 2\n"
        "tool_evidence_budget_tokens = 4096\n",
        encoding="utf-8",
    )

    retrieval = Config.from_toml(config_path).retrieval

    assert retrieval.initial_result_limit == 3
    assert retrieval.tool_result_limit == 4
    assert retrieval.tool_search_limit == 2
    assert retrieval.tool_evidence_budget_tokens == 4096


def test_gemma_sampling_and_reasoning_settings_reach_runtime(tmp_path):
    from mycelium import Mycelium
    path = tmp_path / 'config.toml'
    path.write_text('[llm]\ntemperature=0.8\ntop_p=0.9\ntop_k=40\n'
                    'context_window_tokens=65536\nreasoning_output_tokens=24576\n'
                    'reasoning_enabled=true\nreasoning_format="native"\ntimeout_seconds=700\n')
    memory = Mycelium(tmp_path / 'store', config_path=path)
    llm = memory.llm
    assert (llm.temperature, llm.top_p, llm.top_k) == (0.8, 0.9, 40)
    assert (llm.reasoning_output_tokens, llm.reasoning_format, llm.timeout) == (24576, 'native', 700)
    assert llm.output_budget(8192, think=True) == 24576
    assert llm.context_window_tokens == 65536


def test_reasoning_configuration_rejects_invalid_contract_values():
    import pytest
    from mycelium.config import LLMConfig
    for values in ({'reasoning_enabled': 'false'}, {'reasoning_output_tokens': 0}, {'reasoning_format': 'fallback'}):
        with pytest.raises(ValueError):
            LLMConfig(**values)
