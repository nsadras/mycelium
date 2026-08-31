"""Typed entry points for production memory prompt templates."""

from mycelium.ontology import CLAIM_TYPES, entity_type_prompt_catalog
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


def identity_matching_prompt(
    registry: str,
    nodes: str,
    evidence: str,
    reviewed_adjudications: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/identity_matching",
        registry=registry,
        nodes=nodes,
        evidence=evidence,
        reviewed_adjudications=reviewed_adjudications,
    )


def identity_types_prompt(identities: str, evidence: str) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/identity_types",
        identities=identities,
        evidence=evidence,
        ontology=entity_type_prompt_catalog(discoverable_only=True),
    )


def identity_type_verification_prompt(
    proposals: str,
    identities: str,
    evidence: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/identity_type_verification",
        proposals=proposals,
        identities=identities,
        evidence=evidence,
        ontology=entity_type_prompt_catalog(discoverable_only=True),
    )


def identity_maturity_prompt(nodes: str, evidence: str) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/identity_maturity",
        nodes=nodes,
        evidence=evidence,
    )


def identity_maturity_verification_prompt(
    proposals: str, evidence: str
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/identity_maturity_verification",
        proposals=proposals,
        evidence=evidence,
    )


def entity_plan_prompt(
    registry: str,
    nodes: str,
    evidence: str,
    reviewed_adjudications: str = "none",
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/entity_plan",
        registry=registry,
        nodes=nodes,
        evidence=evidence,
        reviewed_adjudications=reviewed_adjudications,
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


def fact_resolution_prompt(
    owner: str,
    sections: str,
    claims: str,
    existing_facts: str,
    reviewed_relations: str,
) -> tuple[str, str]:
    """Resolve one owner's claims into a complete source-grounded fact plan."""
    return render_prompt_pair(
        "memory/fact_resolution",
        owner=owner,
        sections=sections,
        claims=claims,
        existing_facts=existing_facts,
        reviewed_relations=reviewed_relations,
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
