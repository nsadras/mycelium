from dataclasses import replace

from mycelium import Mycelium
from mycelium.artifacts import ClaimEntityReference
from mycelium.memory_workspace import merge_memory_evidence
from mycelium.retrieval_context import RetrievedContextBuilder
from mycelium.evidence_rendering import render_memory_evidence
from mycelium.store import WikiStore
from tests.test_audit_remediation import seed


def reference(claim, entity, role="subject", identifier="ref"):
    return ClaimEntityReference(identifier, claim.claim_id, role, "They", entity.entity_id,
        1.0, "Explicit attribution", "extraction", "test", "active", "2030-01-01")


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
