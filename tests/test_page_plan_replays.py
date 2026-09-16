"""Direct configured-model probes before integrating page placement changes."""

import json
import os
from pathlib import Path

import pytest

from mycelium import Mycelium
from mycelium.artifacts import (
    EntityRecord,
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation_models import ClaimEvidence
from mycelium.consolidation_formatting import RoutingFormatter
from benchmarks.experiments.attribution_contract_probes import decide


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("MYCELIUM_RUN_PAGE_REPLAYS") != "1",
    reason="Opt-in configured model probes",
)
@pytest.mark.parametrize(
    "case", ["shared", "incidental", "project", "multiple_sections"]
)
async def test_page_plan_real_model(tmp_path, case, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(
        tmp_path / "store",
        config_path=Path(__file__).resolve().parents[1] / "mycelium.toml",
    )
    entities = [
        EntityRecord(
            "p1",
            "person",
            "Elena Ruiz",
            "elena",
            [],
            "active",
            "2026-09-04",
            "2026-09-04",
        ),
        EntityRecord(
            "o1",
            "project" if case == "project" else "organization",
            "Harbor Workshop",
            "harbor",
            [],
            "active",
            "2026-09-04",
            "2026-09-04",
        ),
    ]
    if case == "multiple_sections":
        entities = [memory.artifacts.get_entity("you")]
    statements = {
        "shared": "Elena Ruiz founded Harbor Workshop, a bicycle repair business, in 2019.",
        "incidental": "Harbor Workshop now opens on Sundays. Elena Ruiz merely read this announcement aloud; it does not describe her work, plans, or relationship to the business.",
        "project": "Elena Ruiz leads the testing work for the Harbor Workshop project.",
        "multiple_sections": "The user plans to learn woodworking to make a birthday gift for their partner.",
    }
    text = statements[case]
    personal = case == "multiple_sections"
    source = SourceDocument(
        "s1",
        "agent_conversation" if personal else "tool_observation",
        "s",
        "2026-09-04",
        None,
        [],
        [SourceSegment("seg1", 0, text, role="user" if personal else "tool")],
    )
    claim = MemoryClaim("c1", text, [], [ClaimProvenance("s1", ["seg1"])], "2026-09-04")
    formatter = RoutingFormatter(memory.artifacts)
    subjects = [
        {
            "entity_id": e.entity_id,
            "entity_type": e.entity_type,
            "title": e.title,
            "participant_bindings": [],
        }
        for e in entities
    ]
    attribution, presentation, _ = await decide(
        memory.llm,
        subjects,
        json.loads(
            formatter.format_evidence({"C001": ClaimEvidence(claim, source)}, {})
        ),
        {e.entity_id for e in entities},
        {},
    )
    response = {"attribution": attribution, "decisions": presentation}
    response_path = tmp_path / "response.json"
    response_path.write_text(json.dumps(response, indent=2))
    assert json.loads(response_path.read_text()) == response
    print(case, json.dumps(response), flush=True)
    decision = response["decisions"]["C001"]
    assert decision["pages"]
    expected = (
        {"you"}
        if case == "multiple_sections"
        else ({"o1"} if case == "incidental" else {"p1", "o1"})
    )
    assert set(decision["pages"]) == expected


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("MYCELIUM_RUN_PAGE_REPLAYS") != "1",
    reason="Opt-in configured model probes",
)
async def test_page_plan_with_larger_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(
        tmp_path / "store",
        config_path=Path(__file__).resolve().parents[1] / "mycelium.toml",
    )
    entities = [
        memory.artifacts.create_entity("person", "Elena Ruiz"),
        memory.artifacts.create_entity("organization", "Harbor Workshop"),
    ]
    entities += [
        memory.artifacts.create_entity("person", name)
        for name in ("Nora", "Omar", "Iris", "Theo", "Leah", "Noah")
    ]
    person, organization = [e.entity_id for e in entities[:2]]
    texts = [
        "Elena Ruiz enjoys landscape painting.",
        "Harbor Workshop opens on Sundays.",
        "Elena Ruiz founded Harbor Workshop in 2019.",
        "Elena Ruiz volunteers at Harbor Workshop on Saturdays.",
    ]
    source = SourceDocument(
        "s",
        "tool_observation",
        "s",
        "2026-09-08",
        None,
        [],
        [SourceSegment(f"s{i}", i, text, role="tool") for i, text in enumerate(texts)],
    )
    evidence = {
        f"C{i + 1:03d}": ClaimEvidence(
            MemoryClaim(
                f"c{i}",
                text,
                [],
                [ClaimProvenance("s", [f"s{i}"])],
                "2026-09-08",
            ),
            source,
        )
        for i, text in enumerate(texts)
    }
    formatter = RoutingFormatter(memory.artifacts)
    subjects = [
        {
            "entity_id": e.entity_id,
            "entity_type": e.entity_type,
            "title": e.title,
            "participant_bindings": [],
        }
        for e in entities
    ]
    attribution, presentation, _ = await decide(
        memory.llm,
        subjects,
        json.loads(formatter.format_evidence(evidence, {})),
        {e.entity_id for e in entities},
        {},
    )
    result = {"attribution": attribution, "decisions": presentation}
    (tmp_path / "response.json").write_text(json.dumps(result, indent=2))
    for alias, expected in zip(
        evidence,
        [{person}, {organization}, {person, organization}, {person, organization}],
    ):
        decision = result["decisions"][alias]
        assert decision["pages"]
        selected = set(decision["pages"])
        assert selected == expected
        assert decision["primary_subject"] in selected
