"""Opt-in direct production synthesis contract probes, without pipeline integration."""
import json
import os
from pathlib import Path

import pytest

from mycelium import Mycelium, prompts
from mycelium.structured_outputs import fact_synthesis_output_model
from tests.test_extraction_replays import check_meaning


CASES = [
    ("equivalent", ["Mira prefers written updates.", "Mira prefers receiving updates in writing."],
     1, "Mira prefers written updates.", "Mira dislikes written updates."),
    ("distinct", ["Mira joined a ceramics class.", "Mira began exercising."],
     2, "Mira joined a ceramics class and began exercising.", "Mira joined an exercise class."),
    ("modality", ["Mira is considering a trip in October.", "Mira has not decided whether to travel."],
     None, "Mira is considering an October trip but has not decided to travel.", "Mira has committed to an October trip."),
    ("details", ["Mira's workshop is on Tuesday.", "Mira's workshop has eight seats."],
     1, "Mira's workshop is on Tuesday and has eight seats.", "Mira's workshop is on Wednesday."),
    ("conflict", ["Mira prefers tea.", "Mira now prefers coffee instead of tea."],
     2, "Mira now prefers coffee instead of tea.", "Mira now prefers tea instead of coffee."),
    ("corrected", ["Mira prefers coffee.", "Mira grows herbs."],
     2, "Mira prefers coffee and grows herbs.", "Mira prefers tea."),
    ("review_excluded", ["Mira's workshop is on Tuesday.", "Mira's workshop has eight seats.",
                          "Mira joined a choir last month."],
     2, "Mira's workshop is on Tuesday and has eight seats; Mira joined a choir last month.",
     "Mira's workshop is on Wednesday."),
    ("separate_occurrences", ["Mira attended a pottery workshop on May 3.",
                              "Mira attended a pottery workshop on June 4.",
                              "The pottery workshop Mira attended on May 3 began at 9 a.m.",
                              "Mira intends to learn sailing.", "Mira prefers written updates.",
                              "The pottery workshop Mira attended on June 4 had twelve participants."],
     4, "Mira attended separate pottery workshops on May 3 at 9 a.m. and on June 4 with twelve participants; "
        "Mira intends to learn sailing and prefers written updates.",
     "The pottery workshop on May 3 had twelve participants."),
    ("conflict_with_other_memories", ["Mira's bicycle is blue.", "Mira's bicycle is now green.",
                                     "Mira's workshop is on Tuesday.", "Mira's workshop has eight seats.",
                                     "Mira joined a choir last month."],
     4, "Mira's workshop is on Tuesday and has eight seats; Mira joined a choir last month.",
     "Mira's workshop is on Wednesday."),
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_SYNTHESIS_PROBES") != "1", reason="Opt-in host Ollama probes")
@pytest.mark.parametrize("name,texts,count,expected,forbidden", CASES, ids=[c[0] for c in CASES])
async def test_grounded_synthesis(tmp_path, monkeypatch, name, texts, count, expected, forbidden):
    print(f"synthesis {name}: {tmp_path}", flush=True)
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm-errors"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    claims = {f"C{i:03d}": text for i, text in enumerate(texts, 1)}
    changes = ([{"incoming_claim_aliases": ["C002"], "target_claim_aliases": ["C001"],
                 "relation": "supersedes", "explanation": "The newer statement explicitly replaces the prior state."}]
               if name in {"conflict", "conflict_with_other_memories"} else [])
    schema = fact_synthesis_output_model(claims, ["profile", "history", "needs_review"], changes)
    canonical = {alias: {"text": text, "temporal_status": "unknown", "temporal": None}
                 for alias, text in claims.items()}
    system, user = prompts.fact_synthesis_prompt(
        "Mira (person)", json.dumps(canonical),
        "Mira prefers tea." if name == "corrected" else "none", json.dumps(changes),
        "profile: interests and ongoing knowledge\nhistory: past events\nneeds_review: unresolved memory",
    )
    result = schema.model_validate(await memory.llm.call_structured(
        system, user, schema, num_predict=4096, debug_label="synthesis-probe",
    )).model_dump()
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    # The modality case tests faithful uncertainty, not a mandatory compression
    # ratio. Keeping its two assertions separate is a valid conservative choice.
    if count is not None:
        assert len(result["facts"]) == count
    await check_meaning(memory, {"expected": expected, "forbidden": forbidden},
                        result["facts"], tmp_path / "meaning.json")


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_SYNTHESIS_PROBES") != "1", reason="Opt-in host Ollama probes")
async def test_repartitions_overbroad_existing_group(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    texts = ["Rina enjoys making ceramics.", "Rina likes working with clay.",
             "Rina finished a vase on May 3.", "The vase Rina finished on May 3 has a blue glaze.",
             "Rina met a potter at the June fair.", "The potter Rina met at the June fair taught her a glazing method.",
             "Rina plans to take a ceramics course in October."]
    claims = {f"C{i:03d}": text for i, text in enumerate(texts, 1)}
    canonical = {alias: {"text": text, "temporal_status": "past" if alias in {"C003", "C004", "C005", "C006"} else "current",
                         "temporal": None} for alias, text in claims.items()}
    system, user = prompts.fact_synthesis_prompt("Rina (person)", json.dumps(canonical),
        "An existing display fact groups C001 through C006 into one long sentence.", "[]",
        "profile: preferences and plans; history: completed occurrences")
    response = await memory.llm.call_structured(system, user,
        fact_synthesis_output_model(claims, ["profile", "history"]), num_predict=4096, dump_success=True)
    (tmp_path / "response.json").write_text(json.dumps(response, indent=2))
    assert {frozenset(f["member_claim_aliases"]) for f in response["facts"]} == {
        frozenset(members) for members in [["C001", "C002"], ["C003", "C004"], ["C005", "C006"], ["C007"]]}
    assert all(f["state"] == "history" for f in response["facts"]
               if {"C003", "C005"}.intersection(f["member_claim_aliases"]))
