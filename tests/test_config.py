from engram.config import EngramConfig
from mycelium.config import Config


def test_store_paths_are_owned_by_runtime_and_engram_config(tmp_path):
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text("", encoding="utf-8")

    config = Config.from_toml(config_path)
    engram_config = EngramConfig.from_toml(config_path)

    assert not hasattr(config, "store_path")
    assert engram_config.store_path == EngramConfig().store_path
