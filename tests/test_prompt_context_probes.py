"""Mixed-context probes: fixtures are evaluation inputs, never prompt instructions."""

import json
import os
from pathlib import Path
import pytest
from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimPlacement,
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.truth_review import TruthReviewer
from tests.model_probe_helpers import grouped_statements, check_meaning


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
    return TruthReviewer(memory.llm, memory.artifacts)._records(claims, placements, {})


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
    memory.llm.trace_path = tmp_path / "calls.jsonl"
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
    records = render_truth_claims(memory, {
        **targets, "C009": record(incoming, "2026-10-22"),
    })
    decisions = await TruthReviewer(memory.llm, memory.artifacts)._compare_pairs(
        [(target, "C009") for target in targets], records,
    )
    (tmp_path / "response.json").write_text(json.dumps(
        {left: decision for (left, _), decision in decisions.items()}, indent=2,
    ))
    decision = decisions[("C001", "C009")]
    assert (decision["relation"] == "no_change") == (expected == "no_change")
    if scope:
        assert decision["scope"] == scope
    assert all(d["relation"] == "no_change" for (left, _), d in decisions.items() if left != "C001")


@pytest.mark.asyncio
async def test_synthesis_mixed_history(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path.cwd() / "mycelium.toml")
    memory.llm.trace_path = tmp_path / "calls.jsonl"
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
    for g in groups:
        for t in g:
            alias = f"C{len(canonical) + 1:03d}"
            canonical[alias] = record(t, "2026-11-01", "unknown")
    statements = await grouped_statements(
        memory, "Rina (person)", canonical,
        "profile: ongoing attributes and plans\nhistory: past occurrences",
        tmp_path / "response.json",
    )
    await check_meaning(
        memory,
        {"expected": "Rina attended separate bookbinding workshops on March 3 lasting two hours and October 6 at the library; she intends to learn clarinet and try sourdough, adopted a cat April 8, and bought a bicycle April 9.",
         "forbidden": "The October 6 workshop lasted two hours."},
        statements, tmp_path / "meaning.json",
    )
