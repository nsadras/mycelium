from pathlib import Path

import pytest
from jinja2 import StrictUndefined, UndefinedError

from mycelium import prompts
from mycelium.ontology import CLAIM_TYPES
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
        "identities": "identities",
        "proposals": "proposals",
        "entity_plan": "entity plan",
        "reviewed_adjudications": "none",
        "incoming_alias": "N001",
        "incoming_claim": "incoming claim",
            "candidates": "candidates",
            "owner": "owner",
            "sections": "sections",
            "claims": "claims",
            "existing_facts": "existing facts",
            "reviewed_relations": "reviewed relations",
        "source_type": "agent_conversation",
        "source_policy": "policy",
        "claim_types": CLAIM_TYPES,
        "source_id": "source-1",
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
        None,
        "[segment-1] A decision was made.",
    )

    assert f"claim_type ({'/'.join(CLAIM_TYPES)})" in system
    assert "Capture decisions, proposals, action items" in system
    assert "SOURCE ID: source-1" in user
    assert "OCCURRED AT: unknown" in user


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
