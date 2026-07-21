from mycelium.batching import batch_items, split_text_by_tokens, structured_input_budget
from mycelium.config import Config
from engram.config import EngramConfig


def test_split_text_by_tokens_preserves_every_character():
    text = "first line\n" + ("middle words " * 1000) + "\nlast sentinel"

    chunks = split_text_by_tokens(text, 100)

    assert len(chunks) > 1
    assert "".join(chunks) == text
    assert chunks[-1].endswith("last sentinel")


def test_batch_items_uses_rendered_prompt_budget():
    batches = batch_items(
        ["alpha " * 30, "beta " * 30, "gamma " * 30],
        lambda items: "static prompt " + "".join(items),
        max_tokens=70,
    )

    assert [item for batch in batches for item in batch] == [
        "alpha " * 30,
        "beta " * 30,
        "gamma " * 30,
    ]
    assert len(batches) > 1


def test_structured_input_budget_reserves_output_and_safety_margin():
    assert structured_input_budget(32768, 8192) == 22528


def test_context_window_is_shared_by_dream_and_engram_config(tmp_path):
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text('[llm]\ncontext_window_tokens = 65536\n', encoding="utf-8")

    assert Config.from_toml(config_path).llm.context_window_tokens == 65536
    assert EngramConfig.from_toml(config_path).summary_context_window_tokens == 65536
