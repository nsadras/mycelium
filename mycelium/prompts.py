"""Typed entry points for production memory prompt templates."""

from mycelium.ontology import (
    CLAIM_TYPES,
    EXTRACTION_SUBJECT_POLICY,
    FACT_EVIDENCE_POLICY,
)
from mycelium.prompting import render_prompt, render_prompt_pair


_EXTRACTION_POLICY_TEMPLATES = {
    "agent_conversation": "memory/extraction_policies/agent_conversation.jinja",
    "meeting_transcript": "memory/extraction_policies/meeting_transcript.jinja",
    "multi_party_conversation": "memory/extraction_policies/multi_party_conversation.jinja",
    "tool_observation": "memory/extraction_policies/tool_observation.jinja",
}


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
