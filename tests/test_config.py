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
