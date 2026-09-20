"""Structural regression checks for the production evidence/view boundary."""

import pytest

from mycelium import memory_contract as contract
from mycelium import Mycelium
from mycelium.operations import SourceInput


@pytest.mark.asyncio
async def test_reviewed_speaker_reaches_retention_and_shared_project_views(tmp_path, monkeypatch):
    """Check the handoff and citations; native probes assess the model's attribution."""
    from engram.memory_adapter import encode_meeting_into_memory
    from engram.store import EngramStore

    store = EngramStore(tmp_path / "engram.sqlite")
    meeting = store.create_meeting("Workshop planning")
    segment = store.add_segment(meeting.id, start_seconds=0, end_seconds=8,
        speaker="SPEAKER_00", text="I built Bench Ledger to track workshop tool loans.")
    store.save_speaker_names(meeting.id, {"SPEAKER_00": "Rowan"})
    calls = {"retain": 0, "present": 0}

    async def no_search(*args, **kwargs):
        return []

    async def retain(llm, payload):
        calls["retain"] += 1
        assert payload["source_type"] == "meeting_transcript"
        assert payload["participants"] == ["Rowan"]
        assert [(s["speaker"], s["text"]) for s in payload["segments"]] == [("Rowan", segment.text)]
        assert {s["id"] for s in payload["existing_subjects"]} == {"you"}
        person, project = payload["new_subject_ids"][:2]
        return {"subjects": [
            {"id": person, "title": "Rowan", "entity_type": "person", "review_required": False},
            {"id": project, "title": "Bench Ledger", "entity_type": "project", "review_required": False}],
            "memories": [{"id": "m", "text": "Rowan built Bench Ledger to track workshop tool loans.",
                "segment_ids": [payload["segments"][0]["id"]], "subject_ids": [person, project]}],
            "changes": []}

    async def present(llm, payload):
        calls["present"] += 1
        subjects = {s["title"]: s["id"] for s in payload["subjects"]}
        person, project = subjects["Rowan"], subjects["Bench Ledger"]
        memory = payload["memories"][0]
        assert set(memory["subject_ids"]) == {person, project}
        assert set(payload["affected_subject_ids"]) == {person, project}
        return {"items": [
            {"owner_id": person, "heading": "Projects", "text": "Rowan built Bench Ledger.",
             "memory_ids": [memory["id"]], "linked_subject_ids": [project], "state": "current"},
            {"owner_id": project, "heading": "Purpose", "text": "Tracks workshop tool loans.",
             "memory_ids": [memory["id"]], "linked_subject_ids": [], "state": "current"}]}

    monkeypatch.setattr(contract, "retain", retain)
    monkeypatch.setattr(contract, "present", present)
    with Mycelium(tmp_path / "memory") as memory:
        monkeypatch.setattr(memory.retriever.claim_index, "search", no_search)
        entry = await encode_meeting_into_memory(memory, store, meeting.id)
        assert memory.artifacts.list_claims() == []
        assert not (await memory.pipeline.consolidate()).report.failures
        claim, = memory.artifacts.list_claims()
        person = next(e for e in memory.artifacts.list_entities() if e.title == "Rowan")
        project = next(e for e in memory.artifacts.list_entities() if e.title == "Bench Ledger")
        assert memory.artifacts.entities_for_claims({claim.claim_id}) == {person.entity_id, project.entity_id}
        assert claim.provenance[0].speaker == "Rowan"
        pages = {p.entity_id: p for p in memory.wiki.list_all()}
        for eid in (person.entity_id, project.entity_id):
            page = pages[eid]
            assert page.source_log_entries == [entry.entry_id]
            assert "Rowan" in page.content
            for section in page.sections:
                for item in section["items"]:
                    assert item["sources"][0]["segment_ids"] == claim.provenance[0].segment_ids
        assert [edge.target for edge in pages[person.entity_id].related] == [project.slug]
        assert [edge.target for edge in pages[project.entity_id].related] == [person.slug]
        assert calls == {"retain": 1, "present": 1}


