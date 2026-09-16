import pytest
from pydantic import ValidationError

from mycelium.subject_discovery import subject_discovery_model
from mycelium.subject_identity import subject_identity_model
from mycelium.subject_review_bindings import subject_review_model


def discovered(kind="person", evidence=None):
    return {
        "entity_type": kind,
        "title": "Subject",
        "description": "Grounded subject",
        "aliases": [],
        "supporting_evidence": evidence or ["C001"],
    }


def test_discovery_cannot_change_reviewed_type_or_bind_participant_to_project():
    schema = subject_discovery_model(["C001"], {"P001": "user"}, {"R001": "project"})
    schema.model_validate(
        {"subjects": [discovered(evidence=["P001"]), discovered("project", ["R001"])]}
    )
    for subjects in [
        [discovered(evidence=["P001", "R001"])],
        [discovered("project", ["P001", "R001"])],
        [discovered(evidence=["P001"])],
        [discovered(evidence=["P001", "P001"]), discovered("project", ["R001"])],
        [
            discovered(evidence=["P001"]),
            discovered(evidence=["P001"]),
            discovered("project", ["R001"]),
        ],
    ]:
        with pytest.raises(ValidationError):
            schema.model_validate({"subjects": subjects})


def test_discovery_requires_exact_grounding_ids():
    schema = subject_discovery_model(["C001"], {}, {})
    with pytest.raises(ValidationError):
        schema.model_validate({"subjects": [discovered(evidence=["invented"])]})
    assert schema.model_validate({"subjects": []}).subjects == []
    with pytest.raises(ValueError, match="source evidence"):
        subject_discovery_model([], {}, {})


def test_identity_result_cannot_change_subject_type_or_select_outside_candidate_snapshot():
    schema = subject_identity_model(["entity-1", "entity-2"])
    valid = {
        "resolution": "existing",
        "entity_id": "entity-1",
        "title": None,
        "aliases": [],
        "reason": "Identity-defining evidence",
    }
    schema.model_validate({"decision": valid})
    for change in [
        {"entity_id": "invented"},
        {"entity_type": "project"},
        {"supporting_evidence": []},
    ]:
        with pytest.raises(ValidationError):
            schema.model_validate({"decision": {**valid, **change}})
    for ids in [["entity-1", "entity-1"], ["invented"]]:
        with pytest.raises(ValidationError):
            schema.model_validate(
                {
                    "decision": {
                        "resolution": "review_required",
                        "candidate_entity_ids": ids,
                        "reason": "Unresolved",
                    }
                }
            )


def test_empty_registry_allows_new_or_unnamed_review_without_invented_candidates():
    schema = subject_identity_model([])
    for decision in [
        {"resolution": "new", "reason": "Distinct subject"},
        {
            "resolution": "review_required",
            "reason": "Unknown person",
            "candidate_entity_ids": [],
        },
    ]:
        schema.model_validate({"decision": decision})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "decision": {
                    "resolution": "existing",
                    "entity_id": "invented",
                    "reason": "Guess",
                    "title": None,
                    "aliases": [],
                }
            }
        )


def test_review_assignments_preserve_exact_distinct_identities():
    schema = subject_review_model(
        {"S001": {}, "S002": {}},
        {"R001": {"entity_id": "entity-1"}, "R002": {"entity_id": "entity-2"}},
    )
    assignments = {
        "R001": {"subject_alias": "S001", "reason": "Reviewed first subject"},
        "R002": {"subject_alias": "S002", "reason": "Reviewed other subject"},
    }
    schema.model_validate({"assignments": assignments})
    for value in ["S001", "invented"]:
        with pytest.raises(ValidationError):
            schema.model_validate(
                {
                    "assignments": {
                        **assignments,
                        "R002": {
                            "subject_alias": value,
                            "reason": "Invalid assignment",
                        },
                    }
                }
            )
    with pytest.raises(ValidationError):
        schema.model_validate({"assignments": {"R001": assignments["R001"]}})


def test_missing_subject_does_not_require_guessing_a_review_binding():
    schema = subject_review_model({}, {"R001": {"entity_id": "entity-1"}})
    schema.model_validate(
        {
            "assignments": {
                "R001": {"subject_alias": "unresolved", "reason": "Subject is absent"}
            }
        }
    )
