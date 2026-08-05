"""Production prompts for extraction, routing, and reconsolidation."""


def consolidation_identify_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Route source-grounded memory claims to focused wiki pages.

Use entity pages for named people, organizations, places, products, and pets; event pages for
specific dated events; and topic pages for projects, goals, tools, or coherent areas of work.
Prefer an existing page from the supplied catalog when it fits. Use stable lowercase hyphenated
slugs and at most eight distinct pages per batch. Never create generic catch-all or placeholder
pages. Named participants are not implicitly the system user.

Return exactly one decision for every EVIDENCE alias. Copy each alias exactly once. A decision has:
- evidence_alias: the supplied C001-style alias;
- disposition: route or ignore;
- page: a page slug for route, otherwise an empty string;
- action: update/create for route, otherwise none;
- page_type: entity, event, or topic.

Route each claim to one page. Ignore transient questions, scaffolding, generic knowledge, and facts
that are not useful as durable personalized memory. Respond with JSON only."""
    user = f"""WIKI PAGE CATALOG:
{index_content}

SOURCE-GROUNDED CLAIMS:
{evidence}"""
    return system, user


def prediction_error_prompt(wiki_page: str, current_context: str) -> tuple[str, str]:
    system = """Assess whether current context makes a retrieved memory page inaccurate or incomplete.
Return JSON with conflict_type (none/additive/partial/major), discrepancy_score from 0 to 1,
explanation, and suggested_update. Do not treat merely related information as contradiction."""
    return system, f"STORED PAGE:\n{wiki_page}\n\nCURRENT CONTEXT:\n{current_context}"


def reconsolidation_rewrite_prompt(original_page: str, update_signals: str) -> tuple[str, str]:
    system = """Rewrite a flagged wiki page using the supplied update signals. Preserve grounded facts,
resolve actual contradictions explicitly, and do not invent information. Return JSON with title,
content, and confidence only."""
    return system, f"ORIGINAL PAGE:\n{original_page}\n\nUPDATE SIGNALS:\n{update_signals}"


def routing_prompt(index_content: str, query: str, budget_tokens: int) -> tuple[str, str]:
    system = f"""Select up to eight existing wiki pages relevant to the user query, within a memory
budget of {budget_tokens} tokens. Return a JSON list with page, priority (1 highest), and reason.
Never invent a page not present in the index. Respond with JSON only."""
    return system, f"WIKI INDEX:\n{index_content}\n\nUSER QUERY:\n{query}"


def claim_extraction_prompt(
    source_type: str,
    source_id: str,
    occurred_at: str | None,
    segments: str,
) -> tuple[str, str]:
    policies = {
        "agent_conversation": (
            "Prioritize user facts, preferences, constraints, commitments, corrections, and accepted "
            "decisions. Assistant proposals are interaction history unless the user accepts them."
        ),
        "meeting_transcript": (
            "Capture decisions, proposals, action items, owners, deadlines, objections, commitments, "
            "reported events, and status changes while preserving each speaker's stance."
        ),
        "multi_party_conversation": (
            "Capture durable facts for every named participant, preserve ownership, and ignore routine "
            "greetings, thanks, generic praise, encouragement, and content-free questions."
        ),
        "tool_observation": (
            "Capture only specific source-grounded facts useful to the user's project or decision. "
            "Ignore arguments, transport metadata, errors, search labels, navigation, citation widgets, "
            "page furniture, and generic textbook information. Use evidence_modality=tool."
        ),
    }
    policy = policies.get(source_type, policies["agent_conversation"])
    system = f"""Extract durable atomic claims from {source_type} segments in one pass.

Policy: {policy}

Each claim must be one standalone third-person subject-predicate assertion with explicit named
entities. Resolve first/second-person references; do not copy dialogue-shaped text. Preserve exact
names, dates, relative-time phrases, locations, quantities, reasons, and ownership. Cite only supplied
segment IDs that directly support the claim. Do not invent context or combine unrelated facts.

Populate claim_type (identity/state/event/preference/plan/belief/relationship/decision/commitment/
interaction/observation/unknown), an open predicate, evidence_modality, temporal_status, about,
speaker, confidence, optional replaceable-state slot, and open facets. Put exact time wording in
facets.when. Use inferred only for a strong implication with facets.inference_basis and confidence at
most 0.7.

Account for every segment once: cite it from claims when substantive, or put it in
ignored_segment_ids when it is only scaffolding, filler, raw image URL, transport metadata, or an
exact repetition. Do not omit a substantive claim because it seems unimportant. Return JSON only."""
    user = f"""SOURCE ID: {source_id}
OCCURRED AT: {occurred_at or 'unknown'}

SEGMENTS:
{segments}"""
    return system, user
