import json
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
    value = {"title": "You", "entity_type": "you", "resolution": "existing",
             "entity_id": "you", "aliases": [], "supporting_evidence": ["C001"],
             "participant_evidence": ["P001"], "candidate_entity_ids": [],
             "reason": "Explicit identity evidence.", **changes}
    value["supporting_evidence"] = list(dict.fromkeys(
        value["supporting_evidence"] + value.pop("participant_evidence")
    ))
    fields = {"reason", "aliases", "supporting_evidence"}
    if changes.get("node_id") != "you":
        fields.add("resolution")
        if value["resolution"] == "existing":
            fields.update(("entity_id", "title"))
            value["title"] = changes.get("title")
        else:
            fields.update(("title", "entity_type"))
            if value["resolution"] == "review_required":
                fields.add("candidate_entity_ids")
    return {key: value[key] for key in fields}



@pytest.mark.parametrize("changes", [
    {"supporting_evidence": ["missing"]},
    {"resolution": "new", "entity_id": "", "entity_type": "person"},
    {"entity_id": "missing"},
    {"supporting_evidence": ["C001"]},
    {"candidate_entity_ids": ["missing"]},
])
def test_identity_contract_rejects_invalid_ids_and_user_binding(changes):
    schema = identity_plan_model(["C001"], {"P001": "user"}, {"you": "you"})
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": [], "user": {**subject(node_id="you"), **changes}})


def test_declared_user_is_required_separately_from_other_subjects():
    schema = identity_plan_model(["C001"], {"P001": "user"}, {"you": "you"})
    plan = schema.model_validate({"subjects": [], "user": subject(node_id="you")})
    assert list(schema.model_json_schema()["properties"]) == ["user", "subjects"]
    assert plan.user.supporting_evidence == ["C001", "P001"]
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": []})


def test_identity_contract_rejects_duplicate_existing_identity():
    schema = identity_plan_model(["C001"], {}, {"you": "you"})
    with pytest.raises(ValidationError, match="same canonical identity"):
        schema.model_validate({"subjects": [subject(participant_evidence=[]),
                                           subject(node_id="n2", participant_evidence=[])]})


@pytest.mark.parametrize("resolution,changes,error_field,error_type", [
    ("new", {"entity_id": "entity-73"}, "entity_id", "extra_forbidden"),
    ("new", {"candidate_entity_ids": ["entity-73"]}, "candidate_entity_ids", "extra_forbidden"),
    ("existing", {"entity_id": "unknown"}, "entity_id", "literal_error"),
    ("existing", {"entity_type": "person"}, "entity_type", "extra_forbidden"),
    ("review_required", {"candidate_entity_ids": ["invented"]}, "candidate_entity_ids", "literal_error"),
    ("new", {"page": True}, "page", "extra_forbidden"),
])
def test_resolution_variants_reject_impossible_states(resolution, changes, error_field, error_type):
    schema = identity_plan_model(["C001"], {}, {"you": "you", "entity-73": "organization"})
    node = subject(title="Workshop", entity_type="organization", resolution=resolution,
                   entity_id="entity-73", participant_evidence=[])
    schema.model_validate({"subjects": [node]})
    with pytest.raises(ValidationError) as error:
        schema.model_validate({"subjects": [{**node, **changes}]})
    variant = {"new": "NewIdentity", "existing": "ExistingIdentity",
               "review_required": "UnresolvedOrganizationIdentity"}[resolution]
    relevant_errors = [item for item in error.value.errors() if item["loc"][:3] == ("subjects", 0, variant)]
    assert len(relevant_errors) == 1
    assert relevant_errors[0]["loc"][3] == error_field
    assert relevant_errors[0]["type"] == error_type


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
        kind = fields["entity_type"]["const"]
        if kind == "person":
            assert candidates["items"].get("const", candidates["items"].get("enum")) == "you"
        elif kind == "organization":
            assert candidates["items"].get("const", candidates["items"].get("enum")) == "entity-73"
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
    return memory, llm, ClaimRouter(llm, memory.artifacts, memory.config), [ClaimEvidence(claim, source)]


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
    payload = json.loads(rendered)
    for alias in ("C001", "C002"):
        assert payload["claims"][alias]["citations"] == [
            {"source_id": "s1", "segment_id": "seg1"}
        ]
    assert payload["claims"]["C003"]["citations"] == [
        {"source_id": "s2", "segment_id": "seg1"}
    ]
    assert payload["sources"]["s1"]["segments"]["seg1"]["text"] == item.source.segments[0].content
    assert payload["sources"]["s2"]["segments"]["seg1"]["text"] == other_source.segments[0].content


