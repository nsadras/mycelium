"""Neutral cumulative-memory regression through capture, Build Memory, and retrieval."""
import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from mycelium import Mycelium
from tests.model_probe_helpers import capture, check_meaning


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_LONG_MEMORY_REPLAY") != "1", reason="Opt-in host Ollama replay")
async def test_cumulative_memory_keeps_independent_details(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    config = Path(__file__).resolve().parents[1] / "mycelium.toml"
    memory = Mycelium(tmp_path / "store", config_path=config)
    batches = [
        ["I work as a librarian.", "I enjoy watercolor painting.", "I own a blue bicycle.",
         "I am learning Spanish.", "I grow tomatoes on my balcony.", "I joined a choir last month."],
        ["I have worked as a librarian for ten years.", "I prefer painting landscapes in watercolor.",
         "My bicycle has a wicker basket.", "I practice Spanish on Tuesday evenings.",
         "My balcony tomatoes are cherry tomatoes.", "My choir rehearses on Wednesdays."],
        ["I still enjoy watercolor painting.", "I plan to take a pottery class in November.",
         "I bought a red raincoat yesterday.", "I volunteer at an animal shelter on Saturdays.",
         "I prefer written directions.", "I have two cats."],
    ]
    for index, statements in enumerate(batches, 1):
        await capture(memory, [{"role": "user", "content": text} for text in statements], f"batch-{index}")
        build = await memory.consolidate()
        (tmp_path / f"build-{index}.json").write_text(json.dumps(asdict(build), indent=2, default=str))
        assert not build.report.failures
        facts = memory.artifacts.list_consolidated_facts()
        held = {cid for p in memory.artifacts.list_reconsolidation_proposals(status="pending")
                for cid in p.incoming_claim_ids}
        placed = {p.claim_id for p in memory.artifacts.list_placements() if p.status == "placed"}
        represented = {cid for f in facts for cid in f.member_claim_ids}
        assert placed - held <= represented
        for page in memory.wiki.list():
            ids = [cid for section in page.sections for item in section["items"]
                   if item["kind"] == "fact" for cid in item["claim_ids"]]
            assert len(ids) == len(set(ids))
        # Reload each time: progress and review boundaries must be durable.
        memory = Mycelium(tmp_path / "store", config_path=config)

    texts = [f.text for f in memory.artifacts.list_consolidated_facts()]
    (tmp_path / "facts.json").write_text(json.dumps(texts, indent=2))
    await check_meaning(memory, {
        "expected": "The user has worked as a librarian for ten years, enjoys painting watercolor landscapes, "
                    "owns a blue bicycle with a wicker basket, and practices Spanish on Tuesday evenings.",
        "forbidden": "The user's choir rehearses on Tuesdays.",
    }, texts, tmp_path / "meaning.json")
    async with memory.session("What do you remember about my bicycle?") as session:
        evidence = asdict(session.memory_evidence)
    (tmp_path / "retrieval.json").write_text(json.dumps(evidence, indent=2, default=str))
    await check_meaning(memory, {
        "expected": "The user owns a blue bicycle with a wicker basket.",
        "forbidden": "The user owns a red bicycle.",
    }, evidence, tmp_path / "retrieval-meaning.json")
