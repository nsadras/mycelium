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


def subject_graph_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Build a subject graph from one source-grounded memory cohort.

Reserved-user rule: the registry's `you` identity is already a graph endpoint and must never appear in the nodes
array. First identify evidence about the configured user from structural user labels and the names or aliases on the
registry's `you` record. Represent that subject only with the literal endpoint `you` in edges and participant
resolutions. Before returning, remove any Person node that represents the configured user and replace its edge
endpoint with `you`.

This is a census and relationship pass, not page admission, identity matching, or claim ownership. Include each
distinct real subject needed to explain the retained claims, including meaningful Project components. Define one
node per real subject across the whole cohort: merge short and full names, participant appearances, and repeated
mentions into that node and combine their evidence. Do not omit a Person merely because their evidence occurs
inside a Project.

Use this identity ontology exactly:
- Person is a human.
- Organization is a group.
- Project is an intentional effort with an outcome whose plans, work, decisions, or status continue over time. A
  planned series of sessions with a continuing outcome is one Project.
- Event is one bounded occurrence, not a continuing series or Project component.
- Topic is a non-agent subject, body of knowledge, technology, tool, method, service, feature, issue, or deliverable
  when it needs a graph node.
- Place is a physical or geographic location only. Never create nodes for temporal expressions.

Define every subject once with an N001-style ID. Use `component_of` whenever a tool, pilot, session, milestone,
feature, issue, vendor, or deliverable gets its memory meaning from a Project. Use `participant_in` only for a Person,
Organization, or `you` involved in a Project or Event. Use `about` for a Project or Event concerning a Topic,
`located_at` only for a physical Place, and otherwise `related_to`. Every edge endpoint must be a declared node or
an exact stable ID copied from the supplied registry. Use a stable registry endpoint when the subject is already
unambiguous; use an N001-style node when identity still needs resolution. Cite only supplied C001-style claims or
P001-style participants. Resolve every supplied participant exactly once to `you`, an exact existing Person ID, or
a declared Person node. Do not decide whether a node deserves a page."""
    user = f"""ENTITY REGISTRY CONTEXT:
{index_content}

SOURCE-GROUNDED GRAPH EVIDENCE:
{evidence}"""
    return system, user


def graph_identity_resolution_prompt(
    index_content: str,
    graph: str,
    evidence: str,
) -> tuple[str, str]:
    system = """Resolve every subject-graph node to identity without deciding page admission.

When a node is the same continuing real subject as a same-type identity in the registry, including a shorter or
fuller name, useful alias, or stable relationship label, copy that exact stable ID. The singleton `you` ID is also
a compatible target for a Person node only when that node represents the configured user. When no compatible
existing identity represents the node, leave entity_id empty. Never otherwise map across types or introduce another subject.
preferred_title is the clearest evidence-grounded name and useful former descriptions belong in aliases. Resolve
every supplied N001-style node exactly once and return JSON matching the schema."""
    user = f"""ENTITY REGISTRY:
{index_content}

SUBJECT GRAPH:
{graph}

SOURCE-GROUNDED IDENTITY EVIDENCE:
{evidence}"""
    return system, user


def graph_admission_prompt(
    index_content: str,
    graph: str,
    evidence: str,
) -> tuple[str, str]:
    system = """Classify every resolved subject-graph node for user-memory admission.

`independent` means the subject can accumulate useful continuing state or history separately. `component` means
its memory value derives from a parent Project. `incidental` means it is a routine or one-off detail without
separately useful history. `established` means the source evidence itself shows stable continuity: continuing plans,
work, or state across distinct episodes, a durable personal relationship, or already useful accumulated history.
`emerging` means the identity is real but tentative or thinly supported. `not_applicable` is only for component or
incidental nodes.

