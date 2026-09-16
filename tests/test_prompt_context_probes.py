"""Mixed-context probes: fixtures are evaluation inputs, never prompt instructions."""

import json
import os
from pathlib import Path
import pytest
from mycelium import Mycelium, prompts
from mycelium.artifacts import (
    ClaimPlacement,
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.facts import FactResolver
from mycelium.structured_outputs import (
    fact_truth_output_model,
    fact_synthesis_output_model,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("MYCELIUM_RUN_PROMPT_CONTEXT_PROBES") != "1",
        reason="Opt-in configured host-model prompt context probes",
    ),
]


def record(text, date, temporal="current"):
    return {
        "text": text,
        "temporal_status": temporal,
        "temporal": [],
        "source_times": [
            {
                "source_id": "source-" + date,
                "occurred_at": date,
                "segments": [{"segment_id": "s1", "timestamp": date}],
            }
        ],
    }


def render_truth_claims(memory, records):
    claims, placements = {}, {}
    for alias, value in records.items():
        source_id = f"source-{alias}"
        date = value["source_times"][0]["occurred_at"]
        memory.artifacts.save_source(
            SourceDocument(
                source_id,
                "multi_party_conversation",
                "conversation",
                "2026-11-01",
                date,
                ["Rina"],
                [SourceSegment("s1", 0, value["text"], "Rina", "participant", date)],
            )
        )
        claim = MemoryClaim(
            alias,
            value["text"],
            [],
            [ClaimProvenance(source_id, ["s1"])],
            "2026-11-01",
            temporal_status=value["temporal_status"],
        )
        claims[alias] = claim
        placements[alias] = ClaimPlacement(
            alias,
            "you",
            "preferences_working_style",
            [],
            "placed",
            "test",
            "2026-11-01",
            "2026-11-01",
        )
    return FactResolver(memory.llm, memory.artifacts)._claims_text(
        claims, placements, {}, {}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prior,incoming,expected,scope",
    [
        (
            "Rina misplaces her reading glasses every week.",
            "Rina misplaces her reading glasses every week.",
            "no_change",
            "same",
        ),
        (
            "Rina had a frightening dizzy spell last week.",
            "Rina had a frightening dizzy spell last week.",
            "no_change",
            "distinct",
        ),
        (
            "Rina takes swimming lessons to improve her fitness.",
            "Rina does stretching exercises to improve her fitness.",
            "no_change",
            None,
        ),
        (
            "Rina has one designated emergency contact, Omar.",
            "Rina replaced Omar with Leila as her sole emergency contact.",
            "truth_change",
            "same",
        ),
    ],
    ids=[
        "repeated_habit",
        "relative_dates",
        "compatible_activities",
        "exclusive_transition",
    ],
)
async def test_truth_in_mixed_history(
    tmp_path, monkeypatch, prior, incoming, expected, scope
):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path.cwd() / "mycelium.toml")
    targets = {"C001": record(prior, "2026-03-14")}
    distractions = [
        "Rina repairs antique radios.",
        "Rina attended a lecture in January.",
        "Rina plans to visit her cousin in December.",
        "Rina has two cats.",
        "Rina teaches mathematics.",
        "Rina prefers email updates.",
        "Rina bakes bread on Sundays.",
    ]
    targets.update(
        {f"C{i:03d}": record(t, "2026-04-05") for i, t in enumerate(distractions, 2)}
    )
    system, user = prompts.fact_truth_prompt(
        "Rina (person)",
        render_truth_claims(memory, targets),
        "none",
        "none",
        render_truth_claims(memory, {"C009": record(incoming, "2026-10-22")}),
        "[]",
    )
    result = await memory.llm.call_structured(
        system,
        user,
        fact_truth_output_model(targets),
        num_predict=8192,
        dump_success=True, think=True,
    )
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    decision = result
    assert (decision["relation"] == "no_change") == (expected == "no_change")
    if scope:
        assert {c["target"]: c["scope"] for c in decision["comparisons"]}["C001"] == scope
    if expected == "truth_change":
        assert decision["changed_targets"] == ["C001"]


@pytest.mark.asyncio
async def test_synthesis_mixed_history(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path.cwd() / "mycelium.toml")
    groups = [
        [
            "Rina attended a bookbinding workshop on March 3.",
            "The bookbinding workshop Rina attended on March 3 lasted two hours.",
        ],
        [
            "Rina attended a bookbinding workshop on October 6.",
            "The bookbinding workshop Rina attended on October 6 was held in the library.",
        ],
        ["Rina prefers email updates.", "Rina prefers receiving updates by email."],
        ["Rina intends to learn the clarinet."],
        ["Rina intends to try making sourdough."],
        ["Rina adopted a cat on April 8."],
        ["Rina bought a bicycle on April 9."],
        [
            "Rina completed a charity walk on May 2.",
            "The charity walk Rina completed on May 2 raised 400 euros.",
        ],
        ["Rina practices yoga on Mondays."],
        ["Rina volunteers at the library on Fridays."],
    ]
    canonical = {}
    expected = []
    for g in groups:
        members = []
        for t in g:
            alias = f"C{len(canonical) + 1:03d}"
            members.append(alias)
            canonical[alias] = record(t, "2026-11-01", "unknown")
        expected.append(frozenset(members))
    system, user = prompts.fact_synthesis_prompt(
        "Rina (person)",
        json.dumps(canonical, indent=2),
        "none",
        "[]",
        "profile: ongoing attributes and plans\nhistory: past occurrences",
    )
    result = await memory.llm.call_structured(
        system,
        user,
        fact_synthesis_output_model(
            {a: r["text"] for a, r in canonical.items()}, ["profile", "history"]
        ),
        num_predict=8192,
        dump_success=True, think=True,
    )
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    assert {frozenset(f["member_claim_aliases"]) for f in result["facts"]} == set(
        expected
    )