def test_routing_evidence_retains_cross_source_context_and_missing_citations(tmp_path):
    memory, _, _, evidence = setup_router(tmp_path)
    item = evidence[0]
    context = SourceDocument(
        "s2", "agent_conversation", "earlier", "2026-09-05", "2026-08-20", ["user"],
        [SourceSegment("seg1", 0, "The exhibit will be at the library.", role="user",
                       timestamp="2026-08-20")],
        metadata={"title": "Planning discussion"},
    )
    memory.artifacts.save_source(context)
    item.claim.provenance.extend([
        ClaimProvenance("s2", ["seg1"]),
        ClaimProvenance("missing-source", ["seg1"]),
    ])
    rendered = RoutingFormatter(memory.artifacts).format_evidence({"C001": item}, {})
    payload = json.loads(rendered)
    assert payload["sources"]["s2"]["segments"]["seg1"]["text"] == context.segments[0].content
    assert payload["sources"]["s2"]["occurred_at"] == "2026-08-20"
    assert payload["sources"]["s2"]["title"] == "Planning discussion"
    assert context.recorded_at not in rendered
    assert payload["claims"]["C001"]["citations"] == [
        {"source_id": "s1", "segment_id": "seg1"},
        {"source_id": "s2", "segment_id": "seg1"},
        {"source_id": "missing-source", "segment_id": "seg1"},
    ]


def test_page_catalog_limits_sections_to_supplied_active_types(tmp_path):
    memory, _, _, _ = setup_router(tmp_path)
    person = memory.artifacts.create_entity("person", "Avery")
    payload = json.loads(RoutingFormatter.entity_catalog([person], include_sections=True))
    assert set(payload["pages"]) == {person.entity_id}
    assert payload["pages"][person.entity_id]["subject"] == person.title
    assert set(payload["section_definitions"]) == {"person"}


def route(owner="you"):
    return {"decisions": {"C001": {"prominence": "briefing", "uncertainty": None, "owner_entity": owner,
            "pages": {owner: {"section_key": "overview", "reason": "Useful statement."}},
            "reason": None}}}


def source_first_responses(plan):
    discovery, matches = [], []
    for node in plan["subjects"]:
        kind = node.get("entity_type") or node["entity_id"].split("-")[0]
        discovery.append({"entity_type": "person" if kind == "you" else kind,
            "title": node["title"] or node["entity_id"], "description": node["reason"],
            "aliases": node["aliases"], "supporting_evidence": node["supporting_evidence"]})
        decision = {"resolution": node["resolution"], "reason": node["reason"]}
        if node["resolution"] == "existing":
            decision.update(entity_id=node["entity_id"], title=node["title"], aliases=node["aliases"])
        elif node["resolution"] == "review_required":
            decision["candidate_entity_ids"] = node["candidate_entity_ids"]
        matches.append({"decision": decision})
    return [{"subjects": discovery}, *matches]



@pytest.mark.asyncio
async def test_retry_replans_after_registry_changes_without_duplicating_identity(tmp_path):
    memory, llm, router, evidence = setup_router(tmp_path)
    llm.context_window_tokens = 32768
    plan = {"subjects": [subject(title="Exhibit", entity_type="project", resolution="new",
                                entity_id="", participant_evidence=[])]}
    llm.call_structured.side_effect = [*source_first_responses(plan), ValueError("interrupted routing")]
    first = await router.route(evidence)
    assert first.failures
    assert len(first.new_entities) == 1
    for entity in first.new_entities:
        memory.artifacts.save_entity(entity)
    llm.call_structured.reset_mock()
    llm.call_structured.side_effect = [
        *source_first_responses({"subjects": [subject(resolution="existing", entity_id=first.new_entities[0].entity_id,
                              participant_evidence=[])]}),
        route(first.new_entities[0].entity_id),
    ]
    second = await router.route(evidence)
    assert not second.failures
    assert second.routes[0].owner_entity_id == first.new_entities[0].entity_id
    assert {e.entity_id for e in second.new_entities} == {first.new_entities[0].entity_id}
    assert llm.call_structured.await_count == 3


@pytest.mark.asyncio
async def test_human_identity_cannot_be_overridden_by_new_plan(tmp_path):
    memory, llm, router, evidence = setup_router(tmp_path)
    llm.context_window_tokens = 32768
    memory.artifacts.save_entity_reference(ClaimEntityReference(
        reference_id="review1", claim_id="c1", role="identity_subject", entity_id="you",
        surface=None, origin="manual",
        confidence=1.0, reason="Explicit user correction.", dream_run_id="manual",
        status="active", created_at="2026-09-04",
        identity_decision_id="review-decision",
    ))
    llm.call_structured.side_effect = source_first_responses({"subjects": [subject(title="Another person", entity_type="person",
        resolution="new", entity_id="", participant_evidence=[])]})[:1] + [
            {"assignments": {"R001": {"subject_alias": "unresolved", "reason": "The reviewed subject is absent."}}}]
    result = await router.route(evidence)
    assert result.failures and "Cannot bind human identity review R001" in result.failures[0].reason
    assert result.new_entities == []


