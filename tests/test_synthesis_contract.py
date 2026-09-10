from copy import deepcopy

import pytest
from pydantic import ValidationError

from mycelium.structured_outputs import fact_synthesis_output_model


def synthesis_plan():
    return {"facts": [
                {"memory_scope": text, "member_claim_aliases": [key], "section_key": "profile", "state": "current", "text": None,
                 "confidence": 0.9, "reason": "Canonical statement."}
                for key, text in [("C001", "Ava prefers tea."), ("C002", "Ava grows herbs.")]
            ]}


@pytest.mark.parametrize("damage", ["missing_claim", "unknown_claim", "missing_fact", "duplicate_member",
                                    "duplicate_fact", "wrong_section", "cross_group_text", "rewrite"])
def test_synthesis_requires_complete_grounded_projection(damage):
    schema = fact_synthesis_output_model(
        {"C001": "Ava prefers tea.", "C002": "Ava grows herbs."}, ["profile"],
    )
    valid = synthesis_plan()
    schema.model_validate(valid)
    response = deepcopy(valid)
    if damage == "missing_claim":
        response["facts"][0]["member_claim_aliases"] = []
    elif damage == "unknown_claim":
        response["facts"][0]["member_claim_aliases"] = ["C999"]
    elif damage == "missing_fact":
        response["facts"].pop()
    elif damage == "duplicate_member":
        response["facts"][0]["member_claim_aliases"].append("C001")
    elif damage == "duplicate_fact":
        response["facts"][1] = deepcopy(response["facts"][0])
    elif damage == "wrong_section":
        response["facts"][0]["section_key"] = "invented"
    elif damage == "cross_group_text":
        response["facts"][0]["text"] = "Ava grows herbs."
    else:
        response["facts"][0]["text"] = "Ava prefers coffee."
    with pytest.raises(ValidationError):
        schema.model_validate(response)


def test_synthesis_keeps_review_required_sides_separate():
    schema = fact_synthesis_output_model(
        {"C001": "Ava prefers tea.", "C002": "Ava grows herbs."}, ["profile"],
        [{"incoming_claim_aliases": ["C002"], "target_claim_aliases": ["C001"]}],
    )
    response = synthesis_plan()
    schema.model_validate(response)
    response["facts"] = [{**response["facts"][0], "member_claim_aliases": ["C001", "C002"]}]
    with pytest.raises(ValidationError):
        schema.model_validate(response)


@pytest.mark.parametrize("count", [1, 2, 5])
def test_synthesis_schema_has_feasible_array_bounds(count):
    schema = fact_synthesis_output_model({f"C{i:03d}": f"Assertion {i}." for i in range(count)}, ["profile"])
    def check(value):
        if isinstance(value, dict):
            if "minItems" in value and "maxItems" in value:
                assert value["minItems"] <= value["maxItems"]
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(schema.model_json_schema())
