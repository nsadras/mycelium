from tests.discovery_support import discovery_response
from unittest.mock import AsyncMock

import pytest

from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.identity_planner import IdentityPlanner
from mycelium.semantic_candidates import SemanticCandidates
from tests.test_identity_plan import setup_router


@pytest.mark.asyncio
async def test_inferred_type_does_not_remove_existing_identity_candidates(
    tmp_path, monkeypatch
):
    memory, llm, _, evidence = setup_router(tmp_path)
    with memory:
        project = memory.artifacts.create_entity("project", "Original effort")
        captured = []

        async def select(_self, documents, queries, **kwargs):
            captured.append((documents, queries, kwargs))
            return sorted(documents)

        monkeypatch.setattr(SemanticCandidates, "select", select)
        llm.call_structured.side_effect = [
            discovery_response(
                {
                    "subjects": [
                        {
                            "entity_type": "artifact",
                            "title": "Renamed prototype",
                            "description": "The source-described prototype",
                            "alternate_names": [],
                            "supporting_evidence": ["C001"],
                        }
                    ]
                }
            ),
            {
                "decision": {
                    "resolution": "existing",
                    "entity_id": project.entity_id,
                    "reason": "Same source-described subject",
                    "preferred_name_update": None,
                    "aliases": [],
                }
            },
        ]
        result = await IdentityPlanner(llm, memory.artifacts, memory.config).plan(
            {"C001": evidence[0]},
            {},
            {},
            {e.entity_id: e for e in memory.artifacts.list_entities()},
            [],
            RoutingFormatter(memory.artifacts),
        )
        assert project.entity_id in captured[0][0]
        assert captured[0][2]["limit"] == 24
        assert result["subjects"][0]["entity_id"] == project.entity_id
        assert result["subjects"][0]["source_subjects"] == [
            {
                "title": "Renamed prototype",
                "description": "The source-described prototype",
                "supporting_evidence": ["C001"],
            }
        ]
        assert memory.artifacts.get_entity(project.entity_id).entity_type == "project"
        assert memory.artifacts.get_entity(project.entity_id).aliases == []


@pytest.mark.asyncio
async def test_declared_speaker_candidates_remain_people(tmp_path, monkeypatch):
    memory, llm, _, evidence = setup_router(tmp_path)
    with memory:
        evidence[0].source.segments[0].speaker = "Namesake"
        evidence[0].source.segments[0].role = "participant"
        memory.artifacts.save_source(evidence[0].source)
        project = memory.artifacts.create_entity("project", "Namesake")
        person = memory.artifacts.create_entity("person", "Namesake")
        captured = []

        async def select(_self, documents, queries, **kwargs):
            captured.append(set(documents))
            return sorted(documents)

        monkeypatch.setattr(SemanticCandidates, "select", select)
        llm.call_structured.side_effect = [
            discovery_response(
                {
                    "subjects": [
                        {
                            "entity_type": "person",
                            "title": "Namesake",
                            "description": "A speaker in the source",
                            "alternate_names": [],
                            "supporting_evidence": ["P001"],
                        }
                    ]
                }
            ),
            {
                "decision": {
                    "resolution": "existing",
                    "entity_id": person.entity_id,
                    "reason": "Same source speaker",
                    "preferred_name_update": None,
                    "aliases": [],
                }
            },
        ]
        result = await IdentityPlanner(llm, memory.artifacts, memory.config).plan(
            {"C001": evidence[0]},
            {"P001": (evidence[0].source, "Namesake", "participant")},
            {},
            {e.entity_id: e for e in memory.artifacts.list_entities()},
            [],
            RoutingFormatter(memory.artifacts),
        )
        assert captured == [{"you", person.entity_id}]
        assert project.entity_id not in captured[0]
        assert result["subjects"][0]["entity_id"] == person.entity_id


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["new", "review_required"])
async def test_final_identity_name_and_aliases_replace_discovery_proposals(
    tmp_path, monkeypatch, resolution
):
    memory, llm, _, evidence = setup_router(tmp_path)
    with memory:
        monkeypatch.setattr(SemanticCandidates, "select", AsyncMock(return_value=[]))
        evidence[0].source.segments[
            0
        ].content = (
            "The project is called Source label, also known as Source alternative."
        )
        memory.artifacts.save_source(evidence[0].source)
        final = {
            "resolution": resolution,
            "reason": "Original source establishes the spelling",
            "title_basis": "source_name",
            "title": "Source label",
            "aliases": ["Source alternative"],
        }
        if resolution == "review_required":
            final["candidate_entity_ids"] = []
        llm.call_structured.side_effect = [
            discovery_response(
                {
                    "subjects": [
                        {
                            "entity_type": "project",
                            "title": "Incorrect proposal",
                            "description": "A discovered subject",
                            "alternate_names": ["Incorrect alias"],
                            "supporting_evidence": ["C001"],
                        }
                    ]
                }
            ),
            {"decision": final},
        ]
        result = await IdentityPlanner(llm, memory.artifacts, memory.config).plan(
            {"C001": evidence[0]},
            {},
            {},
            {e.entity_id: e for e in memory.artifacts.list_entities()},
            [],
            RoutingFormatter(memory.artifacts),
        )
        node = result["subjects"][0]
        assert node["title"] == "Source label" and node["aliases"] == [
            "Source alternative"
        ]
        assert node["entity_type"] == "project"
        assert node["supporting_evidence"] == ["C001"]
        assert "Incorrect proposal" in llm.call_structured.await_args_list[1].args[1]
