"""Production prompts for extraction, routing, and reconsolidation."""


def entity_discovery_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Discover durable semantic entities that deserve their own wiki pages.

This is entity discovery, not claim placement. Return only genuinely new entities absent from the
registry. Projects are named outcomes or continuing endeavors with continuity, commitment, or multiple
supporting claims; they do not require a brand name. Examples include opening a dance studio or building
an online clothing store. People need a durable relationship or recurring substantive relevance. Topics
need intentional ongoing research or two non-equivalent claims. Organizations and places need lasting
relevance. Events must be named, substantial, and consequential. Do not create pages for incidental
objects, generic activities, routine appointments, broad catchalls, or a second entity already represented
by an existing title or alias.

Consider the supplied claims as one episodic cohort. Evidence from different source episodes may jointly
establish a durable entity even when no individual claim is sufficient. Return one exact top-level property
for every supplied C001-style EVIDENCE alias and no others. Put the same fully specified candidate on every
claim that materially supports it, and candidate=null on claims that do not support a new entity. Each claim
may support at most one new entity in this pass. A concrete continuing venture or outcome is a Project even without a
proper name: for example, “a person is starting a dance studio” establishes Project “Dance Studio.” A plan
to start a generic, still-undefined “business” does not. Repeated candidate proposals are consolidated
deterministically. Return JSON only."""
    user = f"""ENTITY REGISTRY:
{index_content}

SOURCE-GROUNDED CLAIMS:
{evidence}"""
    return system, user


def cohort_scope_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Organize one cohort of retained claims into durable wiki identities and claim owners.

Use the whole cohort. Reuse an existing stable ID when evidence describes the same real subject, including
an early description that receives a name later. Otherwise define a new identity once with an N001-style ID
and cite the C001-style claims or P001-style participants that establish it. Do not create duplicate,
catchall, component, phase, tool, vendor, issue, deliverable, or routine-session pages.

Create only independently useful identities:
- Person: a human with a durable relationship or substantive relevance.
- Project: a continuing endeavor or outcome supported by concrete work, commitment, or recurring activity
  across the evidence. Its individual sessions and milestones remain part of the Project.
- Event: one bounded occurrence with lasting significance independent of a continuing Project.
- Topic, Organization, or Place: independently and durably relevant, not merely incidental or tool-reported.

Use named_project for an explicitly named Project, project_continuity for an inferred Project,
meeting_participant for a participant-backed Person, and the matching schema basis for other types.
Set independent_scope=false when a proposed identity is subordinate rather than page-worthy.

The claim owner is the identity whose state, plans, requirements, responsibilities, relationships, or history
the claim changes. Assign every supplied claim exactly once to an existing ID, a declared candidate ID, or
deferred. Claims already passed retention policy: defer only when identity or ownership lacks evidence.
Reconsider prior assignments when the full cohort resolves them. User-authored personal facts belong to `you`
unless a more specific subject owns them. External evidence may support another entity but does not establish
a personal fact about `you` by itself.

Resolve every supplied participant exactly once. speaker_role=user resolves to `you`; every other speaker
resolves to an existing Person or a declared Person candidate. Use the supplied mention roles and stable
entity references as evidence when resolving people and other subjects.

For every canonical claim, fill subject_entity, object_entities, and contextual_entities with supplied stable
IDs when those semantic roles exist, and include non-owner endpoints in linked_entities. For project_role,
the Person or `you` is the owner and exactly one Project is linked.

Return every supplied claim and participant alias exactly once. Use only declared candidate IDs, exact evidence
aliases, concise human page titles, and JSON matching the schema."""
    user = f"""ENTITY REGISTRY AND SECTION CONTRACT:
{index_content}

SOURCE-GROUNDED CLAIM COHORT:
{evidence}"""
    return system, user


def consolidated_fact_prompt(evidence: str) -> tuple[str, str]:
    """Plan concise wiki statements without changing canonical source claims."""
    system = """You organize already-routed memory claims into concise wiki facts.
Every claim alias must appear exactly once. Group claims only when they express the same fact,
or complementary details that read more clearly as one statement. Never group contradictions,
alternatives, unrelated facts, or claims from different owner/section scopes. Preserve all names,
dates, quantities, commitments, constraints, and uncertainty. The output text must be directly
entailed by its member claims; do not add explanations or inferred conclusions. Prefer one crisp
sentence, but use two when compression would omit information. This is presentation synthesis:
the original claims remain canonical and source-linked."""
    user = f"""Create the fact groups for this routed cohort:

{evidence}

Return every alias exactly once. The owner and section printed on each claim are fixed and cannot
be changed by grouping."""
    return system, user


