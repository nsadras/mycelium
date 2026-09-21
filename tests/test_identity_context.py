"""Binding continuity and explicit corrections; model quality is checked by native runs."""

from copy import deepcopy
from dataclasses import asdict, replace
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium, identity_context, memory_contract
from mycelium.artifacts import ExtractionBatchState, SourceSegment
from mycelium.operations import SourceInput
from mycelium.organization import IdentityReviewService, EntityCurationService
from tests.test_view_lifecycle import views_fixture


def retained(payload, name="Sam"):
    pid = payload["participants"][0]["id"]
    sid = payload["participants"][0]["subject_id"] or payload["new_subject_ids"][0]
    return {"subjects": [{"id": sid, "title": name, "entity_type": "person", "participant_ids": [pid]}],
            "memories": [{"id": "m", "text": "Sam is preparing a plan.", "subject_ids": [sid],
                          "segment_ids": [payload["segments"][0]["id"]]}], "changes": []}


@pytest.mark.asyncio
async def test_source_bindings_survive_restart_and_do_not_merge_named_speakers(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        captured = await memory.ingest_source(SourceInput("Two Sams", "meeting", source_type="meeting_transcript",
            segments=(SourceSegment("a", 0, "I am preparing a plan.", speaker="Sam", participant_id="speaker-0"),
                      SourceSegment("b", 1, "I am testing it.", speaker="Sam", participant_id="speaker-1"))))
        source = memory.artifacts.get_source(captured.source_ids[0])
        retainer = memory.consolidator.retainer
        payload = await retainer.input(source, source.segments[:1], "first", prior_ids=[])
        first, second = payload["participants"]
        assert first["id"] != second["id"]
        assert first["subject_id"] is None and second["subject_id"] is None
        with memory.db.transaction():
            ids = retainer.persist(source, "first", payload, retained(payload))
        original = memory.artifacts.get_entity(identity_context.binding(memory.artifacts, first["id"])["entity_id"])
        episode = memory.artifacts.get_episode(captured.episode_ids[0])
        episode.claim_ids = ids
        episode.extraction_batches = [ExtractionBatchState("first", 0, [source.segments[0].segment_id], status="complete"),
                                      ExtractionBatchState("second", 1, [source.segments[1].segment_id])]
        episode.extraction_status = "partial"
        memory.artifacts.save_episode(episode)
    with Mycelium(tmp_path) as memory:
        source = memory.artifacts.get_source(captured.source_ids[0])
        payload = await memory.consolidator.retainer.input(source, source.segments[1:], "second", prior_ids=[])
        assert payload["participants"][0]["subject_id"] == original.entity_id
        assert payload["participants"][1]["subject_id"] is None
        # The identity and distinguishing evidence arrive even with no retrieved/recent claims.
        candidate = next(s for s in payload["existing_subjects"] if s["id"] == original.entity_id)
        assert candidate["evidence"][0]["id"] == ids[0]
        other = replace(source, source_id="another-recording")
        assert identity_context.participant_id(other, other.segments[0]) != first["id"]
        target = memory.artifacts.create_entity("person", "Samuel Porter")
        bound = identity_context.binding(memory.artifacts, first["id"])
        reviewed = IdentityReviewService(memory.artifacts).review(bound["decision_id"], "approve", entity_id=target.entity_id)
        assert reviewed.entity_id == target.entity_id
        assert identity_context.participants(memory.artifacts, source)[0]["binding_origin"] == "user"
        assert memory.artifacts.get_entity(target.entity_id).title == "Samuel Porter"
        # A later batch may reference the corrected identity directly, without
        # redeclaring its binding. Keep the same review scope and decision ID.
        payload = await memory.consolidator.retainer.input(source, source.segments[1:], "second", prior_ids=[])
        output = {"subjects": [], "memories": [{"id": "m", "text": "Samuel Porter prepared the plan being tested.",
            "subject_ids": [target.entity_id], "segment_ids": [source.segments[1].segment_id]}], "changes": []}
        with memory.db.transaction():
            later = memory.consolidator.retainer.persist(source, "second", payload, output)
        ref, = memory.artifacts.list_entity_references(claim_id=later[0], status="active")
        assert ref.identity_decision_id == reviewed.decision_id
        assert set(memory.artifacts.get_entity_resolution_decision(reviewed.decision_id).supporting_claim_ids) == set(ids + later)
        assert identity_context.participants(memory.artifacts, source)[0]["binding_origin"] == "user"
        EntityCurationService(memory.artifacts, memory.wiki, memory.consolidator.materializer).merge(target.entity_id, original.entity_id)
        assert identity_context.participants(memory.artifacts, source)[0]["subject_id"] == original.entity_id


def test_binding_contract_scopes_participants_without_redeclaring_existing_subjects():
    payload = {"participants": [{"id": "p", "subject_id": "person"}], "segments": [{"id": "s"}],
               "existing_subjects": [{"id": "person", "entity_type": "person"}, {"id": "project", "entity_type": "project"}],
               "new_subject_ids": ["new"]}
    value = {"subjects": [], "memories": [{"id": "m", "text": "An existing subject.",
        "subject_ids": ["person"], "segment_ids": ["s"]}], "changes": []}
    model = memory_contract.retention_model(payload)
    model.model_validate(value)
    for sid in ("new", "project"):
        with pytest.raises(ValueError):
            model.model_validate({**value, "subjects": [{"id": sid, "title": "Changed",
                "entity_type": "person", "participant_ids": ["p"]}]})


@pytest.mark.asyncio
async def test_retention_rejects_a_stale_binding_snapshot(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        monkeypatch.setattr(memory.retriever.claim_index, "search", AsyncMock(return_value=[]))
        await memory.ingest_source(SourceInput("I am preparing a plan.", "s", source_type="meeting_transcript",
            segments=(SourceSegment("s", 0, "I am preparing a plan.", speaker="Sam"),)))
        async def respond(llm, payload):
            person = memory.artifacts.create_entity("person", "User-selected Sam")
            pid = payload["participants"][0]["id"]
            identity_context.save_binding(memory.artifacts, memory.artifacts.list_sources()[0].source_id,
                                          pid, person.entity_id, "explicit-review", origin="user")
            return retained(payload)
        monkeypatch.setattr(memory_contract, "retain", respond)
        result = await memory.consolidate()
        assert any("Memory changed" in f["reason"] for f in result.report.failures)
        assert not memory.artifacts.list_claims()
        assert memory.artifacts.list_episodes()[0].extraction_status == "failed"
        assert identity_context.participants(memory.artifacts, memory.artifacts.list_sources()[0])[0]["binding_origin"] == "user"


@pytest.mark.asyncio
async def test_accepted_correction_updates_wording_refs_and_resumable_views(tmp_path, monkeypatch):
    from mycelium.artifacts import EntityResolutionDecision
    from tests.test_claim_lifecycle import NOW
    artifacts, wiki, service, claim, person, fact = views_fixture(tmp_path)
    claim.text = "Rowan is preparing the checklist."
    from tests.extraction_support import stored_time
    claim.facets = stored_time(claim.provenance[0].segment_ids[0], "next week",
        {"kind": "unresolved", "reason": "No source date"}, None)
    artifacts.save_claim(claim)
    target = artifacts.create_entity("person", "Rowan Ellis")
    decision = EntityResolutionDecision("identity", "entity_creation", person.entity_id, "person", person.title,
        ["source"], [claim.claim_id], claim.provenance[0].segment_ids, .8, "Model choice", "accepted", "run", NOW)
    artifacts.save_entity_resolution_decision(decision)
    source_before = artifacts.get_source("source")
    original = deepcopy(claim)
    corrected = "Rowan Ellis is preparing the checklist."
    reviewed = IdentityReviewService(artifacts).review("identity", "approve", entity_id=target.entity_id,
                                                       claim_texts={claim.claim_id: corrected})
    assert artifacts.get_entity(target.entity_id).title == "Rowan Ellis"
    assert artifacts.get_claim(claim.claim_id).status == "superseded"
    replacement, = [artifacts.get_claim(cid) for cid in reviewed.supporting_claim_ids]
    assert replacement.text == corrected
    assert replacement.facets == original.facets
    assert any(p.segment_ids == original.provenance[0].segment_ids for p in replacement.provenance)
    assert artifacts.get_source("source") == source_before
    assert artifacts.entities_for_claims({replacement.claim_id}) == {"you", target.entity_id}
    assert artifacts.db.ids("identity-review-history")
    assert service.views.llm.call_structured.await_count == 0

    async def present(llm, payload):
        assert fact.fact_id in {f["id"] for f in payload["existing_items"]}
        assert person.entity_id in payload["affected_subject_ids"]
        return {"items": [{"owner_id": target.entity_id, "heading": "Preparation", "text": corrected,
            "memory_ids": [replacement.claim_id], "linked_subject_ids": [], "state": "current"}]}
    monkeypatch.setattr(memory_contract, "present", present)
    # A resumed Build need only supply the pending replacement; its exact link
    # finds old view items even when embedding retrieval returns no context.
    await service.views.refresh({replacement.claim_id}, context_ids=[], run_id="retry")
    assert corrected in wiki.get(target.slug).content
    assert all(fact.member_claim_ids != [original.claim_id] for fact in artifacts.list_consolidated_facts())

    from mycelium.claim_index import LanceClaimIndex
    from tests.test_claim_index import FakeEmbedder
    index = LanceClaimIndex(tmp_path / "claims.lance", artifacts, FakeEmbedder())
    hits = await index.search("checklist")
    assert any(h.claim_id == replacement.claim_id and h.claim_text == corrected for h in hits)
    # Search preserves history, but must label the replaced interpretation.
    assert all(h.memory_tier == "superseded" for h in hits if h.claim_id == original.claim_id)


def test_invalid_identity_wording_rolls_back_entire_review(tmp_path):
    from mycelium.artifacts import EntityResolutionDecision
    from tests.test_claim_lifecycle import NOW
    artifacts, wiki, service, claim, person, fact = views_fixture(tmp_path)
    decision = EntityResolutionDecision("identity", "entity_creation", person.entity_id, "person", person.title,
        ["source"], [claim.claim_id], [], .8, "Model choice", "accepted", "run", NOW)
    artifacts.save_entity_resolution_decision(decision)
    before = [asdict(r) for r in artifacts.list_entity_references()]
    with pytest.raises(ValueError, match="reviewed identity"):
        IdentityReviewService(artifacts).review("identity", "approve", entity_id="you", entity_type="person",
                                                claim_texts={"unrelated": "Changed"})
    assert artifacts.get_entity_resolution_decision("identity") == decision
    assert [asdict(r) for r in artifacts.list_entity_references()] == before
    assert artifacts.db.ids("identity-review-history") == []
