"""Typed entry points for production memory prompt templates."""

from mycelium.ontology import CLAIM_TYPES
from mycelium.prompting import render_prompt, render_prompt_pair


_EXTRACTION_POLICY_TEMPLATES = {
    "agent_conversation": "memory/extraction_policies/agent_conversation.jinja",
    "meeting_transcript": "memory/extraction_policies/meeting_transcript.jinja",
    "multi_party_conversation": "memory/extraction_policies/multi_party_conversation.jinja",
    "tool_observation": "memory/extraction_policies/tool_observation.jinja",
}


def subject_node_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/subject_nodes",
        registry=index_content,
        evidence=evidence,
    )


def entity_plan_prompt(
    registry: str,
    nodes: str,
    evidence: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/entity_plan",
        registry=registry,
        nodes=nodes,
        evidence=evidence,
    )


def claim_routing_prompt(
    registry: str,
    entity_plan: str,
    evidence: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/claim_routing",
        registry=registry,
        entity_plan=entity_plan,
        evidence=evidence,
    )


def consolidated_fact_prompt(evidence: str) -> tuple[str, str]:
    """Plan concise wiki statements without changing canonical source claims."""
    return render_prompt_pair("memory/fact_synthesis", evidence=evidence)


def claim_reconsolidation_prompt(
    incoming_alias: str,
    incoming_claim: str,
    candidates: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/reconsolidation",
        incoming_alias=incoming_alias,
        incoming_claim=incoming_claim,
        candidates=candidates,
    )


def claim_extraction_prompt(
    source_type: str,
    source_id: str,
    occurred_at: str | None,
    segments: str,
) -> tuple[str, str]:
    policy_template = _EXTRACTION_POLICY_TEMPLATES.get(
        source_type,
        _EXTRACTION_POLICY_TEMPLATES["agent_conversation"],
    )
    return render_prompt_pair(
        "memory/extraction",
        source_type=source_type,
        source_policy=render_prompt(policy_template),
        claim_types=CLAIM_TYPES,
        source_id=source_id,
        occurred_at=occurred_at,
        unknown_time="unknown",
        segments=segments,
    )
