"""Mechanical checks for the isolated comparison, not evidence of model quality."""

import pytest

from benchmarks.experiments import compact_contract as contract
from benchmarks.experiments.compact_pipeline import CompactPipeline
from mycelium import Mycelium
from mycelium.operations import SourceInput


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
        pipeline = CompactPipeline(memory)
        monkeypatch.setattr(memory.retriever.claim_index, "search", no_search)
        await pipeline.ingest_source(SourceInput("Rowan visited a museum.", "s", occurred_at="2032-01-02"))
        assert memory.artifacts.list_claims() == []
        regenerate = pipeline.materializer.regenerate

        def fail_after_staging(ids):
            regenerate(ids)
            raise OSError("injected publication preparation failure")

        monkeypatch.setattr(pipeline.materializer, "regenerate", fail_after_staging)
        failed = await pipeline.consolidate()
        assert failed.report.failures
        assert len(memory.artifacts.list_claims()) == 1
        assert memory.wiki.list_all() == []
        assert memory.artifacts.list_consolidated_facts() == []
        assert memory.artifacts.list_placements() == []
        monkeypatch.setattr(pipeline.materializer, "regenerate", regenerate)
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
        pipeline.artifacts.save_consolidated_fact(old_fact)
        prior_page = memory.wiki.list_all()[0]

        async def existing_search(*args, **kwargs):
            from types import SimpleNamespace
            return [SimpleNamespace(claim_id=old_claim.claim_id)]

        monkeypatch.setattr(memory.retriever.claim_index, "search", existing_search)
        await pipeline.ingest_source(SourceInput("Rowan visited a gallery.", "s2", occurred_at="2032-01-03"))
        monkeypatch.setattr(pipeline.materializer, "regenerate", fail_after_staging)
        assert (await pipeline.consolidate()).report.failures
        assert memory.wiki.list_all()[0] == prior_page
        assert memory.artifacts.list_consolidated_facts() == [old_fact]
        monkeypatch.setattr(pipeline.materializer, "regenerate", regenerate)
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
    for changed in ({"protected_memory_ids": ["c1"]},
                    {"page_exclusions": [{"memory_id": "c1", "subject_id": "person"}]},
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
