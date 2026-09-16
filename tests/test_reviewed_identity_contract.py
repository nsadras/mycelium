import pytest

from mycelium.reviewed_identity_contract import expand_review_evidence


def test_reviewing_one_identity_does_not_erase_another_review_in_the_same_claim(
    tmp_path,
):
    from mycelium.artifacts import ArtifactStore, EntityResolutionDecision
    from mycelium.organization import IdentityReviewService
    from tests.memory_helpers import claim, place

    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.create_entity("you", "You")
    person = artifacts.create_entity("person", "Rin")
    project = artifacts.create_entity("project", "Orchard")
    place(artifacts, claim("claim", "Rin leads Orchard.", "2031-01-01"))
    service = IdentityReviewService(artifacts)
    decisions = []
    for entity in (person, project):
        decision = EntityResolutionDecision(
            decision_id=f"review-{entity.entity_id}",
            decision_type="entity_creation",
            entity_id=entity.entity_id,
            proposed_entity_type=entity.entity_type,
            proposed_title=entity.title,
            source_ids=["source-claim"],
            supporting_claim_ids=["claim"],
            supporting_segment_ids=["source-claim#seg-0001"],
            confidence=0.9,
            reason="Proposed identity",
            review_state="review_required",
            dream_run_id="test",
            created_at="2031-01-01",
            proposed_scope="independent",
            proposed_page_state="provisional",
        )
        artifacts.save_entity_resolution_decision(decision)
        service.review(decision.decision_id, "approve")
        decisions.append(decision.decision_id)
    references = artifacts.list_entity_references(claim_id="claim", status="active")
    assert {ref.entity_id for ref in references} == {
        person.entity_id,
        project.entity_id,
    }
    assert {ref.identity_decision_id for ref in references} == set(decisions)
    # Reopening and deciding the same review supersedes only that occurrence.
    revised = artifacts.get_entity_resolution_decision(decisions[0])
    revised.review_state = "review_required"
    artifacts.save_entity_resolution_decision(revised)
    service.review(revised.decision_id, "approve")
    active = artifacts.list_entity_references(claim_id="claim", status="active")
    assert len(active) == 2
    assert {ref.entity_id for ref in active} == {person.entity_id, project.entity_id}
    assert (
        len(artifacts.list_entity_references(claim_id="claim", status="superseded"))
        == 1
    )


def test_user_can_confirm_a_person_occurrence_as_you_without_renaming_you(tmp_path):
    from dataclasses import asdict
    from mycelium.artifacts import ArtifactStore, EntityResolutionDecision
    from mycelium.organization import IdentityReviewService
    from tests.memory_helpers import claim, place

    artifacts = ArtifactStore(tmp_path / "artifacts")
    you = artifacts.create_entity("you", "You")
    place(
        artifacts, claim("claim", "The speaker prefers concise updates.", "2031-01-01")
    )
    decision = EntityResolutionDecision(
        "review",
        "entity_creation",
        None,
        "person",
        "Unidentified speaker",
        ["source-claim"],
        ["claim"],
        ["source-claim#seg-0001"],
        0.8,
        "Unresolved speaker",
        "review_required",
        "test",
        "2031-01-01",
        proposed_scope="independent",
        proposed_page_state="provisional",
        candidate_entity_ids=["you"],
    )
    artifacts.save_entity_resolution_decision(decision)
    result = IdentityReviewService(artifacts).review(
        "review", "approve", entity_id="you"
    )
    assert result.entity_id == "you"
    assert asdict(artifacts.get_entity("you")) == asdict(you)
    reference = artifacts.list_entity_references(claim_id="claim", status="active")[0]
    assert reference.entity_id == "you" and reference.identity_decision_id == "review"


@pytest.mark.parametrize("version", [1, 2])
def test_old_schema_stores_are_rejected_without_migration(tmp_path, version):
    import sqlite3
    from mycelium.database import MemoryDatabase

    with sqlite3.connect(tmp_path / "memory.sqlite3") as connection:
        connection.execute(f"PRAGMA user_version={version}")
    with pytest.raises(ValueError, match="fresh store"):
        MemoryDatabase(tmp_path)
    with sqlite3.connect(tmp_path / "memory.sqlite3") as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version


def test_expansion_preserves_other_subjects_and_deduplicates_exact_claim_evidence():
    bindings = {
        "R1": {"entity_id": "you", "claim_alias": "C1"},
        "R2": {"entity_id": "person-rin", "claim_alias": "C1"},
    }
    plan = {
        "user": {"supporting_evidence": ["P1", "R1", "C1"]},
        "subjects": [
            {"entity_id": "person-rin", "supporting_evidence": ["R2"]},
            {"entity_id": "project-orchard", "supporting_evidence": ["C1"]},
        ],
    }
    expanded = expand_review_evidence(plan, bindings)
    assert expanded["user"]["supporting_evidence"] == ["P1", "C1"]
    assert [n["supporting_evidence"] for n in expanded["subjects"]] == [["C1"], ["C1"]]
    assert plan["user"]["supporting_evidence"] == ["P1", "R1", "C1"]
    assert plan["subjects"][0]["supporting_evidence"] == ["R2"]
