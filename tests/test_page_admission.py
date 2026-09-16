import pytest
from pydantic import ValidationError

from mycelium.artifacts import EntityRecord
from mycelium.ontology import ENTITY_TYPES, section_keys
from mycelium.page_admission import (
    ADMISSION_BASES,
    NO_PAGE_BASIS,
    page_admission_model,
    typed_page_plan_model,
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


def test_native_section_schema_is_specific_to_each_actual_entity_id():
    kinds = {"person-1": "person", "project-1": "project", "event-1": "event"}
    model = typed_page_plan_model(["C001"], kinds)
    root = model.model_json_schema()
    definition = root["$defs"]["TypedPagePlacement"]["properties"]["pages"]
    assert definition["additionalProperties"] is False
    assert set(definition["properties"]) == set(kinds)
    for eid, kind in kinds.items():
        assert set(
            definition["properties"][eid]["properties"]["section_key"]["enum"]
        ) == set(section_keys(kind))
    value = {
        "pages": {"person-1": {"section_key": "follow_ups", "reason": "Wrong type"}},
        "owner_entity": "person-1",
        "reason": None,
        "uncertainty": None,
        "prominence": "briefing",
    }
    with pytest.raises(ValidationError, match="selected entity type"):
        model.model_validate({"decisions": {"C001": value}})


def test_empty_page_domain_preserves_explicit_deferral():
    model = typed_page_plan_model(["C001"], {})
    value = {
        "pages": {},
        "owner_entity": "",
        "reason": "No admitted subject page",
        "uncertainty": None,
        "prominence": "detail",
    }
    assert (
        model.model_validate({"decisions": {"C001": value}}).model_dump()["decisions"][
            "C001"
        ]
        == value
    )
