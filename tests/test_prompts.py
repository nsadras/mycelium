from pathlib import Path

import pytest
from jinja2 import StrictUndefined, UndefinedError

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
        "claim_types": ("state", "event"),
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
        "memory_evidence": "evidence",
        "no_memory_context": "none",
        "response_instructions": "answer directly",
        "user_request": "request",
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


def test_templates_are_packaged_inside_the_python_package() -> None:
    assert Path(TEMPLATE_ROOT, "memory", "extraction.system.jinja").is_file()
    assert Path(TEMPLATE_ROOT, "assistant", "memory_agent.system.jinja").is_file()
    assert Path(TEMPLATE_ROOT, "assistant", "memory_request.user.jinja").is_file()
    assert Path(TEMPLATE_ROOT, "engram", "summary.system.jinja").is_file()
    assert Path(TEMPLATE_ROOT, "benchmarks", "grounded_answer.system.jinja").is_file()