@pytest.mark.asyncio
async def test_compact_capture_publication_failure_and_retry(tmp_path, monkeypatch):
    calls = {"retain": 0, "present": 0}

    async def no_search(*args, **kwargs):
        return []

    async def retain(llm, payload):
        calls["retain"] += 1
        sid = payload["existing_subjects"][0]["id"] if payload["existing_subjects"] else payload["new_subject_ids"][0]
        return {"subjects": [{"id": sid, "title": "Rowan",
                             "entity_type": "person", "review_required": False}],
                "memories": [{"id": "m", "text": payload["segments"][0]["text"],
                              "subject_ids": [sid],
                              "segment_ids": [payload["segments"][0]["id"]]}], "changes": []}

    async def present(llm, payload):
        calls["present"] += 1
        old_ids = {cid for item in payload["existing_items"] for cid in item["memory_ids"]}
        fresh = next(m for m in payload["memories"] if m["id"] not in old_ids)
        return {"items": [{"owner_id": payload["affected_subject_ids"][0], "heading": "Museum visits",
                "text": fresh["text"], "memory_ids": [fresh["id"]],
                "linked_subject_ids": [], "state": "history"}]}

    monkeypatch.setattr(contract, "retain", retain)
    monkeypatch.setattr(contract, "present", present)
    with Mycelium(tmp_path, memory_profile="none") as memory:
        pipeline = memory.pipeline
        monkeypatch.setattr(memory.retriever.claim_index, "search", no_search)
        await pipeline.ingest_source(SourceInput("Rowan visited a museum.", "s", occurred_at="2032-01-02"))
        assert memory.artifacts.list_claims() == []
        regenerate = memory.consolidator.materializer.regenerate

        def fail_after_staging(ids):
            regenerate(ids)
            raise OSError("injected publication preparation failure")

        monkeypatch.setattr(memory.consolidator.materializer, "regenerate", fail_after_staging)
        failed = await pipeline.consolidate()
        assert failed.report.failures
        assert len(memory.artifacts.list_claims()) == 1
        assert memory.wiki.list_all() == []
        assert memory.artifacts.list_consolidated_facts() == []
        assert memory.artifacts.list_placements() == []
        monkeypatch.setattr(memory.consolidator.materializer, "regenerate", regenerate)
        successful = await pipeline.consolidate()
        assert not successful.report.failures
        assert calls == {"retain": 1, "present": 2}
        assert len(memory.artifacts.list_claims()) == 1
        assert len(memory.artifacts.list_consolidated_facts()) == 1
        assert memory.wiki.list_all()[0].sections[0]["title"] == "Museum visits"
        await pipeline.consolidate()
        assert calls == {"retain": 1, "present": 2}
        assert memory.artifacts.list_episodes()[0].extraction_status == "complete"

        old_claim = memory.artifacts.list_claims()[0]
        old_fact = memory.artifacts.list_consolidated_facts()[0]
        old_fact.manual_text = True
        memory.artifacts.save_consolidated_fact(old_fact)
        prior_page = memory.wiki.list_all()[0]

        async def existing_search(*args, **kwargs):
            from types import SimpleNamespace
            return [SimpleNamespace(claim_id=old_claim.claim_id)]

        monkeypatch.setattr(memory.retriever.claim_index, "search", existing_search)
        await pipeline.ingest_source(SourceInput("Rowan visited a gallery.", "s2", occurred_at="2032-01-03"))
        monkeypatch.setattr(memory.consolidator.materializer, "regenerate", fail_after_staging)
        assert (await pipeline.consolidate()).report.failures
        assert memory.wiki.list_all()[0] == prior_page
        assert memory.artifacts.list_consolidated_facts() == [old_fact]
        monkeypatch.setattr(memory.consolidator.materializer, "regenerate", regenerate)
        assert not (await pipeline.consolidate()).report.failures
        assert calls == {"retain": 2, "present": 4}
        assert memory.artifacts.get_consolidated_fact(old_fact.fact_id) == old_fact
        assert len(memory.artifacts.list_claims()) == 2
        assert len(memory.artifacts.list_consolidated_facts()) == 2


def test_compact_review_and_citation_boundaries():
    payload = {"subjects": [{"id": "person"}], "affected_subject_ids": ["person"],
               "memories": [{"id": "c1"}], "protected_memory_ids": [], "page_exclusions": []}
    item = {"owner_id": "person", "heading": "Plans", "text": "A source-backed plan.",
            "memory_ids": ["c1"], "linked_subject_ids": [], "state": "current"}
    contract.presentation_model(payload).model_validate({"items": [item]})
    for changed in ({"page_exclusions": [{"memory_id": "c1", "subject_id": "person"}]},
                    {"memories": []}):
        with pytest.raises(ValueError):
            contract.presentation_model({**payload, **changed}).model_validate({"items": [item]})


def test_compact_identity_uses_declared_ids_only():
    payload = {"segments": [{"id": "s"}], "existing_subjects": [{"id": "person"}],
               "new_subject_ids": ["new"], "prior_memories": []}
    row = {"id": "person", "title": "Rowan", "entity_type": "person", "review_required": False}
    model = contract.retention_model(payload)
    model.model_validate({"subjects": [row], "memories": [], "changes": []})
    for change in ({"id": "invented"}, {"review_required": True}):
        with pytest.raises(ValueError):
            model.model_validate({"subjects": [{**row, **change}], "memories": [], "changes": []})


