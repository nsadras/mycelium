"""Typed entry points for production memory prompt templates."""

from mycelium.prompting import render_prompt, render_prompt_pair


_EXTRACTION_POLICY_TEMPLATES = {
    "agent_conversation": "memory/extraction_policies/agent_conversation.jinja",
    "meeting_transcript": "memory/extraction_policies/meeting_transcript.jinja",
    "multi_party_conversation": "memory/extraction_policies/multi_party_conversation.jinja",
    "tool_observation": "memory/extraction_policies/tool_observation.jinja",
}


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
        source_id=source_id,
        participants=participants,
        segments=segments,
        context=context,
    )
