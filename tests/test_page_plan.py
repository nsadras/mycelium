import json

import pytest
from pydantic import ValidationError

from mycelium.ollama import OllamaClient
from mycelium.ontology import ENTITY_TYPES, routing_section_keys, section_keys
from mycelium.page_plan import page_plan_model
from mycelium.source_attribution import (
    attributed_pages,
    source_attribution_model,
    source_attribution_prompt,
)


def presentation(pages, owner):
    return {
        "primary_reason": "Source-backed main subject",
        "primary_subject": owner,
        "pages": pages,
        "uncertainty": None,
        "prominence": "briefing",
    }


def attribution(relation):
    return {
        "assertions": ["Cited source assertion"] if relation == "described" else [],
        "relation_to_claim": relation,
    }


def test_attribution_native_roundtrip_retains_unplaced_subject_and_reporting_context():
    schema = source_attribution_model(["C001"], ["you", "other"], {"you"})
    response = {
        "attributions": {
            "C001": {
                "you": attribution("reporting_only"),
                "other": attribution("described"),
            }
        }
    }
    client = OllamaClient(url="http://localhost:11434", model="unused")
    assert (
        schema.model_validate(
            client._parse_structured_response(json.dumps(response), schema)
        ).model_dump()
        == response
    )
    assert attributed_pages(response["attributions"], {"you"}, {}) == {"C001": []}
    assert attributed_pages(response["attributions"], {"you", "other"}, {}) == {
        "C001": ["other"]
    }
    assert attributed_pages(
        response["attributions"], {"you", "other"}, {"C001": {"other"}}
    ) == {"C001": []}
    assert response["attributions"]["C001"]["other"]["relation_to_claim"] == "described"


@pytest.mark.parametrize("kind", ENTITY_TYPES)
def test_native_schema_requires_one_allowed_section_for_each_attributed_page(kind):
    schema = page_plan_model({"C001": ["subject"]}, {"subject": kind})
    definitions = schema.model_json_schema()["$defs"]
    page_sections = next(
        d for d in definitions.values() if d.get("title") == "PageSections"
    )
    assert page_sections["required"] == ["subject"]
    assert set(page_sections["properties"]["subject"]["enum"]) == set(
        routing_section_keys(kind)
    )
    assert page_sections["additionalProperties"] is False
    for section in routing_section_keys(kind):
        response = {
            "decisions": {"C001": presentation({"subject": section}, "subject")}
        }
        assert schema.model_validate(response).model_dump() == response
    for section in [
        None,
        "invalid",
        ["overview", "profile"],
        *set(section_keys(kind)) - set(routing_section_keys(kind)),
    ]:
        with pytest.raises(ValidationError):
            schema.model_validate(
                {"decisions": {"C001": presentation({"subject": section}, "subject")}}
            )


def test_attribution_requires_every_exact_pair_and_limits_reporting_to_source_participants():
    schema = source_attribution_model(
        ["C001", "C002"], ["person", "project"], {"person"}
    )
    row = {"person": attribution("reporting_only"), "project": attribution("described")}
    schema.model_validate({"attributions": {"C001": row, "C002": row}})
    invalid = [
        {"C001": row},
        {"C001": {"person": attribution("described")}, "C002": row},
        {"C001": {**row, "extra": attribution("described")}, "C002": row},
        {"C001": {**row, "project": attribution("reporting_only")}, "C002": row},
        {"C001": {**row, "project": attribution("invented")}, "C002": row},
        {
            "C001": {
                **row,
                "project": {"relation_to_claim": "described", "reason": None},
            },
            "C002": row,
        },
        {
            "C001": {
                **row,
                "project": {
                    **attribution("unrelated"),
                    "assertions": ["Contradictory asserted content"],
                },
            },
            "C002": row,
        },
    ]
    for response in invalid:
        with pytest.raises(ValidationError):
            schema.model_validate({"attributions": response})


@pytest.mark.parametrize("relation", ["described", "reporting_only", "unrelated"])
def test_asserted_content_agrees_with_relation_and_is_bounded(relation):
    schema = source_attribution_model(["C001"], ["you"], {"you"})
    row = attribution(relation)
    schema.model_validate({"attributions": {"C001": {"you": row}}})
    assertions = [] if relation == "described" else ["An assertion about this person"]
    with pytest.raises(ValidationError, match="Inconsistent attribution at C001/you"):
        schema.model_validate(
            {"attributions": {"C001": {"you": {**row, "assertions": assertions}}}}
        )
    for assertions in [[""], ["x" * 501], ["Assertion"] * 13]:
        with pytest.raises(ValidationError):
            schema.model_validate(
                {"attributions": {"C001": {"you": {**row, "assertions": assertions}}}}
            )


