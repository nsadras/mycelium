from typing import get_args

import pytest

from mycelium.ontology import (
    CLAIM_TYPES,
    DISCOVERABLE_ENTITY_TYPES,
    ENTITY_ONTOLOGY,
    ENTITY_TYPES,
    INDEPENDENT_SUBJECT_SCOPES,
    SUBJECT_SCOPES,
    SUBJECT_SCOPE_ONTOLOGY,
    ClaimType,
    DiscoverableEntityType,
    default_section,
    ontology_response,
)
from mycelium.structured_outputs import (
    ExtractedClaimOutput,
)
from mycelium.identity_plan import IdentitySubject
from server.api.memory_artifacts import get_ontology


def test_ontology_registry_is_internally_complete() -> None:
    assert tuple(definition.key for definition in ENTITY_ONTOLOGY) == ENTITY_TYPES
    assert len(ENTITY_TYPES) == len(set(ENTITY_TYPES))
    assert set(get_args(ClaimType)) == set(CLAIM_TYPES)
    assert set(get_args(DiscoverableEntityType)) == set(DISCOVERABLE_ENTITY_TYPES)

    for definition in ENTITY_ONTOLOGY:
        keys = definition.section_keys()
        assert len(keys) == len(set(keys))
        assert set(definition.defaults()) == set(CLAIM_TYPES)
        assert set(definition.defaults().values()) <= set(keys)
        if definition.project_role_section is not None:
            assert definition.project_role_section in keys


def test_structured_model_contracts_derive_from_the_ontology() -> None:
    claim_schema = ExtractedClaimOutput.model_json_schema()
    identity_type_schema = IdentitySubject.model_json_schema()

    assert set(claim_schema["properties"]["claim_type"]["enum"]) == set(CLAIM_TYPES)
    assert set(identity_type_schema["properties"]["entity_type"]["enum"]) == set(
        ENTITY_TYPES
    )


def test_subject_representation_registry_is_internally_complete() -> None:
    assert tuple(
        definition.key for definition in SUBJECT_SCOPE_ONTOLOGY
    ) == SUBJECT_SCOPES
    assert len(SUBJECT_SCOPES) == len(set(SUBJECT_SCOPES))
    assert set(INDEPENDENT_SUBJECT_SCOPES) == {"materialized", "provisional"}
    assert {
        (definition.key, definition.persisted_scope, definition.page_state)
        for definition in SUBJECT_SCOPE_ONTOLOGY
    } == {
        ("materialized", "independent", "materialized"),
        ("provisional", "independent", "provisional"),
        ("component", "component", "no_page"),
        ("occurrence", "occurrence", "no_page"),
        ("standalone_event", "standalone_event", "no_page"),
        ("context", "context", "no_page"),
    }

def test_declared_default_section_rules_are_centralized() -> None:
    assert default_section("artifact", "state", None) == "current_state"
    assert default_section("project", "state", None) == "current_status"
    assert default_section("you", "observation", None) == "current_context"
    assert (
        default_section("person", "relationship", "project_role") == "shared_projects"
    )

    assert (
        default_section("artifact", "relationship", "project_role")
        == "related_projects"
    )


@pytest.mark.asyncio
async def test_ontology_api_returns_the_authoritative_registry() -> None:
    response = await get_ontology()

    assert response == ontology_response()
    assert "needs_review" in {
        section["key"]
        for definition in response["entity_types"]
        for section in definition["sections"]
    }
