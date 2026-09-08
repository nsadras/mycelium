import json

import pytest
from pydantic import ValidationError

from mycelium.ollama import OllamaClient
from mycelium.page_plan import page_plan_model


@pytest.mark.parametrize("second_section", ["overview", "not_selected"])
def test_page_choices_survive_structured_response_roundtrip(second_section):
    schema = page_plan_model(["C001"], {"you": "you", "project-1": "project"})
    response = {"decisions": {"C001": {
        "route_kind": "general", "owner_entity": "you", "reason": "Grounded placements.",
        "confidence": 0.9,
        "pages": {
            "you": {"section_key": "priorities_plans", "reason": "Personal goal."},
            "project-1": {"section_key": second_section, "reason": "Explicit page decision."},
        },
    }}}
    # No network request: exercise the parser/serializer that previously dropped
    # required null decisions, and the router's subsequent validation boundary.
    client = OllamaClient(url="http://localhost:11434", model="unused")
    parsed = client._parse_structured_response(json.dumps(response), schema)
    assert schema.model_validate(parsed).model_dump() == response


def test_no_eligible_pages_requires_deferral():
    schema = page_plan_model(["C001"], {})
    decision = {"route_kind": "deferred", "confidence": 1.0, "reason": "No eligible identity."}
    schema.model_validate({"decisions": {"C001": decision}})
    with pytest.raises(ValidationError):
        schema.model_validate({"decisions": {"C001": {**decision, "route_kind": "general"}}})
