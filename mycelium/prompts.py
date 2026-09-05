"""Typed entry points for production memory prompt templates."""

from mycelium.ontology import (
    CLAIM_TYPES,
    EXTRACTION_SUBJECT_POLICY,
    FACT_EVIDENCE_POLICY,
    ROUTING_OWNERSHIP_POLICY,
    ROUTING_SUBJECT_POLICY,
    SUBJECT_CENSUS_POLICY,
    SUBJECT_PAGE_STATE_POLICY,
    entity_type_prompt_catalog,
    subject_scope_prompt_catalog,
)
from mycelium.prompting import render_prompt, render_prompt_pair


_EXTRACTION_POLICY_TEMPLATES = {
    "agent_conversation": "memory/extraction_policies/agent_conversation.jinja",
    "meeting_transcript": "memory/extraction_policies/meeting_transcript.jinja",
    "multi_party_conversation": "memory/extraction_policies/multi_party_conversation.jinja",
    "tool_observation": "memory/extraction_policies/tool_observation.jinja",
}


def subject_node_prompt(
    index_content: str,
    candidates: str,
    evidence: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/subject_nodes",
        registry=index_content,
        candidates=candidates,
        evidence=evidence,
        subject_policy=SUBJECT_CENSUS_POLICY,
    )


def identity_node_matching_prompt(
    registry: str,
    node: str,
    evidence: str,
    reviewed_adjudications: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/identity_node_matching",
        registry=registry,
        node=node,
        evidence=evidence,
        reviewed_adjudications=reviewed_adjudications,
    )


def local_identity_matching_prompt(
    node: str,
    evidence: str,
    local_identities: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/local_identity_matching",
        node=node,
        evidence=evidence,
        local_identities=local_identities,
    )


def pending_identity_matching_prompt(
    identity: str,
    evidence: str,
    pending_proposals: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/pending_identity_matching",
        identity=identity,
        evidence=evidence,
        pending_proposals=pending_proposals,
    )


def new_identity_verification_prompt(
    proposed_identity: str,
    registry: str,
    evidence: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/new_identity_verification",
        proposed_identity=proposed_identity,
        registry=registry,
        evidence=evidence,
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
    maturity_decisions: str,
    evidence: str,
    reviewed_adjudications: str = "none",
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/entity_plan",
        registry=registry,
        nodes=nodes,
        maturity_decisions=maturity_decisions,
        evidence=evidence,
        reviewed_adjudications=reviewed_adjudications,
        subject_scopes=subject_scope_prompt_catalog(),
        page_state_policy=SUBJECT_PAGE_STATE_POLICY,
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
        subject_policy=ROUTING_SUBJECT_POLICY,
        ownership_policy=ROUTING_OWNERSHIP_POLICY,
    )


def fact_truth_prompt(
    owner: str,
    claims: str,
    existing_facts: str,
    reviewed_relations: str,
    incoming_claims: str,
    prior_decisions: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/fact_truth",
        owner=owner,
        claims=claims,
        existing_facts=existing_facts,
        reviewed_relations=reviewed_relations,
        incoming_claims=incoming_claims,
        prior_decisions=prior_decisions,
    )


def fact_candidate_selection_prompt(
    incoming_claims: str,
    prior_facts: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/fact_candidate_selection",
        incoming_claims=incoming_claims,
        prior_facts=prior_facts,
    )


def assistant_context_selection_prompt(
    query: str,
    candidates: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "assistant/context_selection",
        query=query,
        candidates=candidates,
    )


def fact_grouping_prompt(
    owner: str,
    claims: str,
    existing_facts: str,
    truth_changes: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/fact_grouping",
        owner=owner,
        claims=claims,
        existing_facts=existing_facts,
        truth_changes=truth_changes,
    )


def fact_rendering_prompt(
    owner: str,
    sections: str,
    groups: str,
    existing_facts: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/fact_rendering",
        owner=owner,
        sections=sections,
        groups=groups,
        existing_facts=existing_facts,
        fact_evidence_policy=FACT_EVIDENCE_POLICY,
    )


def fact_group_quality_prompt(
    owner: str,
    group: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/fact_group_quality",
        owner=owner,
        group=group,
    )


def fact_quality_prompt(
    owner: str,
    rendered_facts: str,
    groups: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/fact_quality",
        owner=owner,
        rendered_facts=rendered_facts,
        groups=groups,
        fact_evidence_policy=FACT_EVIDENCE_POLICY,
    )


def fact_repair_prompt(
    owner: str,
    rejected_facts: str,
    groups: str,
) -> tuple[str, str]:
    return render_prompt_pair(
        "memory/fact_repair",
        owner=owner,
        rejected_facts=rejected_facts,
        groups=groups,
        fact_evidence_policy=FACT_EVIDENCE_POLICY,
    )


def claim_extraction_prompt(
    source_type: str,
    source_id: str,
    participants: list[str],
    segments: str,
    context: str = "",
) -> tuple[str, str]:
    policy_template = _EXTRACTION_POLICY_TEMPLATES.get(
        source_type,
        _EXTRACTION_POLICY_TEMPLATES["agent_conversation"],
    )
    return render_prompt_pair(
        "memory/extraction",
        source_type=source_type,
        source_policy=render_prompt(policy_template),
        subject_policy=EXTRACTION_SUBJECT_POLICY,
        claim_types=CLAIM_TYPES,
        source_id=source_id,
        participants=participants,
        segments=segments,
        context=context,
    )
