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
            "you": {"subject_evidence": "Explicit fixture subject decision.", "relevance": "describes_subject", "section_key": "priorities_plans", "reason": "Personal goal."},
            "project-1": {"subject_evidence": "Explicit fixture subject decision.", "relevance": "describes_subject", "section_key": second_section, "reason": "Explicit page decision."},
        },
    }}}
    # No network request: exercise the parser/serializer that previously dropped
    # required null decisions, and the router's subsequent validation boundary.
    client = OllamaClient(url="http://localhost:11434", model="unused")
    parsed = client._parse_structured_response(json.dumps(response), schema)
    assert schema.model_validate(parsed).model_dump() == response


def test_no_eligible_pages_requires_deferral():
    schema = page_plan_model(["C001"], {})
    decision = {"pages": {}, "owner_entity": "", "route_kind": "deferred", "confidence": 1.0, "reason": "No eligible identity."}
    schema.model_validate({"decisions": {"C001": decision}})
    with pytest.raises(ValidationError):
        schema.model_validate({"decisions": {"C001": {**decision, "route_kind": "general"}}})


def test_incidental_relevance_cannot_select_a_page():
    schema = page_plan_model(["C001"], {"you": "you"})
    page = {"subject_evidence": "No statement about this subject.",
            "relevance": "incidental_or_unrelated", "section_key": "profile", "reason": "Incidental."}
    decision = {"pages": {"you": page}, "owner_entity": "you", "route_kind": "general",
                "reason": "An invalid selection.", "confidence": 1.0}
    with pytest.raises(ValidationError, match="subject evidence"):
        schema.model_validate({"decisions": {"C001": decision}})
    page["section_key"] = "not_selected"
    decision.update(owner_entity="", route_kind="deferred")
    schema.model_validate({"decisions": {"C001": decision}})
    decision["owner_entity"] = "you"
    with pytest.raises(ValidationError, match="Deferred"):
        schema.model_validate({"decisions": {"C001": decision}})
