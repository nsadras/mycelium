"""Direct configured-model probes before integrating page placement changes."""

import json
import os
from pathlib import Path

import pytest

from mycelium import Mycelium
from mycelium.artifacts import EntityRecord, ClaimProvenance, MemoryClaim, SourceDocument, SourceSegment
from mycelium.consolidation_models import ClaimEvidence
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.page_plan import page_plan_model, page_plan_prompt


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("MYCELIUM_RUN_PAGE_REPLAYS") != "1", reason="Opt-in configured model probes")
@pytest.mark.parametrize("case", ["shared", "incidental", "project", "multiple_sections"])
async def test_page_plan_real_model(tmp_path, case, monkeypatch):
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(tmp_path / "store", config_path=Path(__file__).resolve().parents[1] / "mycelium.toml")
    entities = [EntityRecord("p1", "person", "Elena Ruiz", "elena", [], "active", "2026-09-04", "2026-09-04"),
                EntityRecord("o1", "project" if case == "project" else "organization",
                             "Harbor Workshop", "harbor", [], "active", "2026-09-04", "2026-09-04")]
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
    source = SourceDocument("s1", "agent_conversation" if personal else "tool_observation",
                            "s", "2026-09-04", None, [],
                            [SourceSegment("seg1", 0, text, role="user" if personal else "tool")])
    claim = MemoryClaim("c1", text, [], [ClaimProvenance("s1", ["seg1"])], "2026-09-04")
    formatter = RoutingFormatter(memory.artifacts)
    schema = page_plan_model(["C001"], {e.entity_id: e.entity_type for e in entities})
    system, user = page_plan_prompt(formatter.entity_catalog(entities, include_sections=True),
                                    "Resolved identities are listed above.",
                                    formatter.format_evidence({"C001": ClaimEvidence(claim, source)}, {}))
    response = schema.model_validate(await memory.llm.call_structured(system, user, schema)).model_dump(exclude_none=True)
    (tmp_path / "response.json").write_text(json.dumps(response, indent=2))
    print(case, json.dumps(response), flush=True)
    decision = response["decisions"]["C001"]
    assert decision["route_kind"] == "general"
    expected = {"you"} if case == "multiple_sections" else ({"o1"} if case == "incidental" else {"p1", "o1"})
    assert {key for key, value in decision["pages"].items() if value["section_key"] != "not_selected"} == expected
