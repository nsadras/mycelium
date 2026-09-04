from pathlib import Path

import pytest
from jinja2 import StrictUndefined, UndefinedError

from mycelium import prompts
from mycelium.ontology import CLAIM_TYPES, FACT_EVIDENCE_POLICY
from mycelium.prompting import TEMPLATE_ROOT, prompt_environment, render_prompt


def test_every_prompt_is_an_external_strict_jinja_template() -> None:
    environment = prompt_environment()
    assert environment.undefined is StrictUndefined
    assert environment.autoescape is False

    templates = environment.list_templates()
    assert templates
    assert all(name.endswith(".jinja") for name in templates)
    assert {
        path.relative_to(TEMPLATE_ROOT).as_posix()
        for path in TEMPLATE_ROOT.rglob("*.jinja")
    } == set(templates)

    shared_context = {
        "registry": "registry",
        "ontology": "ontology",
        "evidence": "evidence",
        "nodes": "nodes",
        "maturity_decisions": "maturity decisions",
        "node": "node",
        "identities": "identities",
            "local_identities": "local identities",
            "identity": "identity",
            "pending_proposals": "pending proposals",
        "proposals": "proposals",
        "entity_plan": "entity plan",
        "reviewed_adjudications": "none",
            "subject_policy": "subject policy",
            "ownership_policy": "ownership policy",
            "fact_evidence_policy": "fact evidence policy",
        "subject_scopes": "subject scopes",
        "page_state_policy": "page-state policy",
        "proposed_identity": "identity",
        "incoming_alias": "N001",
        "incoming_claim": "incoming claim",
            "candidates": "candidates",
            "owner": "owner",
            "groups": "groups",
            "group": "group",
            "truth_changes": "truth changes",
            "incoming_claims": "incoming claims",
            "sections": "sections",
            "claims": "claims",
            "existing_facts": "existing facts",
            "reviewed_relations": "reviewed relations",
            "prior_decisions": "prior decisions",
            "prior_facts": "prior facts",
            "rendered_facts": "rendered facts",
            "rejected_facts": "rejected facts",
        "source_type": "agent_conversation",
        "source_policy": "policy",
        "claim_types": CLAIM_TYPES,
            "source_id": "source-1",
            "participants": ["Ava", "Dana"],
        "occurred_at": None,
        "unknown_time": "unknown",
        "segments": "segments",
        "chat_topic": "topic",
        "recent_thread": "thread",
        "no_prior_turns": "none",
        "user_message": "message",
        "memory_context": "context",
        "no_memory_context": "none",
        "title": "Meeting",
        "transcript": "Transcript",
        "summaries": ["one", "two"],
            "question": "question",
            "query": "query",
            "payload": '{"answer": "value"}',
    }
    for name in templates:
        assert render_prompt(name, **shared_context)


def test_missing_template_variables_fail_closed() -> None:
    with pytest.raises(UndefinedError):
        render_prompt("memory/extraction.user.jinja", source_id="source-1")


def test_extraction_injects_schema_values_and_source_policy() -> None:
    system, user = prompts.claim_extraction_prompt(
        "meeting_transcript",
        "source-1",
        ["Ava", "Dana"],
        "[segment-1] A decision was made.",
    )

    assert f"claim_type ({'/'.join(CLAIM_TYPES)})" in system
    assert "Capture decisions, proposals, action items" in system
    assert "SOURCE: source-1" in user
    assert "SOURCE PARTICIPANTS:\n- Ava\n- Dana" in user
    assert "SOURCE TIME" not in user


def test_extraction_explains_structured_memory_terms() -> None:
    system, _ = prompts.claim_extraction_prompt(
        "agent_conversation",
        "source-1",
        ["Dana"],
        "[segment-1] Dana selected Atlas.",
    )

    assert "A stored claim is one source-supported assertion" in system
    assert "`about` lists the named identities" in system
    assert "`slot` optionally names a replaceable state" in system
    assert "`facets` stores structured details" in system
    assert "`evidence_modality` records how the evidence was observed" in system
    assert "`evidence_type` records whether the assertion was directly stated" in system


def test_fact_prompts_share_the_authoritative_evidence_policy() -> None:
    prompt_pairs = [
        prompts.fact_rendering_prompt("owner", "sections", "groups", "facts"),
        prompts.fact_quality_prompt("owner", "rendered", "groups"),
        prompts.fact_repair_prompt("owner", "rejected", "groups"),
    ]

    for system, _ in prompt_pairs:
        assert FACT_EVIDENCE_POLICY in system


def test_entity_plan_receives_fixed_page_admission_decisions() -> None:
    system, user = prompts.entity_plan_prompt(
        "registry",
        "nodes",
        "N001: admission=provisional; verification=not_required",
        "evidence",
    )

    assert "A page-admission decision says" in system
    assert "Treat that decision" in system
    assert "verification result as fixed" in system
    assert "FIXED PAGE-ADMISSION DECISIONS:" in user
    assert "admission=provisional; verification=not_required" in user


def test_subject_census_prompt_explains_the_task_and_local_terms() -> None:
    system, user = prompts.subject_node_prompt(
        "registry", "candidate checklist", "evidence"
    )

    assert system.startswith("Build a complete list of the distinct subjects")
    assert "node groups candidate mentions that refer to one real-world subject" in system
    assert "C... identifies a stored claim" in system
    assert "P... identifies a" in system
    assert "source-declared participant" in system
    assert "A date, time, duration, deadline, or age is not a subject" in system
    assert "Do not choose identity" in system
    assert "ontology type" in system
    assert "complete typed census" not in system
    assert user.startswith("KNOWN ENTITY TYPES AND IDENTITIES:\nregistry")
    assert "ELIGIBLE SUBJECT CANDIDATES:\ncandidate checklist" in user
    assert "CLAIMS, PARTICIPANTS, AND SOURCE EVIDENCE:\nevidence" in user


def test_prompt_templates_preserve_structured_multiline_inputs() -> None:
    _, routing_user = prompts.claim_routing_prompt(
        "ENTITY one\nENTITY two",
        "PLAN one\nPLAN two",
        "[C001] first\n[C002] second",
    )
    reduction = render_prompt(
        "engram/reduction.user.jinja",
        title="Planning",
        summaries=['{"part": 1}', '{"part": 2}'],
    )

    assert "ENTITY one\nENTITY two" in routing_user
    assert "[C001] first\n[C002] second" in routing_user
    assert reduction == (
        "Meeting title: Planning\n\nPartial summaries in chronological order:\n"
        'PART 1:\n{"part": 1}\nPART 2:\n{"part": 2}'
    )


def test_templates_are_packaged_inside_the_python_package() -> None:
    assert Path(TEMPLATE_ROOT, "memory", "extraction.system.jinja").is_file()
    assert Path(TEMPLATE_ROOT, "assistant", "chat.system.jinja").is_file()
    assert Path(TEMPLATE_ROOT, "engram", "summary.system.jinja").is_file()
    assert Path(TEMPLATE_ROOT, "benchmarks", "grounded_answer.system.jinja").is_file()
