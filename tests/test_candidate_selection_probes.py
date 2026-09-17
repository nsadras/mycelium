"""Opt-in real-model checks for batching and broad historical corrections."""

import json
import os
import time
from pathlib import Path

import pytest

from mycelium import Mycelium
from mycelium.facts import FactResolver
from tests.memory_helpers import claim, fact, place

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MYCELIUM_RUN_SELECTION_PROBES") != "1",
        reason="Opt-in configured-model selection probes",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broad", [False, True], ids=["independent_queries", "broad_correction"]
)
async def test_batched_selection_retains_relevant_history(tmp_path, monkeypatch, broad):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(
        tmp_path / "store",
        config_path=Path(__file__).resolve().parents[1] / "mycelium.toml",
    )
    structured_call = memory.llm.call_structured

    async def record_contract(*args, **kwargs):
        return await structured_call(*args, **kwargs, dump_success=True)

    monkeypatch.setattr(memory.llm, "call_structured", record_contract)
    if broad:
        texts = [
            f"Mira's electricity meter reading on June {i}, 2026 was {100 + i} kWh."
            for i in range(1, 29)
        ]
        texts += [
            f"Mira's water meter reading on June {i}, 2026 was {200 + i} liters."
            for i in range(1, 29)
        ]
    else:
        texts = [
            f"Mira catalogued equipment item {i} in storage locker {i}."
            for i in range(1, 57)
        ]
    texts += [
        "Mira's only bicycle is blue.",
        "Mira's workshop is on July 8, 2026.",
        "Mira prefers written updates.",
        "Mira attended a different workshop on February 2, 2026.",
    ]
    old = [claim(f"old-{i}", text, "2026-01-01") for i, text in enumerate(texts)]
    queries = [
        "Mira's only bicycle is now green after being repainted.",
        "Mira's July 8, 2026 workshop lasted two hours.",
        "Mira prefers to receive updates in writing.",
        "Mira corrected all her recorded June 2026 electricity meter readings: every reading was 10 kWh too high."
        if broad
        else "Mira plans to learn the harp.",
    ]
    incoming = [claim(f"new-{i}", text, "2026-08-01") for i, text in enumerate(queries)]
    placements = {c.claim_id: place(memory.artifacts, c) for c in old + incoming}
    expected = {
        "new-0": {"fact-old-56"},
        "new-1": {"fact-old-57"},
        "new-2": {"fact-old-58"},
        "new-3": {f"fact-old-{i}" for i in range(28)} if broad else set(),
    }
    start = time.perf_counter()
    result = await FactResolver(memory.llm, memory.artifacts, memory.config)._select_prior_facts(
        incoming,
        placements,
        [fact(c) for c in old],
        {"you": memory.artifacts.get_entity("you")},
    )
    (tmp_path / "result.json").write_text(
        json.dumps(
            {
                "seconds": time.perf_counter() - start,
                "selected": {k: sorted(v) for k, v in result.items()},
                "trace": list(memory.llm._call_log),
            },
            indent=2,
        )
    )
    assert result == expected
    assert len(memory.llm._call_log) == 5