@pytest.mark.asyncio
async def test_invented_candidate_fails_without_creating_entities_or_routing(tmp_path):
    memory, llm, router, evidence = setup_router(tmp_path)
    llm.context_window_tokens = 32768
    llm.call_structured.side_effect = source_first_responses({"subjects": [subject(
        title="Workshop", entity_type="organization", resolution="review_required",
        entity_id="", participant_evidence=[], candidate_entity_ids=["invented"],
    )]})
    result = await router.route(evidence)
    assert len(result.failures) == 1
    assert result.new_entities == []
    assert result.routes == []
    assert llm.call_structured.await_count == 2
    assert [e.entity_id for e in memory.artifacts.list_entities()] == ["you"]


@pytest.mark.asyncio
async def test_identity_candidates_survive_routing_and_repository_roundtrip(tmp_path):
    from mycelium.artifacts import EntityRecord

    memory, llm, router, evidence = setup_router(tmp_path)
    llm.context_window_tokens = 32768
    for entity_id in ["person-a", "person-b"]:
        memory.artifacts.save_entity(EntityRecord(
            entity_id, "person", entity_id, entity_id, [], "active", "2026-09-07", "2026-09-07",
        ))
    llm.call_structured.side_effect = [*source_first_responses({"subjects": [subject(
        title="Unknown organizer", entity_type="person", resolution="review_required",
        entity_id="", participant_evidence=[], candidate_entity_ids=["person-a", "person-b"],
    )]}), {"decisions": {"C001": {"prominence": "briefing", "pages": {"person-unknown-organizer": {"section_key": "goals_plans", "reason": "The unresolved organizer made the commitment."}}, "owner_entity": "person-unknown-organizer", "reason": None, "uncertainty": "Which organizer is unknown."}}}]
    result = await router.route(evidence)
    assert not result.failures
    assert len(result.new_entities) == 1
    for entity in result.new_entities:
        memory.artifacts.save_entity(entity)
    assert len(result.entity_decisions) == 1
    decision = result.entity_decisions[0]
    memory.artifacts.save_entity_resolution_decision(decision)
    stored = memory.artifacts.get_entity_resolution_decision(decision.decision_id)
    assert stored.candidate_entity_ids == ["person-a", "person-b"]
    assert result.routes[0].identity_blocker_ids == (decision.decision_id,)
    rendered = RoutingFormatter(memory.artifacts).format_pending_identity_proposals([stored])
    assert "candidate_entity_ids=person-a,person-b" in rendered
    stored.candidate_entity_ids = ["missing"]
    with pytest.raises(FileNotFoundError):
        memory.artifacts.save_entity_resolution_decision(stored)


def test_identity_catalog_retains_staged_founding_evidence(tmp_path):
    from mycelium.artifacts import EntityResolutionDecision, EntityRecord
    memory, _, _, evidence = setup_router(tmp_path)
    entity = EntityRecord("project-new", "project", "Exhibit", "exhibit", [], "active", "2026-09-04", "2026-09-04")
    decision = EntityResolutionDecision("d1", "entity_creation", entity.entity_id, "project", entity.title,
        ["s1"], ["c1"], ["seg1"], 0.9, "Founding subject evidence.", "accepted", "build", "2026-09-04",
        identity_evidence_claim_ids=["c1"], reviewer_note="Confirmed this identity from the source.")
    formatter = RoutingFormatter(memory.artifacts)
    assert evidence[0].claim.text not in formatter.entity_planning_catalog([entity])
    rendered = formatter.entity_planning_catalog([entity], [decision])
    assert evidence[0].claim.text in rendered
    assert '"claim_id": "c1"' in rendered
    assert '"source_id": "s1"' in rendered
    assert '"segment_ids": ["seg1"]' in rendered
    assert decision.reason not in rendered
    assert decision.reviewer_note in rendered
    pending = formatter.format_pending_identity_proposals([decision])
    assert decision.reason not in pending
    assert decision.reviewer_note in pending
    assert evidence[0].claim.text in pending
    assert memory.artifacts.list_entity_resolution_decisions() == []


