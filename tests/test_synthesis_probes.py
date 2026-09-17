"""Opt-in current grouping/rendering probes; presentation layout is not a contract."""
import os
from pathlib import Path

import pytest

from mycelium import Mycelium
from tests.model_probe_helpers import check_meaning, grouped_statements


CASES = [('equivalent',
  ['Mira prefers written updates.', 'Mira prefers receiving updates in writing.'],
  'Mira prefers written updates.',
  'Mira dislikes written updates.'),
 ('distinct',
  ['Mira joined a ceramics class.', 'Mira began exercising.'],
  'Mira joined a ceramics class and began exercising.',
  'Mira joined an exercise class.'),
 ('modality',
  ['Mira is considering a trip in October.', 'Mira has not decided whether to travel.'],
  'Mira is considering an October trip but has not decided to travel.',
  'Mira has committed to an October trip.'),
 ('details',
  ["Mira's workshop is on Tuesday.", "Mira's workshop has eight seats."],
  "Mira's workshop is on Tuesday and has eight seats.",
  "Mira's workshop is on Wednesday."),
 ('conflict',
  ['Mira prefers tea.', 'Mira now prefers coffee instead of tea.'],
  'Mira now prefers coffee instead of tea.',
  'Mira now prefers tea instead of coffee.'),
 ('corrected',
  ['Mira prefers coffee.', 'Mira grows herbs.'],
  'Mira prefers coffee and grows herbs.',
  'Mira prefers tea.'),
 ('review_excluded',
  ["Mira's workshop is on Tuesday.",
   "Mira's workshop has eight seats.",
   'Mira joined a choir last month.'],
  "Mira's workshop is on Tuesday and has eight seats; Mira joined a choir last month.",
  "Mira's workshop is on Wednesday."),
 ('separate_occurrences',
  ['Mira attended a pottery workshop on May 3.',
   'Mira attended a pottery workshop on June 4.',
   'The pottery workshop Mira attended on May 3 began at 9 a.m.',
   'Mira intends to learn sailing.',
   'Mira prefers written updates.',
   'The pottery workshop Mira attended on June 4 had twelve participants.'],
  'Mira attended separate pottery workshops on May 3 at 9 a.m. and on June 4 with twelve '
  'participants; Mira intends to learn sailing and prefers written updates.',
  'The pottery workshop on May 3 had twelve participants.'),
 ('conflict_with_other_memories',
  ["Mira's bicycle is blue.",
   "Mira's bicycle is now green.",
   "Mira's workshop is on Tuesday.",
   "Mira's workshop has eight seats.",
   'Mira joined a choir last month.'],
  "Mira's workshop is on Tuesday and has eight seats; Mira joined a choir last month.",
  "Mira's workshop is on Wednesday.")]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_SYNTHESIS_PROBES") != "1", reason="Opt-in host Ollama probes")
@pytest.mark.parametrize("name,texts,expected,forbidden", CASES, ids=[c[0] for c in CASES])
async def test_grounded_synthesis(tmp_path, monkeypatch, name, texts, expected, forbidden):
    print(f"synthesis {name}: {tmp_path}", flush=True)
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    memory.llm.trace_path = tmp_path / "calls.jsonl"
    claims = {f"C{i:03d}": text for i, text in enumerate(texts, 1)}
    canonical = {alias: {"text": text, "temporal_status": "unknown", "temporal": []}
                 for alias, text in claims.items()}
    statements = await grouped_statements(
        memory, "Mira (person)", canonical,
        "profile: interests and ongoing knowledge\nhistory: past events",
        tmp_path / "response.json",
    )
    await check_meaning(memory, {"expected": expected, "forbidden": forbidden},
                        statements, tmp_path / "meaning.json")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_SYNTHESIS_PROBES") != "1", reason="Opt-in host Ollama probes")
async def test_preserves_occurrences_and_plans(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    memory.llm.trace_path = tmp_path / "calls.jsonl"
    texts = ["Rina enjoys making ceramics.", "Rina likes working with clay.",
             "Rina finished a vase on May 3.", "The vase Rina finished on May 3 has a blue glaze.",
             "Rina met a potter at the June fair.", "The potter Rina met at the June fair taught her a glazing method.",
             "Rina plans to take a ceramics course in October."]
    claims = {f"C{i:03d}": text for i, text in enumerate(texts, 1)}
    canonical = {alias: {"text": text, "temporal_status": "past" if alias in {"C003", "C004", "C005", "C006"} else "current",
                         "temporal": []} for alias, text in claims.items()}
    statements = await grouped_statements(
        memory, "Rina (person)", canonical,
        "profile: preferences and plans; history: completed occurrences",
        tmp_path / "response.json",
    )
    await check_meaning(
        memory,
        {"expected": "Rina finished a blue-glazed vase on May 3 and met a potter at the June fair who taught her a glazing method. She plans a ceramics course in October.",
         "forbidden": "Rina completed a ceramics course in October."},
        statements, tmp_path / "meaning.json",
    )
