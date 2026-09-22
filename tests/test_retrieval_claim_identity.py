from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium
from mycelium.artifacts import ClaimEntityReference, ConsolidatedFact
from mycelium.memory_workspace import merge_memory_evidence
from mycelium.retrieval_context import RetrievedContextBuilder, render_memory_evidence
from mycelium.store import WikiStore
from tests.test_audit_remediation import seed


def reference(claim, entity, role="subject", identifier="ref"):
    return ClaimEntityReference(identifier, claim.claim_id, role, "They", entity.entity_id,
        1.0, "Explicit attribution", "extraction", "test", "active", "2030-01-01")


def view(artifacts, entity, claims, identifier="view", text="Useful related context."):
    artifacts.save_consolidated_fact(ConsolidatedFact(identifier, text, [c.claim_id for c in claims],
        entity.entity_id, "Notes", "current", [], "manual", 1.0, "Supported view", "2030-01-01", "2030-01-01"))


def test_large_view_cannot_hide_small_canonical_claim(tmp_path):
    artifacts, claim, hit = seed(tmp_path)
    entity = artifacts.create_entity("person", "Nora")
    view(artifacts, entity, [claim], text="Long view context. " * 3000)
    builder = RetrievedContextBuilder(WikiStore(tmp_path / "wiki"), artifacts)
    result = builder.build([hit], budget_tokens=500, record_limit=5)
    assert [r.record_id for r in result.records] == [claim.claim_id]
    assert result.records[0].statement == claim.text
    assert result.sources and result.more_available


@pytest.mark.asyncio
async def test_shared_membership_respects_actual_search_record_limit(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, hit = seed(tmp_path)
        entity = artifacts.create_entity("person", "Nora")
        second = replace(claim, claim_id="c2", text="An independent detail.")
        artifacts.save_claim(second)
        for i in range(8):
            view(artifacts, entity, [claim, second], identifier=f"view-{i}")
        memory.retriever.claim_index.search = AsyncMock(return_value=[hit, hit, replace(hit, claim_id="c2")])
        result = await memory.retriever.search_evidence("Preferences", limit=3, budget_tokens=4000)
        assert [r.record_id for r in result.evidence.records[:2]] == ["c1", "c2"]
        assert len(result.evidence.records) == 3 and result.evidence.more_available
        assert result.evidence.records[2].canonical_claims[1].text == second.text
        assert len({r.record_id for r in result.evidence.records}) == 3


def test_deferred_claim_has_exact_identity_roles_without_requiring_a_page(tmp_path):
    artifacts, claim, hit = seed(tmp_path)
    artifacts.save_claim(replace(claim, text="They supplied the equipment.", about=[]))
    subject = artifacts.create_entity("person", "Rene", aliases=["R. Bell"], materialization_state="provisional")
    namesake = artifacts.create_entity("person", "Rene", aliases=["R. Hale"])
    artifacts.save_entity_reference(reference(claim, subject))
    artifacts.save_entity_reference(reference(claim, namesake, "context", "other-ref"))
    builder = RetrievedContextBuilder(WikiStore(tmp_path / "wiki"), artifacts)
    result = builder.build([hit], budget_tokens=1500)
    record = result.records[0]
    assert record.subject_entity_id == subject.entity_id
    assert {(s.entity_id, s.role) for s in record.subjects} == {(subject.entity_id, "subject"), (namesake.entity_id, "context")}
    assert "R. Bell" in render_memory_evidence(result) and "Identity (context)" in render_memory_evidence(result)
    assert not builder.page_references(result)


def test_reference_only_change_refreshes_identity_revision(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, hit = seed(tmp_path)
        first = artifacts.create_entity("person", "First")
        second = artifacts.create_entity("person", "Second")
        ref = reference(claim, first)
        artifacts.save_entity_reference(ref)
        initial = memory.retriever.context_builder.build([hit], budget_tokens=2000)
        artifacts.save_entity_reference(replace(ref, entity_id=second.entity_id))
        refreshed = memory.retriever.refresh_evidence(initial, budget_tokens=2000)
        assert refreshed.records[0].revision > initial.records[0].revision
        assert refreshed.records[0].subjects[0].entity_id == second.entity_id
        assert merge_memory_evidence(refreshed, initial).records == refreshed.records


@pytest.mark.asyncio
async def test_selected_view_reaches_answer_and_refresh_without_expanding_new_records(tmp_path):
    from mycelium.operations import RetrievalRequest
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, hit = seed(tmp_path)
        second = replace(claim, claim_id="c2", text="A related retained detail.")
        artifacts.save_claim(second)
        entity = artifacts.create_entity("person", "Nora")
        view(artifacts, entity, [claim, second])
        memory.retriever.claim_index.search = AsyncMock(return_value=[hit])
        memory.llm.call_structured = AsyncMock(return_value={
            "selected_ids": ["M002"], "supported_aspects": ["Related detail"], "remaining_gaps": []})
        result = await memory.retrieve_context(RetrievalRequest("The related detail?", 2000))
        assert [r.record_id for r in result.evidence.records] == ["view"]
        assert "A related retained detail." in result.rendered_context
        assert result.trace["selected_record_ids"] == ["view"]
        assert result.evidence.sources
        refreshed = memory.retriever.refresh_evidence(result.evidence, budget_tokens=2000)
        assert refreshed == result.evidence


def test_shared_assertions_are_rendered_once_without_dropping_unmatched_support(tmp_path):
    artifacts, claim, hit = seed(tmp_path)
    second = replace(claim, claim_id="c2", text="A unique related assertion.")
    artifacts.save_claim(second)
    entity = artifacts.create_entity("person", "Nora")
    for identifier in ("view-1", "view-2"):
        view(artifacts, entity, [claim, second], identifier=identifier)
    builder = RetrievedContextBuilder(WikiStore(tmp_path / "wiki"), artifacts)
    rendered = render_memory_evidence(builder._memory_evidence([hit]))
    assert rendered.count(claim.text) == 1
    assert rendered.count(second.text) == 1
    # A view shown on its own still carries both underlying assertions.
    evidence = builder._memory_evidence([hit])
    rendered = render_memory_evidence(replace(evidence, records=(evidence.records[-1],)))
    assert claim.text in rendered and second.text in rendered


def test_invalidated_view_keeps_corrected_interpretation_without_discovering_other_views(tmp_path):
    with Mycelium(tmp_path, memory_profile='none') as memory:
        artifacts, claim, hit = seed(tmp_path)
        entity = artifacts.create_entity('person', 'Nora')
        view(artifacts, entity, [claim])
        initial = memory.retriever.context_builder.build([hit], budget_tokens=3000)
        initial = replace(initial, records=tuple(r for r in initial.records if r.record_type == 'fact'))
        artifacts.save_claim(replace(claim, status='superseded'))
        current = replace(claim, claim_id='replacement', text='Nora now prefers coffee.')
        artifacts.save_claim(current)
        view(artifacts, entity, [current], identifier='unseen-view')
        refreshed = memory.retriever.refresh_evidence(initial, budget_tokens=3000)
        assert [(r.record_id, r.state) for r in refreshed.records] == [(claim.claim_id, 'superseded')]
        assert refreshed.sources[0] == replace(initial.sources[0], revision=refreshed.sources[0].revision)
