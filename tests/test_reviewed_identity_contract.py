import pytest
from pydantic import ValidationError

from mycelium.reviewed_identity_contract import expand_review_evidence, reviewed_identity_model


def fixture():
    bindings = {"R001": {"entity_id": "person-rin", "claim_alias": "C001", "surface": "Rin"}}
    schema = reviewed_identity_model(["C001"], {}, {"person-rin": "person"}, bindings)
    plan = {"subjects": [
        {"resolution": "existing", "entity_id": "person-rin", "title": None,
         "aliases": [], "supporting_evidence": ["R001"], "reason": "User-reviewed person"},
        {"resolution": "new", "entity_type": "project", "title": "Orchard",
         "aliases": [], "supporting_evidence": ["C001"], "reason": "Distinct subject in the same claim"},
    ]}
    return bindings, schema, plan


def test_reviewed_occurrence_does_not_own_other_subjects_in_the_claim():
    bindings, schema, plan = fixture()
    valid = schema.model_validate(plan).model_dump()
    expanded = expand_review_evidence(valid, bindings)
    assert expanded["subjects"][0]["supporting_evidence"] == ["C001"]
    assert expanded["subjects"][1]["supporting_evidence"] == ["C001"]
    assert valid["subjects"][0]["supporting_evidence"] == ["R001"]


@pytest.mark.parametrize("change", ["omit", "reassign", "duplicate"])
def test_a_human_binding_cannot_be_omitted_reassigned_or_duplicated(change):
    _, schema, plan = fixture()
    if change in {"omit", "reassign"}:
        plan["subjects"][0]["supporting_evidence"] = ["C001"]
    if change in {"reassign", "duplicate"}:
        plan["subjects"][1]["supporting_evidence"].append("R001")
    with pytest.raises(ValidationError, match="human identity"):
        schema.model_validate(plan)


def test_two_confirmed_subjects_can_share_claim_evidence():
    bindings, _, plan = fixture()
    bindings["R002"] = {"entity_id": "project-orchard", "claim_alias": "C001", "surface": "Orchard"}
    schema = reviewed_identity_model(["C001"], {}, {"person-rin": "person", "project-orchard": "project"}, bindings)
    plan["subjects"][1] = {"resolution": "existing", "entity_id": "project-orchard", "title": None,
        "aliases": [], "supporting_evidence": ["R002"], "reason": "Other reviewed identity"}
    assert len(schema.model_validate(plan).subjects) == 2


def test_reviewed_user_and_other_subjects_keep_separate_bindings():
    bindings = {"R001": {"entity_id": "you", "claim_alias": "C001", "surface": None}}
    schema = reviewed_identity_model(["C001"], {"P001": "user"}, {"you": "you"}, bindings)
    plan = {"user": {"aliases": [], "supporting_evidence": ["P001", "R001"], "reason": "Declared user"},
        "subjects": [{"resolution": "new", "entity_type": "project", "title": "Orchard",
            "aliases": [], "supporting_evidence": ["C001"], "reason": "Distinct project"}]}
    schema.model_validate(plan)
    assert expand_review_evidence(plan, bindings)["user"]["supporting_evidence"] == ["P001", "C001"]


def test_reviewing_one_identity_does_not_erase_another_review_in_the_same_claim(tmp_path):
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
            decision_id=f"review-{entity.entity_id}", decision_type="entity_creation", entity_id=entity.entity_id,
            proposed_entity_type=entity.entity_type, proposed_title=entity.title, source_ids=["source-claim"],
            supporting_claim_ids=["claim"], supporting_segment_ids=["source-claim#seg-0001"], confidence=.9,
            reason="Proposed identity", review_state="review_required", dream_run_id="test", created_at="2031-01-01",
            proposed_scope="independent", proposed_page_state="provisional",
        )
        artifacts.save_entity_resolution_decision(decision)
        service.review(decision.decision_id, "approve")
        decisions.append(decision.decision_id)
    references = artifacts.list_entity_references(claim_id="claim", status="active")
    assert {ref.entity_id for ref in references} == {person.entity_id, project.entity_id}
    assert {ref.identity_decision_id for ref in references} == set(decisions)
    # Reopening and deciding the same review supersedes only that occurrence.
    revised = artifacts.get_entity_resolution_decision(decisions[0])
    revised.review_state = "review_required"
    artifacts.save_entity_resolution_decision(revised)
    service.review(revised.decision_id, "approve")
    active = artifacts.list_entity_references(claim_id="claim", status="active")
    assert len(active) == 2
    assert {ref.entity_id for ref in active} == {person.entity_id, project.entity_id}
    assert len(artifacts.list_entity_references(claim_id="claim", status="superseded")) == 1


def test_user_can_confirm_a_person_occurrence_as_you_without_renaming_you(tmp_path):
    from dataclasses import asdict
    from mycelium.artifacts import ArtifactStore, EntityResolutionDecision
    from mycelium.organization import IdentityReviewService
    from tests.memory_helpers import claim, place
    artifacts = ArtifactStore(tmp_path / "artifacts")
    you = artifacts.create_entity("you", "You")
    place(artifacts, claim("claim", "The speaker prefers concise updates.", "2031-01-01"))
    decision = EntityResolutionDecision("review", "entity_creation", None, "person", "Unidentified speaker",
        ["source-claim"], ["claim"], ["source-claim#seg-0001"], .8, "Unresolved speaker", "review_required",
        "test", "2031-01-01", proposed_scope="independent", proposed_page_state="provisional", candidate_entity_ids=["you"])
    artifacts.save_entity_resolution_decision(decision)
    result = IdentityReviewService(artifacts).review("review", "approve", entity_id="you")
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