Being a Project or being related to another subject does not make a node a component; only derived containment does.
A planned series with a continuing outcome across distinct episodes is an established independent Project. A tool,
deliverable, pilot, session, feature, issue, vendor, or Project-only research subject is a component when all of its
memory value comes from that Project. A routine appointment or ordinary bounded occurrence is incidental unless
the evidence shows independent lasting consequences. Use source-grounded memory value, never general-world
importance. Classify every supplied node exactly once. Do not decide a page label, change identities, or assign
claim ownership."""
    user = f"""RESOLVED ENTITY REGISTRY:
{index_content}

RESOLVED SUBJECT GRAPH:
{graph}

SOURCE-GROUNDED ADMISSION EVIDENCE:
{evidence}"""
    return system, user


def identity_verification_prompt(
    matches: str,
    evidence: str,
) -> tuple[str, str]:
    system = """Verify every proposed existing-identity match.

Decide only whether the candidate and existing identity are the same continuing real subject. A shared entity type,
shared Project, related work, or being the only registry option is not evidence of sameness. Different people,
organizations, topics, places, or events remain different even when they are closely related. Use only the supplied
identity records and cited source evidence. The singleton `you` identity can match a Person candidate only when the
candidate is the configured user named by that record or its aliases. Return every supplied candidate exactly once
and JSON matching the schema."""
    user = f"""PROPOSED IDENTITY MATCHES:
{matches}

SOURCE-GROUNDED EVIDENCE:
{evidence}"""
    return system, user


def claim_owner_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Choose one semantic owner for every retained claim.

Identity discovery has finished. Use only supplied stable entity IDs and never invent another identity. The
owner is the identity whose state, plans, requirements, responsibilities, relationships, or history the claim
changes. It is not automatically the speaker or first named noun. A bounded session, milestone, tool, vendor,
issue, or deliverable that belongs to a Project routes to that Project rather than becoming its own owner.
Treat a structured role=owner mention as strong, revisable evidence of the claim's semantic owner. Work,
decisions, schedules, requirements, and status for an endeavor route to its Project even when a person performs
the action. Knowledge or findings accumulated about a Topic route to that Topic. Keep the Person or `you` as
owner only when the claim primarily changes that person's own profile, preference, relationship, or personal
state. Use an empty owner only when the completed registry and evidence genuinely cannot identify one. Do not
defer merely because a claim mentions a contained event, tool, or deliverable; choose its lasting parent.

Claims already passed retention policy, so do not discard them. External evidence may support another entity but
does not establish a personal fact about `you` by itself. Do not resolve links or other entity roles. Return every
supplied claim alias exactly once and JSON matching the schema."""
    user = f"""COMPLETED ENTITY REGISTRY AND SECTION CONTRACT:
{index_content}

SOURCE-GROUNDED CLAIMS:
{evidence}"""
    return system, user


def claim_reference_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Resolve stable entity roles after claim ownership has already been fixed.

Copy only IDs from the completed registry. subject_entity is the entity whose action, state, belief, or
relationship the sentence directly predicates. object_entities are distinct recipients or semantic objects.
contextual_entities are durable entities that give the claim its setting without being subject or object.

The registry's `you` ID is the configured user's stable identity. When a claim explicitly relates multiple
registry identities, resolve every named participant: use object_entities for a non-owner relationship participant
and contextual_entities for the setting in which a relation or action occurs. For predicate=project_role, the
Person or `you` is the fixed owner and subject, and exactly one Project must be contextual. Do not change the
supplied owner, add entities merely because they occur in the same cohort, or infer an endpoint without evidence.
Leave roles empty when the claim does not establish a stable endpoint. Return every claim alias exactly once and
JSON matching the schema."""
    user = f"""COMPLETED ENTITY REGISTRY:
{index_content}

OWNED SOURCE-GROUNDED CLAIMS:
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
them to their evidence time. When timestamped segments are supplied, a claim with relative time must copy the
one cited segment ID containing that time expression into temporal_anchor_segment_id. Otherwise leave
temporal_anchor_segment_id empty and the date will remain unresolved. Use inferred only for a strong
implication with facets.inference_basis and confidence at most 0.7.

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
