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
    system = """Organize one cohort of source-grounded memory claims into a concise personal wiki.

Do entity discovery and claim ownership as one globally consistent decision. Define each genuinely new
entity once with an N001-style candidate ID, cite every materially supporting claim alias, then assign every
claim either to an existing entity ID, to one candidate ID, to deferred, or to source_only. Assignments may
cite other claims whose shared context establishes the owner. Never use an undeclared candidate ID.

Resolve every supplied P001-style participant occurrence to either `you`, an existing Person ID, or a
declared Person candidate. A participant-backed Person candidate cites those participant aliases using
supporting_participants and uses creation_basis=meeting_participant. Repeated names, variants, and aliases
must be resolved semantically in this one plan; deterministic code will not compare participant strings.
An occurrence with speaker_role=user must resolve to `you`. Every other supplied meeting speaker must
resolve to an existing Person or a declared Person candidate, never to `you` or another entity type.

The owner is the entity whose state, requirements, plans, responsibilities, or history the claim changes.
Use the cohort to resolve aliases and evolving names: early descriptions of an endeavor must attach to its
later established Project. Components, vendors, technologies, issues, phases, pilots, milestones, meetings,
and research subjects belong to the established Project they serve unless they have clear value and continuity
independent of it. Mark such candidates independent_scope=false and do not assign claims to them as pages.

Follow this order: (1) identify existing entities and all qualifying new candidates using the entire cohort;
(2) resolve early descriptions, later names, and participant references to those entities; (3) assign every
claim. Do not defer a claim merely because its owner was absent before this pass when the cohort now satisfies
the creation policy. A canonical assignment must have a nonempty existing entity ID or declared candidate ID.
Claims grounded in user speech about the user's own identity, preferences, relationships, or plans normally
belong to the existing `you` entity unless a more specific established entity is their subject.

Creation policy:
- People are eligible from retained evidence; meeting participants may already exist in the registry.
- A named Project uses creation_basis=named_project and needs an explicit identity claim plus another
  substantive supporting claim.
- An inferred Project needs non-equivalent evidence across multiple source episodes plus a continuity signal.
- Topics, Organizations, Places, and Events need explicit independent user relevance or recurring support;
  a single tool observation, incidental location, routine event, or named component is insufficient.
- Do not create catchalls or duplicate an existing title or alias.

A recurring personal endeavor is also a Project when it has a continuing purpose and concrete work or a
scheduled next step across sources. Do not route the endeavor's facts to `you` merely because the user
performs it. The user relationship may link to the Project, while incidental appointments and locations
remain subordinate. Source IDs show whether evidence recurs across episodes. A named relative or collaborator
discussed substantively in retained user evidence deserves a Person candidate even when they are not a
labeled meeting participant.

Use canonical when a claim is useful on a justified page. Use deferred when more context is needed. Use
source_only for valid but tangential, low-value, control-plane, assistant-only, sponsored, routine, or cosmetic
information that should remain inspectable source memory but not wiki content. External evidence can support a
Project but cannot automatically establish a personal fact on You.

For a project_role relationship, the Person or You is the canonical owner and exactly one Project is linked.
Return every supplied claim alias and participant alias exactly once. Candidate titles must be concise human
page titles without redundant type labels. Return JSON only."""
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