def test_generation_schema_scopes_citations_before_decoding():
    payload = {"segments": [{"id": "source-a#seg-0041"}, {"id": "source-a#seg-0042"}],
               "context_segments": [{"id": "source-b#seg-0001"}],
               "existing_subjects": [], "new_subject_ids": ["person"], "prior_memories": []}
    model = contract.retention_model(payload)
    schema = model.model_json_schema()
    assert schema["$defs"]["MemorySelection"]["properties"]["segment_ids"]["items"]["enum"] == [
        "source-a#seg-0041", "source-a#seg-0042", "source-b#seg-0001"]
    value = {"subjects": [{"id": "person", "title": "Rowan", "entity_type": "person", "review_required": False}],
             "memories": [{"id": "m", "text": "A supported statement.", "subject_ids": ["person"],
                           "segment_ids": ["source-a#seg-0041", "source-b#seg-0001"]}], "changes": []}
    model.model_validate(value)
    value["memories"][0]["segment_ids"] = ["source-a#seg-00041"]
    with pytest.raises(ValueError):
        model.model_validate(value)
    view_model = contract.presentation_model({"subjects": [{"id": "person"}],
        "affected_subject_ids": ["person"], "memories": [{"id": "m"}]})
    view_schema = view_model.model_json_schema()
    assert view_schema["$defs"]["ViewSelection"]["properties"]["memory_ids"]["items"]["const"] == "m"
    item = {"owner_id": "person", "heading": "Context", "text": "A supported statement.",
            "memory_ids": ["m"], "linked_subject_ids": [], "state": "current"}
    view_model.model_validate({"items": [item]})
    item["memory_ids"] = ["invented"]
    with pytest.raises(ValueError):
        view_model.model_validate({"items": [item]})


@pytest.mark.asyncio
async def test_shared_evidence_keeps_distinct_items_and_owners(tmp_path, monkeypatch):
    async def no_search(*args, **kwargs):
        return []

    async def retain(llm, payload):
        a, b = payload["new_subject_ids"][:2]
        return {"subjects": [{"id": sid, "title": title, "entity_type": "person", "review_required": False}
                             for sid, title in [(a, "Rowan"), (b, "Sasha")]],
                "memories": [{"id": "m", "text": "Rowan keeps the receipts; Sasha brings the tools.",
                              "segment_ids": [payload["segments"][0]["id"]], "subject_ids": [a, b]}],
                "changes": []}

    async def present(llm, payload):
        a, b = payload["affected_subject_ids"]
        cid = payload["memories"][0]["id"]
        items = [{"owner_id": sid, "heading": heading, "text": text, "memory_ids": [cid],
                  "linked_subject_ids": [], "state": "current"}
                 for sid, heading, text in [(a, "Records", "Keeps the receipts."),
                                           (b, "Equipment", "Brings the tools.")]]
        return contract.presentation_model(payload).model_validate({"items": items}).model_dump()

    monkeypatch.setattr(contract, "retain", retain)
    monkeypatch.setattr(contract, "present", present)
    with Mycelium(tmp_path, memory_profile="none") as memory:
        pipeline = memory.pipeline
        monkeypatch.setattr(memory.retriever.claim_index, "search", no_search)
        await pipeline.ingest_source(SourceInput("Rowan keeps the receipts; Sasha brings the tools.", "s"))
        assert not (await pipeline.consolidate()).report.failures
        claim = memory.artifacts.list_claims()[0]
        facts = sorted(memory.artifacts.list_consolidated_facts(), key=lambda f: f.owner_entity_id)
        assert len(facts) == 2
        assert all(f.member_claim_ids == [claim.claim_id] for f in facts)
        assert memory.artifacts.list_placements() == []
        pages = {p.entity_id: p for p in memory.wiki.list_all()}
        for fact in facts:
            page = pages[fact.owner_entity_id]
            item = page.sections[0]["items"][0]
            assert item["text"] == fact.text
            assert item["canonical_owner_entity_ids"] == [fact.owner_entity_id]
            assert item["sources"][0]["segment_ids"] == claim.provenance[0].segment_ids
            assert page.source_log_entries == [claim.provenance[0].raw_log_entry_id]

        # Refreshing A with the same evidence cannot erase B's distinct item.
        a, b = facts
        b.manual_text = True
        memory.artifacts.save_consolidated_fact(b)
        payload = memory.consolidator.views.input({claim.claim_id}, [], {a.owner_entity_id})
        view = {"items": [{"owner_id": a.owner_entity_id, "heading": "Records", "text": "Stores receipts.",
                            "memory_ids": [claim.claim_id], "linked_subject_ids": [], "state": "current"}]}
        contract.presentation_model(payload).model_validate(view)
        memory.consolidator.views.persist(payload, view, {claim.claim_id}, "refresh")
        assert memory.artifacts.get_consolidated_fact(b.fact_id) == b
        assert len(memory.artifacts.list_consolidated_facts()) == 2
        assert len(memory.artifacts.list_claims()) == 1

        # All presentations disappear when their canonical support is inactive.
        # This checks the renderer, not the application's retraction API.
        claim.status = "retracted"
        memory.artifacts.save_claim(claim)
        memory.consolidator.materializer.regenerate({a.owner_entity_id})
        assert memory.wiki.list_all() == []
