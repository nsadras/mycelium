import pytest
from pydantic import ValidationError

from mycelium.subject_discovery import subject_discovery_model


def user(claims=None):
    return {
        "supporting_claims": claims or [],
        "description": "The declared source user",
        "alternate_names": [],
    }


def person(support):
    return {
        "supporting_evidence": support,
        "description": "A reported person",
        "entity_type": "person",
        "title": "Someone else",
        "alternate_names": [],
    }


def test_declared_user_is_required_even_without_a_claim_about_them():
    schema = subject_discovery_model(
        ["C001"], {"P001": "user", "P002": "user"}, {}, canonical_user=True
    )
    assert list(schema.model_json_schema()["properties"]) == [
        "declared_user",
        "subjects",
    ]
    schema.model_validate({"declared_user": user(), "subjects": [person(["C001"])]})
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": [person(["C001"])]})
    for alias in ["P001", "P002"]:
        with pytest.raises(ValidationError):
            schema.model_validate(
                {"declared_user": user(), "subjects": [person([alias, "C001"])]}
            )


@pytest.mark.parametrize("claims", [["unknown"], ["P001"], ["C001", "C001"]])
def test_user_support_requires_distinct_exact_claim_ids(claims):
    schema = subject_discovery_model(
        ["C001", "C002"], {"P001": "user"}, {}, canonical_user=True
    )
    with pytest.raises(ValidationError):
        schema.model_validate({"declared_user": user(claims), "subjects": []})


def test_other_participants_remain_required_and_cannot_become_the_user():
    schema = subject_discovery_model(
        ["C001"], {"P001": "user", "P002": "participant"}, {}, canonical_user=True
    )
    schema.model_validate(
        {"declared_user": user(), "subjects": [person(["P002", "C001"])]}
    )
    with pytest.raises(ValidationError):
        schema.model_validate({"declared_user": user(["C001"]), "subjects": []})
    with pytest.raises(ValidationError):
        schema.model_validate({"declared_user": user(["P002"]), "subjects": []})


def test_profile_without_canonical_user_keeps_role_occurrences_as_people():
    schema = subject_discovery_model(["C001"], {"P001": "user"}, {})
    assert list(schema.model_json_schema()["properties"]) == ["subjects"]
    schema.model_validate({"subjects": [person(["P001"])]})
