from dataclasses import fields

from engram.config import EngramConfig
from mycelium.config import Config, DreamConfig, LLMConfig


def test_config_surface_contains_only_runtime_settings():
    assert {field.name for field in fields(LLMConfig)} == {
        "url",
        "model",
        "temperature",
        "timeout_seconds",
        "context_window_tokens",
    }
    assert {field.name for field in fields(DreamConfig)} == {
        "main_page_claim_limit",
        "queue_claim_threshold",
        "max_pending_hours",
        "deferred_revisit_hours",
        "lifecycle_poll_seconds",
    }
    assert {field.name for field in fields(Config)} == {
        "context_budget_tokens",
        "llm",
        "dream",
    }


def test_store_paths_are_owned_by_runtime_and_engram_config(tmp_path):
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text("", encoding="utf-8")

    config = Config.from_toml(config_path)
    engram_config = EngramConfig.from_toml(config_path)

    assert not hasattr(config, "store_path")
    assert engram_config.store_path == EngramConfig().store_path
