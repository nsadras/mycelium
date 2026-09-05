from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from mycelium import Mycelium
from mycelium.artifacts import ClaimEntityReference, ClaimProvenance, MemoryClaim, SourceDocument, SourceSegment
from mycelium.consolidation import ClaimRouter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.identity_plan import identity_plan_model


def subject(**changes):
    return {"node_id": "n1", "title": "You", "entity_type": "you", "resolution": "existing",
            "entity_id": "you", "aliases": [], "supporting_evidence": ["C001"],
            "participant_evidence": ["P001"], "candidate_entity_ids": [],
            "reason": "Explicit identity evidence.", "confidence": 1.0, **changes}


@pytest.mark.parametrize("changes", [
    {"supporting_evidence": ["missing"]},
    {"resolution": "new", "entity_id": "", "entity_type": "person"},
    {"entity_id": "missing"},
    {"participant_evidence": []},
    {"candidate_entity_ids": ["missing"]},
])
def test_identity_contract_rejects_invalid_ids_and_user_binding(changes):
    schema = identity_plan_model(["C001"], {"P001": "user"}, {"you": "you"})
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": [], "user": subject(**{"node_id": "you", **changes})})


def test_declared_user_is_required_separately_from_other_subjects():
    schema = identity_plan_model(["C001"], {"P001": "user"}, {"you": "you"})
    plan = schema.model_validate({"subjects": [], "user": subject(node_id="you")})
    assert plan.user.entity_id == "you"
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": []})


def test_identity_contract_rejects_duplicate_existing_identity():
    schema = identity_plan_model(["C001"], {}, {"you": "you"})
    with pytest.raises(ValidationError, match="same canonical identity"):
        schema.model_validate({"subjects": [subject(participant_evidence=[]),
                                           subject(node_id="n2", participant_evidence=[])]})


@pytest.mark.parametrize("changes", [
    {"resolution": "new", "entity_id": "entity-73"},
    {"resolution": "new", "candidate_entity_ids": ["entity-73"]},
    {"resolution": "existing", "entity_id": "unknown"},
    {"resolution": "existing", "entity_id": "entity-73", "entity_type": "person"},
    {"resolution": "review_required", "candidate_entity_ids": ["invented"]},
    {"page": True},
])
def test_resolution_variants_reject_impossible_states(changes):
    schema = identity_plan_model(["C001"], {}, {"you": "you", "entity-73": "organization"})
    node = subject(title="Workshop", entity_type="organization", resolution="new",
                   entity_id="", participant_evidence=[])
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": [{**node, **changes}]})


@pytest.mark.parametrize("registry", [{}, {"you": "you"}, {"entity-73": "organization"}])
def test_new_and_unresolved_identities_do_not_require_an_existing_match(registry):
    schema = identity_plan_model(["C001"], {}, registry)
    for resolution in ("new", "review_required"):
        node = subject(title="Workshop", entity_type="organization", resolution=resolution,
                       entity_id="", participant_evidence=[])
        assert schema.model_validate({"subjects": [node]}).subjects[0].resolution == resolution


def test_native_schema_constrains_candidate_ids_before_model_generation():
    schema = identity_plan_model(["C001"], {}, {"you": "you", "entity-73": "organization"})
    variants = schema.model_json_schema()["$defs"]
    for variant in variants.values():
        fields = variant.get("properties", {})
        if "candidate_entity_ids" not in fields:
            continue
        candidates = fields["candidate_entity_ids"]
        if fields["resolution"].get("const") == "review_required":
            assert set(candidates["items"]["enum"]) == {"you", "entity-73"}
        else:
            assert candidates["maxItems"] == 0


def setup_router(tmp_path):
    memory = Mycelium(tmp_path / "store")
    source = SourceDocument("s1", "agent_conversation", "session", "2026-09-04", None, ["user"],
                            [SourceSegment("seg1", 0, "I am preparing an exhibit.", role="user")])
    memory.artifacts.save_source(source)
    claim = MemoryClaim("c1", "The user is preparing an exhibit.", [],
                        [ClaimProvenance("s1", ["seg1"])], "2026-09-04")
    memory.artifacts.save_claim(claim)
    llm = AsyncMock()
    return memory, llm, ClaimRouter(llm, memory.artifacts), [ClaimEvidence(claim, source)]


