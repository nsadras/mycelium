import pytest
from pydantic import ValidationError

from mycelium.artifacts import EntityRecord
from mycelium.ontology import ENTITY_TYPES
from mycelium.page_admission import (
    ADMISSION_BASES,
    NO_PAGE_BASIS,
    page_admission_model,
)


def entity(kind, state="provisional"):
    return EntityRecord(
        kind,
        kind,
        kind,
        kind,
        [],
        "active",
        "2031-01-01",
        "2031-01-01",
        materialization_state=state,
    )


def test_admission_has_an_explicit_basis_for_every_entity_type():
    assert set(ADMISSION_BASES) == set(ENTITY_TYPES)
    for kind in ENTITY_TYPES:
        schema = page_admission_model(["C001"], {kind: entity(kind)})
        node = {
            "reason": "Source-backed context",
            "basis": ADMISSION_BASES[kind][0],
            "supporting_claims": ["C001"],
        }
        schema.model_validate({"page_admissions": {kind: node}})
        with pytest.raises(ValidationError, match="cited source claims"):
            schema.model_validate(
                {"page_admissions": {kind: {**node, "supporting_claims": []}}}
            )
        with pytest.raises(ValidationError):
            schema.model_validate(
                {"page_admissions": {kind: {**node, "supporting_claims": ["invented"]}}}
            )
        schema.model_validate(
            {
                "page_admissions": {
                    kind: {**node, "basis": NO_PAGE_BASIS, "supporting_claims": []}
                }
            }
        )


def test_existing_pages_are_not_readmitted():
    schema = page_admission_model(
        ["C001"], {"person": entity("person", "materialized")}
    )
    schema.model_validate({"page_admissions": {}})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "page_admissions": {
                    "topic": {
                        "basis": "independent_topic_context",
                        "reason": "Guess",
                        "supporting_claims": ["C001"],
                    }
                }
            }
        )
