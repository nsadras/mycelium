from typing import get_args

import pytest

from mycelium.ontology import (
    CLAIM_TYPES,
    DISCOVERABLE_ENTITY_TYPES,
    ENTITY_ONTOLOGY,
    ENTITY_TYPES,
    ClaimType,
    DiscoverableEntityType,
    ontology_response,
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


@pytest.mark.asyncio
async def test_ontology_api_returns_the_authoritative_registry() -> None:
    response = await get_ontology()

    assert response == ontology_response()
    assert "needs_review" in {
        section["key"]
        for definition in response["entity_types"]
        for section in definition["sections"]
    }