def test_participant_only_identity_derives_binding_from_one_citation_list():
    from mycelium.identity_plan import planned_subjects

    schema = identity_plan_model(["C001"], {"P001": "participant"}, {})
    node = subject(resolution="new", title="Ava", entity_type="person",
                   supporting_evidence=[], participant_evidence=["P001"])
    plan = schema.model_validate({"subjects": [node]}).model_dump()
    nodes = planned_subjects(plan, {}, {"P001": ("source", "Ava", "participant")})
    assert nodes[0]["participant_evidence"] == ["P001"]
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": [{**node, "entity_type": "project"}]})
    with pytest.raises(ValidationError, match="Each participant"):
        schema.model_validate({"subjects": [node, {**node, "title": "Other"}]})


def test_native_identity_evidence_domains_match_declared_entity_types():
    schema = identity_plan_model(["C001"], {"P001": "participant"}, {"person": "person", "org": "organization"}).model_json_schema()
    person = schema["$defs"]["ExistingPersonIdentity"]["properties"]
    other = schema["$defs"]["ExistingIdentity"]["properties"]
    assert person["entity_id"]["const"] == "person"
    assert set(person["supporting_evidence"]["items"]["enum"]) == {"C001", "P001"}
    assert other["entity_id"]["const"] == "org"
    assert other["supporting_evidence"]["items"]["const"] == "C001"


def test_declared_user_without_claims_has_no_other_subject_domain():
    schema = identity_plan_model([], {"P001": "user"}, {"you": "you"})
    schema.model_validate({"subjects": [], "user": {
        "reason": "Declared speaker.", "supporting_evidence": ["P001"], "aliases": [],
    }})
    assert schema.model_json_schema()["properties"]["subjects"]["maxItems"] == 0


@pytest.mark.asyncio
async def test_review_assignment_binds_one_discovered_subject_without_hiding_the_other(tmp_path):
    memory, llm, router, evidence = setup_router(tmp_path)
    llm.context_window_tokens = 32768
    memory.artifacts.save_entity_reference(ClaimEntityReference("review1", "c1", "identity_subject", "The user", "you",
        1., "Explicit review", "manual", "review", "active", "2026-09-04", identity_decision_id="d1"))
    llm.call_structured.side_effect = [
        {"subjects": [
            {"entity_type": "person", "title": "The user", "description": "The person preparing the exhibit", "aliases": [], "supporting_evidence": ["C001"]},
            {"entity_type": "project", "title": "Exhibit", "description": "The exhibit being prepared", "aliases": [], "supporting_evidence": ["C001"]}]},
        {"assignments": {"R001": {"subject_alias": "S001", "reason": "The reviewed person"}}},
        {"decision": {"resolution": "new", "reason": "Separate project"}}, route("project-exhibit")]
    result = await router.route(evidence)
    assert not result.failures
    assert {e.entity_id for e in result.new_entities} == {"you", "project-exhibit"}
    discovery_user = llm.call_structured.await_args_list[0].args[1]
    assert "identity_references" not in discovery_user and "review1" not in discovery_user
    plan = memory.artifacts.list_identity_work_units()[0].entity_plan
    assert plan["review_bindings"]["R001"]["subject_alias"] == "S001"
    assert plan["subjects"][0]["entity_id"] == "you"
    assert "R001" in plan["subjects"][0]["supporting_evidence"]
    assert "R001" not in plan["subjects"][1]["supporting_evidence"]


@pytest.mark.asyncio
async def test_matching_a_provisional_identity_preserves_its_pending_review_on_new_placements(tmp_path):
    from mycelium.artifacts import EntityResolutionDecision
    memory, llm, router, evidence = setup_router(tmp_path)
    llm.context_window_tokens = 32768
    entity = memory.artifacts.create_entity("person", "Unidentified organizer", materialization_state="provisional")
    decision = EntityResolutionDecision("pending", "entity_creation", entity.entity_id, "person", entity.title,
        ["s1"], ["c1"], ["seg1"], .8, "Which organizer is unknown", "review_required", "earlier", "2026-09-04",
        identity_evidence_claim_ids=["c1"], proposed_scope="independent", proposed_page_state="provisional")
    memory.artifacts.save_entity_resolution_decision(decision)
    placement = route(entity.entity_id)
    placement["decisions"]["C001"]["pages"][entity.entity_id]["section_key"] = "goals_plans"
    llm.call_structured.side_effect = [*source_first_responses({"subjects": [subject(resolution="existing",
        entity_id=entity.entity_id, participant_evidence=[])]}), placement]
    result = await router.route(evidence)
    assert not result.failures
    assert result.routes[0].identity_blocker_ids == ("pending",)
    assert memory.artifacts.get_entity_resolution_decision("pending").review_state == "review_required"
    assert {e.entity_id for e in result.new_entities} == {entity.entity_id}