def consolidation_identify_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Assign every durable memory claim one existing semantic owner.

The owner is the entity whose state, requirements, plans, or relationship the claim changes. It is
not automatically the speaker, the first named noun, or the user. Entity discovery has already finished:
use only an existing entity ID from the registry and never invent one. Most supplied claims should be
placed. A person's profile, state, preferences, plans, relationships, and ordinary timeline events belong
to that Person unless a more specific existing Project, Organization, Place, Topic, or Event is the entity
whose state or requirements change. Typed wiki sections are assigned deterministically after ownership.
For predicate=project_role, the Person (or You) is the canonical owner and the Project must be included in
linked_entities. The deterministic wiki projection will present that one relationship on both endpoint pages.

Set owner_entity empty and provide no links only when current evidence is insufficient to choose an existing
entity. This defers the claim in short-term memory so a later Dream can reconsider it with more context.
linked_entities contains only supplied existing entity IDs that are substantively
referenced; do not infer links from co-occurrence. External/tool evidence belongs only in
research_references, or evidence for event pages, and must never establish a You fact automatically.

Return one exact top-level property for every supplied C001-style EVIDENCE alias and no others. Respond
with JSON only."""
    user = f"""ENTITY REGISTRY AND SECTION CONTRACT:
{index_content}

SOURCE-GROUNDED CLAIMS:
{evidence}"""
    return system, user


def claim_reconsolidation_prompt(
    incoming_alias: str,
    incoming_claim: str,
    candidates: str,
) -> tuple[str, str]:
    system = """Compare one new source-grounded claim with existing canonical memory claims.

Return exactly one decision for the supplied incoming alias. Choose:
- additive: the new claim adds independent information;
- supports: it independently supports the same fact as one existing claim;
- contradicts: both claims cannot be true as stated, but the new claim is not clearly a replacement;
- supersedes: the new claim is an explicit correction or a newer value of the same replaceable state.

For additive, target_alias must be empty. For every other relation, copy exactly one supplied existing
alias. Do not infer a conflict merely from different wording, dates, or adjacent facts. Supersedes
requires clear replacement semantics, not simple recency. Return JSON only."""
    user = (
        f"INCOMING {incoming_alias}:\n{incoming_claim}\n\n"
        f"EXISTING CANDIDATES:\n{candidates}"
    )
    return system, user


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

Encode a continuing role or responsibility connecting a person to a project as
claim_type=relationship and predicate=project_role; include both the person and project in about, with the
person as subject. Do not classify a one-off action item, attendance, or incidental contribution as a role.

Populate claim_type (identity/state/event/preference/plan/belief/relationship/decision/commitment/
interaction/observation/unknown), an open predicate, evidence_modality, temporal_status, about,
speaker, confidence, optional replaceable-state slot, and open facets. Put exact time wording in
facets.when for event times and facets.deadline for due dates. Never convert relative time yourself;
preserve phrases such as “by Friday” or “in three days” exactly so the deterministic resolver can anchor
them to OCCURRED AT. Use inferred only for a strong implication with facets.inference_basis and confidence at
most 0.7.

The about list is semantic routing data, not a keyword list. Include the primary subject whose state,
belief, preference, plan, relationship, or action the claim predicates, with role=subject. Include a
different durable entity with role=owner when the claim chiefly changes that entity (for example, a
project requirement). Other named participants may use role=participant. Do not put incidental objects,
generic activities, or predicate complements in about merely because their words occur in the claim.

Account for every segment once: cite it from claims when substantive, or put it in
ignored_segment_ids when it is only scaffolding, filler, raw image URL, transport metadata, or an
exact repetition. Do not omit a substantive claim because it seems unimportant. Return JSON only."""
    user = f"""SOURCE ID: {source_id}
OCCURRED AT: {occurred_at or 'unknown'}

SEGMENTS:
{segments}"""
    return system, user
