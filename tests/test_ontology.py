from typing import get_args

import pytest

from mycelium import prompts
from mycelium.ontology import (
    CLAIM_TYPES,
    DISCOVERABLE_ENTITY_TYPES,
    ENTITY_ONTOLOGY,
    ENTITY_TYPES,
    ClaimType,
    DiscoverableEntityType,
    default_section,
    entity_type_prompt_catalog,
    ontology_response,
    section_prompt_catalog,
)
from mycelium.structured_outputs import (
    ExtractedClaimOutput,
    IdentityTypeProposalOutput,
)
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
    identity_type_schema = IdentityTypeProposalOutput.model_json_schema()

    assert set(claim_schema["properties"]["claim_type"]["enum"]) == set(CLAIM_TYPES)
    assert set(identity_type_schema["properties"]["entity_type"]["enum"]) == set(
        DISCOVERABLE_ENTITY_TYPES
    )


def test_prompt_catalogs_derive_keys_and_descriptions_from_the_registry() -> None:
    entity_catalog = entity_type_prompt_catalog(discoverable_only=True)
    section_catalog = section_prompt_catalog()

    for definition in ENTITY_ONTOLOGY:
        if definition.discoverable:
            assert definition.description in entity_catalog
        assert f"type={definition.key}" in section_catalog
        for section in definition.sections:
            assert f"{section.key}={section.description}" in section_catalog

    extraction_system, _ = prompts.claim_extraction_prompt(
        "agent_conversation", "source-1", None, "[segment-1] Example"
    )
    assert f"claim_type ({'/'.join(CLAIM_TYPES)})" in extraction_system


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