def test_attribution_error_identifies_every_inconsistent_cell_without_repairing_it():
    schema = source_attribution_model(["C001", "C002"], ["you"], {"you"})
    response = {
        "attributions": {
            "C001": {
                "you": {
                    "assertions": ["An assertion"],
                    "relation_to_claim": "reporting_only",
                }
            },
            "C002": {"you": {"assertions": [], "relation_to_claim": "described"}},
        }
    }
    before = json.dumps(response)
    with pytest.raises(ValidationError, match="C001/you, C002/you"):
        schema.model_validate(response)
    assert json.dumps(response) == before


def test_presentation_cannot_add_omit_or_reassign_pages():
    schema = page_plan_model(
        {"C001": ["you", "project"], "C002": []},
        {"you": "you", "project": "project", "other": "person"},
    )
    row = presentation(
        {"you": "current_context", "project": "current_status"}, "project"
    )
    schema.model_validate({"decisions": {"C001": row}})
    for change in [
        {"primary_subject": "other"},
        {"pages": {"you": "current_context"}},
        {"pages": {**row["pages"], "other": "profile"}},
        {"pages": {"you": "overview", "project": "profile"}},
    ]:
        with pytest.raises(ValidationError):
            schema.model_validate({"decisions": {"C001": {**row, **change}}})
    with pytest.raises(ValidationError):
        schema.model_validate({"decisions": {"C001": row, "C002": row}})
    for pages in [["unknown"], ["you", "you"]]:
        with pytest.raises(ValueError, match="unique resolved"):
            page_plan_model({"C001": pages}, {"you": "you"})


def test_empty_domains_are_explicit_and_cannot_invent_attribution_or_pages():
    schema = source_attribution_model(["C001"], [], set())
    schema.model_validate({"attributions": {"C001": {}}})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {"attributions": {"C001": {"invented": attribution("described")}}}
        )
    schema = page_plan_model({"C001": []}, {})
    schema.model_validate({"decisions": {}})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {"decisions": {"C001": presentation({"invented": "overview"}, "invented")}}
        )


def test_attribution_input_carries_evidence_and_identity_without_page_state():
    subjects = [
        {
            "entity_id": "p",
            "entity_type": "person",
            "title": "Person",
            "participant_bindings": [],
            "source_subjects": [],
        }
    ]
    evidence = {
        "claims": {
            "C001": {
                "text": "A source statement",
                "citations": [{"source_id": "s", "segment_id": "x"}],
            }
        },
        "sources": {"s": {"segments": {"x": {"text": "A source statement"}}}},
    }
    _, user = source_attribution_prompt(subjects, evidence)
    assert json.loads(user) == {"resolved_subjects": subjects, **evidence}
    evidence["claims"]["C001"].update(
        identity_references=[
            {"role": "identity_subject", "entity_id": "other", "origin": "manual"}
        ],
        about=[{"entity": "old inferred subject"}],
        claim_id="stored-c1",
    )
    _, changed = source_attribution_prompt(subjects, evidence)
    assert changed == user


def test_attribution_scopes_identity_descriptions_without_mutating_the_plan():
    subjects = [
        {
            "entity_id": "p",
            "title": "Canonical name",
            "source_subjects": [
                {
                    "title": "Earlier description",
                    "description": "A previously resolved occurrence",
                    "supporting_evidence": ["C001", "C002"],
                },
                {
                    "title": "Separate occurrence",
                    "description": "Context from a different batch",
                    "supporting_evidence": ["C003"],
                },
            ],
        }
    ]
    evidence = {
        "claims": {
            "C002": {
                "text": "A statement",
                "citations": [{"source_id": "s", "segment_id": "x"}],
            }
        },
        "sources": {"s": {"segments": {"x": {"text": "Exact source"}}}},
    }
    before = json.dumps([subjects, evidence])
    _, user = source_attribution_prompt(subjects, evidence)
    payload = json.loads(user)
    assert payload["resolved_subjects"][0]["source_subjects"] == [
        {**subjects[0]["source_subjects"][0], "supporting_evidence": ["C002"]}
    ]
    assert payload["claims"] == evidence["claims"]
    assert payload["sources"] == evidence["sources"]
    assert json.dumps([subjects, evidence]) == before
