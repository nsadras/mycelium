import pytest
from pydantic import ValidationError

from mycelium.subject_discovery import subject_discovery_model
from mycelium.subject_identity import subject_identity_model
from mycelium.subject_review_bindings import subject_review_model


def discovered(kind="person", evidence=None, subject_id="S001"):
    return {
        "subject_id": subject_id,
        "entity_type": kind,
        "title": "Subject",
        "description": "Grounded subject",
        "alternate_names": [],
        "supporting_evidence": evidence if evidence is not None else ["C001"],
    }


def test_discovery_cannot_change_reviewed_type_or_bind_participant_to_project():
    from copy import deepcopy

    schema = subject_discovery_model(["C001"], {"P001": "user"}, {"R001": "project"})
    valid = {
        "subjects": [discovered(evidence=[]), discovered("project", ["R001"], "S002")],
        "participant_subjects": {"P001": {"subject_id": "S001"}},
    }
    schema.model_validate(valid)
    invalid = []
    for binding in [
        {},
        {"P001": {"subject_id": "S002"}},
        {"P001": {"subject_id": "S003"}},
        {"P001": {"subject_id": "S001"}, "P002": {"subject_id": "S001"}},
    ]:
        invalid.append({**valid, "participant_subjects": binding})
    for change in [
        {"supporting_evidence": ["P001"]},
        {"supporting_evidence": ["R001"]},
        {"supporting_evidence": ["C001", "C001"]},
        {"subject_id": "S002"},
    ]:
        item = deepcopy(valid)
        item["subjects"][0].update(change)
        invalid.append(item)
    item = deepcopy(valid)
    item["subjects"][1]["supporting_evidence"] = []
    invalid.append(item)
    for item in invalid:
        with pytest.raises(ValidationError):
            schema.model_validate(item)


def test_multiple_participant_occurrences_can_bind_one_grounded_person():
    schema = subject_discovery_model(["C001"], {"P001": None, "P002": None}, {})
    result = schema.model_validate(
        {
            "subjects": [discovered(evidence=[])],
            "participant_subjects": {
                "P001": {"subject_id": "S001"},
                "P002": {"subject_id": "S001"},
            },
        }
    )
    assert result.subjects[0].supporting_evidence == []


def test_discovery_requires_exact_grounding_ids():
    schema = subject_discovery_model(["C001"], {}, {})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {
                "subjects": [discovered(evidence=["invented"])],
                "participant_subjects": {},
            }
        )
    assert (
        schema.model_validate({"subjects": [], "participant_subjects": {}}).subjects
        == []
    )
    with pytest.raises(ValueError, match="source evidence"):
        subject_discovery_model([], {}, {})


def test_identity_result_cannot_change_subject_type_or_select_outside_candidate_snapshot():
    schema = subject_identity_model(
        ["entity-1", "entity-2"], '{"claims": {}, "sources": {}}'
    )
    valid = {
        "resolution": "existing",
        "entity_id": "entity-1",
        "preferred_name_update": None,
        "aliases": [],
        "reason": "Identity-defining evidence",
    }
    schema.model_validate({"decision": valid})
    for change in [
        {"preferred_name_update": ""},
        {"preferred_name_update": "Unsupported name"},
        {"title": ""},
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
                        "title_basis": "description",
                        "title": "Unknown person",
                        "aliases": [],
                    }
                }
            )


def test_empty_registry_allows_new_or_unnamed_review_without_invented_candidates():
    schema = subject_identity_model([], '{"claims": {}, "sources": {}}')
    for decision in [
        {
            "resolution": "new",
            "reason": "Distinct subject",
            "title_basis": "description",
            "title": "Subject",
            "aliases": [],
        },
        {
            "resolution": "review_required",
            "reason": "Unknown person",
            "candidate_entity_ids": [],
            "title_basis": "description",
            "title": "Unidentified person",
            "aliases": [],
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


def test_preferred_name_updates_require_exact_cited_spelling():
    import json

    evidence = {
        "claims": {"C1": {"citations": [{"source_id": "s", "segment_id": "one"}]}},
        "sources": {
            "s": {
                "segments": {
                    "one": {"text": "I renamed Cedar to Larch."},
                    "uncited": {"text": "An unrelated Spruce project."},
                }
            }
        },
    }
    schema = subject_identity_model(["e1"], json.dumps(evidence))
    decision = dict(
        resolution="existing",
        entity_id="e1",
        aliases=[],
        reason="Explicit name update",
        preferred_name_update="Larch",
    )
    assert (
        schema.model_validate({"decision": decision}).decision.preferred_name_update
        == "Larch"
    )
    for name in ("Lorch", "Spruce", "larch"):
        with pytest.raises(ValidationError, match="copied exactly"):
            schema.model_validate(
                {"decision": {**decision, "preferred_name_update": name}}
            )
    assert schema.model_validate(
        {"decision": {**decision, "preferred_name_update": None}}
    )


@pytest.mark.parametrize("resolution", ["new", "review_required"])
def test_declared_source_titles_require_cited_spelling_but_descriptions_can_vary(
    resolution,
):
    import json

    evidence = {
        "claims": {"c": {"citations": [{"source_id": "s", "segment_id": "one"}]}},
        "sources": {
            "s": {
                "segments": {
                    "one": {"text": "The new project is named Larch."},
                    "uncited": {"text": "Spruce is another project."},
                }
            }
        },
    }
    schema = subject_identity_model([], json.dumps(evidence))
    decision = dict(
        resolution=resolution,
        reason="Cited name",
        aliases=[],
        title_basis="source_name",
        title="Larch",
    )
    if resolution == "review_required":
        decision["candidate_entity_ids"] = []
    assert schema.model_validate({"decision": decision}).decision.title == "Larch"
    for title in ("Lorch", "Spruce", "larch"):
        with pytest.raises(ValidationError, match="copied exactly"):
            schema.model_validate({"decision": {**decision, "title": title}})
    assert schema.model_validate(
        {
            "decision": {
                **decision,
                "title_basis": "description",
                "title": "An unnamed effort",
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
