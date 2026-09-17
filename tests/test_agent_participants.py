from tests.discovery_support import discovery_response
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.consolidation_resolution import ResolutionArtifacts
from mycelium.identity_planner import IdentityPlanner
from mycelium.semantic_candidates import SemanticCandidates


def evidence(source_type, source_id="source"):
    source = SourceDocument(
        source_id,
        source_type,
        source_id,
        "2031-05-06",
        None,
        [],
        [
            SourceSegment("s1", 0, "A reported event.", "Rae", "user"),
            SourceSegment("s2", 1, "A second report.", "Rae", "user"),
            SourceSegment("s3", 2, "An answer.", "Assistant", "assistant"),
            SourceSegment("s4", 3, "A tool result.", "Tool", "tool"),
            SourceSegment("s5", 4, "Another speaker.", "Casey", "participant"),
            SourceSegment("s6", 5, "An unnamed speaker.", None, None),
        ],
    )
    claim = MemoryClaim(
        "c1",
        "A reported event.",
        [],
        [ClaimProvenance(source_id, ["s1"])],
        "2031-05-06",
    )
    return ClaimEvidence(claim, source)


@pytest.mark.parametrize(
    "source_type,expected",
    [
        ("agent_conversation", {("Rae", "user")}),
        (
            "meeting_transcript",
            {
                ("Rae", "user"),
                ("Assistant", "assistant"),
                ("Tool", "tool"),
                ("Casey", "participant"),
            },
        ),
        (
            "multi_party_conversation",
            {
                ("Rae", "user"),
                ("Assistant", "assistant"),
                ("Tool", "tool"),
                ("Casey", "participant"),
            },
        ),
        ("tool_result", set()),
        ("document", set()),
    ],
)
def test_participants_follow_declared_source_roles(source_type, expected):
    item = evidence(source_type)
    occurrences = ResolutionArtifacts.participant_occurrences([item, item])
    assert {(name, role) for _, name, role in occurrences.values()} == expected
    assert len(occurrences) == len(expected)
    assert all(
        source.source_id == item.source.source_id
        for source, _, _ in occurrences.values()
    )


def test_participant_scope_does_not_import_other_sources():
    first, second = (
        evidence("agent_conversation", "first"),
        evidence("agent_conversation", "second"),
    )
    participants = ResolutionArtifacts.participant_occurrences(
        [first, second], source_ids={"second"}
    )
    assert {source.source_id for source, _, _ in participants.values()} == {"second"}
    assert ResolutionArtifacts.participant_occurrences([first], source_ids=set()) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ["user", "none"])
async def test_declared_user_identity_respects_configured_profile(
    tmp_path, monkeypatch, profile
):
    with Mycelium(tmp_path / "store", memory_profile=profile) as memory:
        item = evidence("agent_conversation")
        memory.artifacts.save_source(item.source)
        memory.artifacts.save_claim(item.claim)
        llm = AsyncMock()
        llm.call_structured.side_effect = [
            discovery_response(
                {
                    "declared_user": {
                        "supporting_claims": [],
                        "description": "The source speaker",
                        "alternate_names": [],
                    },
                    "subjects": [],
                }
            )
            if profile == "user"
            else discovery_response(
                {
                    "subjects": [
                        {
                            "entity_type": "person",
                            "title": "Rae",
                            "description": "The source speaker",
                            "alternate_names": [],
                            "supporting_evidence": ["P001"],
                        }
                    ]
                }
            ),
            {
                "decision": {
                    "resolution": "new",
                    "reason": "A distinct source speaker",
                    "title_basis": "source_name",
                    "title": "Rae",
                    "aliases": [],
                }
            },
        ]
        selection = AsyncMock(return_value=[])
        monkeypatch.setattr(SemanticCandidates, "select", selection)
        result = await IdentityPlanner(llm, memory.artifacts, memory.config).plan(
            {"C001": item},
            ResolutionArtifacts.participant_occurrences([item]),
            {},
            {e.entity_id: e for e in memory.artifacts.list_entities()},
            [],
            RoutingFormatter(memory.artifacts),
        )
        subject = result["subjects"][0]
        assert subject["supporting_evidence"] == ["P001"]
        if profile == "user":
            assert subject["resolution"] == "existing" and subject["entity_id"] == "you"
            selection.assert_not_awaited()
            assert llm.call_structured.await_count == 1
        else:
            assert subject["resolution"] == "new" and subject["entity_type"] == "person"
            selection.assert_awaited_once()
            assert llm.call_structured.await_count == 2
