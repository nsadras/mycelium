import json

import pytest
from pydantic import ValidationError

from mycelium.ollama import OllamaClient
from mycelium.page_plan import page_plan_model


@pytest.mark.parametrize("second_section", ["overview", "not_selected"])
def test_page_choices_survive_structured_response_roundtrip(second_section):
    schema = page_plan_model(["C001"], {"you": "you", "project-1": "project"})
    response = {"decisions": {"C001": {"prominence": "briefing", "uncertainty": None,
        "owner_entity": "you", "reason": None,
        "pages": {
            "you": {"section_key": "priorities_plans", "reason": "Personal goal."},
            "project-1": {"section_key": second_section, "reason": "Explicit page decision."},
        },
    }}}
    if second_section == "not_selected":
        del response["decisions"]["C001"]["pages"]["project-1"]
    # No network request: exercise the parser/serializer that previously dropped
    # required null decisions, and the router's subsequent validation boundary.
    client = OllamaClient(url="http://localhost:11434", model="unused")
    parsed = client._parse_structured_response(json.dumps(response), schema)
    assert schema.model_validate(parsed).model_dump() == response


def test_no_eligible_pages_requires_deferral():
    schema = page_plan_model(["C001"], {})
    decision = {"prominence": "briefing", "uncertainty": None, "pages": {}, "owner_entity": "", "reason": "No eligible identity."}
    schema.model_validate({"decisions": {"C001": decision}})
    with pytest.raises(ValidationError):
        schema.model_validate({"decisions": {"C001": {**decision, "reason": None}}})


def test_selection_requires_valid_owner_and_destination_reason():
    schema = page_plan_model(["C001"], {"you": "you"})
    decision = {"prominence": "briefing", "uncertainty": None, "pages": {"you": {"section_key": "profile", "reason": "Personal statement."}},
                "owner_entity": "", "reason": None}
    with pytest.raises(ValidationError, match="primary owner"):
        schema.model_validate({"decisions": {"C001": decision}})
    decision["owner_entity"] = "you"
    schema.model_validate({"decisions": {"C001": decision}})
    decision["pages"] = {}
    decision["reason"] = "No supported destination."
    with pytest.raises(ValidationError, match="no owner"):
        schema.model_validate({"decisions": {"C001": decision}})
    decision["owner_entity"] = ""
    schema.model_validate({"decisions": {"C001": decision}})
