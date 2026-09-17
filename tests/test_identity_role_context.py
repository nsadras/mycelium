import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mycelium.identity_planner import IdentityPlanner
from mycelium.semantic_candidates import SemanticCandidates
from tests.discovery_support import discovery_response
from tests.test_identity_plan import setup_router


@pytest.mark.asyncio
async def test_matching_receives_same_source_user_binding_without_subject_assignment(
    tmp_path, monkeypatch
):
    memory, llm, _, evidence = setup_router(tmp_path)
    with memory:
        monkeypatch.setattr(
            SemanticCandidates, "select", AsyncMock(return_value=["you"])
        )
        llm.call_structured.side_effect = [
            discovery_response(
                {
                    "subjects": [
                        {
                            "entity_type": "person",
                            "title": "Rae",
                            "description": "The person described in the source",
                            "alternate_names": [],
                            "supporting_evidence": ["C001"],
                        }
                    ],
                    "declared_user": {
                        "description": "The declared user",
                        "alternate_names": [],
                        "supporting_claims": ["C001", "C002"],
                    },
                }
            ),
            {
                "decision": {
                    "resolution": "existing",
                    "entity_id": "you",
                    "title": "You",
                    "aliases": [],
                    "reason": "The named person is the declared source user",
                }
            },
        ]
        payload = {
            "claims": {
                c: {
                    "text": c,
                    "identity_references": [],
                    "citations": [{"source_id": sid, "segment_id": "line"}],
                }
                for c, sid in [("C001", "a"), ("C002", "b")]
            },
            "sources": {
                sid: {"segments": {"line": {"text": sid}}} for sid in ("a", "b")
            },
            "participants": {
                "P001": {"name": "Rae", "role": "user", "source_id": "a"},
                "P002": {"name": "Other source user", "role": "user", "source_id": "b"},
            },
        }
        formatter = SimpleNamespace(
            format_evidence=lambda *_: json.dumps(payload),
            identity_review_catalog=lambda *_: "none",
        )
        result = await IdentityPlanner(llm, memory.artifacts, memory.config).plan(
            {"C001": evidence[0], "C002": evidence[0]},
            {
                "P001": (SimpleNamespace(source_id="a"), "Rae", "user"),
                "P002": (SimpleNamespace(source_id="b"), "Other source user", "user"),
            },
            {},
            {e.entity_id: e for e in memory.artifacts.list_entities()},
            [],
            formatter,
        )
        request = llm.call_structured.await_args_list[1].args[1]
        scoped = json.loads(
            request.split("Source evidence:\n", 1)[1].split(
                "\n\nRelevant human reviews:", 1
            )[0]
        )
        assert scoped["participants"] == {
            "P001": {**payload["participants"]["P001"], "canonical_entity_id": "you"}
        }
        assert set(scoped["sources"]) == {"a"}
        assert len(result["subjects"]) == 1
        assert result["subjects"][0]["entity_id"] == "you"
        assert payload["participants"]["P001"].get("canonical_entity_id") is None