def test_shared_source_text_is_included_once_with_each_claim_reference(tmp_path):
    memory, _, _, evidence = setup_router(tmp_path)
    item = evidence[0]
    second = MemoryClaim("c2", "The exhibit is being prepared.", [],
                         [ClaimProvenance("s1", ["seg1"])], "2026-09-04")
    # Segment IDs are scoped to sources, not globally unique.
    other_source = SourceDocument("s2", "agent_conversation", "other", "2026-09-04", None, [],
                                 [SourceSegment("seg1", 0, "The venue is open.")])
    third = MemoryClaim("c3", "The venue is open.", [],
                        [ClaimProvenance("s2", ["seg1"])], "2026-09-04")
    rendered = RoutingFormatter(memory.artifacts).format_evidence(
        {"C001": item, "C002": ClaimEvidence(second, item.source),
         "C003": ClaimEvidence(third, other_source)}, {},
    )
    assert rendered.count(item.source.segments[0].content) == 1
    assert rendered.count("cited_source_evidence=source_id=s1; segment_id=seg1") == 2
    assert "cited_source_evidence=source_id=s2; segment_id=seg1" in rendered
    assert "[source_id=s1; segment_id=seg1]" in rendered
    assert "[source_id=s2; segment_id=seg1]" in rendered
    assert other_source.segments[0].content in rendered


def route(owner="you"):
    return {"decisions": {"C001": {"route_kind": "general", "owner_entity": owner,
            "pages": [{"entity_id": owner, "section_key": "overview", "reason": "Useful statement."}],
            "reason": "Source-grounded owner.", "confidence": 1.0}}}


@pytest.mark.asyncio
async def test_retry_reuses_plan_and_allocated_identity_after_partial_commit(tmp_path):
    memory, llm, router, evidence = setup_router(tmp_path)
    plan = {"subjects": [subject(title="Exhibit", entity_type="project", resolution="new",
                                entity_id="", participant_evidence=[])]}
    llm.call_structured.side_effect = [plan, ValueError("interrupted routing")]
    first = await router.route(evidence)
    assert first.failures
    assert len(first.new_entities) == 1
    for entity in first.new_entities:
        memory.artifacts.save_entity(entity)
    llm.call_structured.reset_mock()
    llm.call_structured.side_effect = [route(first.new_entities[0].entity_id)]
    second = await router.route(evidence)
    assert not second.failures
    assert second.routes[0].owner_entity_id == first.new_entities[0].entity_id
    assert {e.entity_id for e in second.new_entities} == {first.new_entities[0].entity_id}
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_human_identity_cannot_be_overridden_by_new_plan(tmp_path):
    memory, llm, router, evidence = setup_router(tmp_path)
    memory.artifacts.save_entity_reference(ClaimEntityReference(
        reference_id="review1", claim_id="c1", role="identity_subject", entity_id="you",
        surface=None, origin="manual",
        confidence=1.0, reason="Explicit user correction.", dream_run_id="manual",
        status="active", created_at="2026-09-04",
    ))
    llm.call_structured.side_effect = [{"subjects": [subject(title="Another person", entity_type="person",
        resolution="new", entity_id="", participant_evidence=[])]}]
    result = await router.route(evidence)
    assert result.failures and "human identity" in result.failures[0].reason
    assert result.new_entities == []


@pytest.mark.asyncio
async def test_invented_candidate_fails_without_creating_entities_or_routing(tmp_path):
    memory, llm, router, evidence = setup_router(tmp_path)
    llm.call_structured.return_value = {"subjects": [subject(
        title="Workshop", entity_type="organization", resolution="review_required",
        entity_id="", participant_evidence=[], candidate_entity_ids=["invented"],
    )]}
    result = await router.route(evidence)
    assert len(result.failures) == 1
    assert result.new_entities == []
    assert result.routes == []
    assert llm.call_structured.await_count == 1
    assert [e.entity_id for e in memory.artifacts.list_entities()] == ["you"]
