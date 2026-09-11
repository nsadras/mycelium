from copy import deepcopy

import pytest
from pydantic import ValidationError

from mycelium.structured_outputs import fact_synthesis_output_model


def synthesis_plan():
    return {"facts": [
                {"prominence": "briefing", 'memory_scope': text, 'member_claim_aliases': [key], 'section_key': 'profile', 'state': 'current', 'text': None}
                for key, text in [("C001", "Ava prefers tea."), ("C002", "Ava grows herbs.")]
            ]}


@pytest.mark.parametrize("damage", ["missing_claim", "unknown_claim", "missing_fact", "duplicate_member",
                                    "duplicate_fact", "wrong_section", "singleton_text"])
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
    else:
        response["facts"][0]["text"] = "Ava prefers coffee."
    with pytest.raises(ValidationError):
        schema.model_validate(response)


def test_synthesis_keeps_review_required_sides_separate():
    claims = {"C001": "Ava prefers tea.", "C002": "Ava grows herbs."}
    schema = fact_synthesis_output_model(
        claims, ["profile"],
        [{"incoming_claim_aliases": ["C002"], "target_claim_aliases": ["C001"]}],
    )
    response = synthesis_plan()
    schema.model_validate(response)
    response["facts"] = [{
        **response["facts"][0],
        "member_claim_aliases": ["C001", "C002"],
        "text": "Ava prefers tea and grows herbs.",
    }]
    fact_synthesis_output_model(claims, ["profile"]).model_validate(response)
    with pytest.raises(ValidationError, match="Truth-change sides cannot share a fact"):
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


def test_native_synthesis_schema_enforces_text_for_combined_claims():
    schema = fact_synthesis_output_model({"C001": "One.", "C002": "Two."}, ["profile"])
    definitions = schema.model_json_schema()["$defs"]
    single = definitions["SingleClaimFact"]["properties"]
    combined = definitions["CombinedFact"]["properties"]
    assert single["member_claim_aliases"]["maxItems"] == 1
    assert single["text"]["type"] == "null"
    assert combined["member_claim_aliases"]["minItems"] == 2
    assert combined["text"]["type"] == "string"
    assert combined["text"]["minLength"] == 1
