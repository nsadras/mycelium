"""Production prompts for extraction, routing, and reconsolidation."""


def subject_node_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Build a complete typed census of unresolved subjects in one source-grounded memory cohort.

This call declares nodes only. Do not decide identity matches, page admission, claim ownership, relationships, or
participant resolution. The registry's `you` identity is reserved and must not appear as a node. Include distinct
real subjects needed as stable identity or relationship endpoints, including meaningful components, occurrences,
people, and artifacts. Do not create a node for every noun or mentioned object: a person's attributes and practices,
and contextual inputs or descriptive content, can remain in the claim without becoming graph identities. Merge
repeated mentions of the same subject within the cohort and combine their cited evidence.
When the registry contains a provisional identity and the supplied evidence adds personal history, state, plans, or
relationships about it, declare a candidate node for that subject again. Identity resolution will match it back to
the stable ID so admission can reconsider whether its page is now mature; do not omit it merely because it is already
known provisionally.

Use this ontology exactly:
- Person is a human.
- Organization is a group.
- Project is an intentional continuing effort toward an outcome.
- Series is an explicitly organized recurring frame whose recurrence has its own identity, state, plans, or history.
  A person's recurring practice or occupation is an attribute of that Person, not a Series.
- Event is one bounded occurrence, including a particular session or appointment.
- Artifact is a made physical or digital object, including a document, tool, product, model, or deliverable.
- Topic is an abstract subject, field, idea, question, or body of knowledge. It is not a fallback for a component,
  service, feature, issue, artifact, event, or unknown subject.
- Place is a physical or geographic location, never a temporal expression.

A workstream, feature, milestone, issue, tool, or deliverable inside a larger effort may need a node so its
relationship can be stated later, but local goals, deadlines, participants, or complexity do not by themselves make
it an independent Project. Represent both a continuing effort and its bounded occurrences when the evidence supports
both. Repeated or plural activities organized around a shared purpose or stated future continuation can establish a
descriptively named Project or Series even when the speaker has not given the effort a proper name; do not collapse
that continuing container into its next scheduled occurrence. Prefer Project for an effort working toward an outcome
and Series when the recurring frame itself is the subject. Do not infer a Series merely from plural wording, an
occupation, a habitual background activity, or inputs that a proposed system will process. A Series requires
source-grounded plans, state, or history about tracking the recurrence itself. When someone proposes building a
tool, workspace, archive, or system for a recurring activity, the continuing build effort is a Project candidate;
the background activity remains context unless it has separate accumulating memory. A particular occurrence remains
separate from its Project or Series. Do not create a Topic merely to restate what a Project or Event concerns. Use
N001-style IDs and cite only supplied evidence aliases. Return JSON matching the schema."""
    user = f"""ENTITY REGISTRY CONTEXT:
{index_content}

SOURCE-GROUNDED NODE EVIDENCE:
{evidence}"""
    return system, user


def entity_plan_prompt(
    registry: str,
    nodes: str,
    evidence: str,
) -> tuple[str, str]:
    system = """Resolve a fixed subject census into one coherent memory-entity plan.

For every supplied node, decide identity, optional containment, and page state together. This call cannot create,
remove, or retype nodes. Cite the supplied evidence in your reasoning and use only exact node or registry IDs.

Identity:
- Copy an existing same-type ID only when the evidence affirmatively shows the same continuing subject through a
  stable name, explicit rename or alias, or defining history. Shared work, type, vocabulary, participants, or being
  the only registry option is not identity evidence.
- A Person may resolve to `you` only when source structure or evidence identifies that person as the configured user.
  A different named person never resolves to `you`.
- Otherwise leave entity_id empty. preferred_title and aliases must remain source-grounded.

Containment:
- Use `component_of` for a dependent part of a Project or Series and `occurrence_of` for one bounded Event within a
  Project or Series. Set parent_entity to the exact parent. Each node has at most one parent.
- Require affirmative parent evidence. Related domain, organization, people, timing, or an available registry option
  is not containment. A separately named effort remains separate unless evidence places it inside a parent.
- With no supported parent, use containment=`none` and an empty parent_entity.

Page state:
- `materialized` means this independent subject already has useful personal state, decisions, plans, relationships,
  or history that should accumulate on its own page, and the evidence establishes continuation through distinct
  episodes or explicit prior history plus current or future continuation.
- `provisional` means a plausible independent subject is known but current evidence is thin, emerging, or only a
  stated wish or proposal. Detailed desired requirements do not prove that work has begun.
- `no_page` means memory belongs to a parent or the node is only context, an attribute, an incidental object, or one
  bounded occurrence without independent history. Components always use no_page.
- A Series is independent only when evidence treats recurrence as a shared frame with its own evolving state, plans,
  decisions, or history. A person's occupation, habit, hobby, or repeated background activity is not itself a Series.
- Existing materialized identities remain usable even when this cohort is thin; do not treat page_state as a request
  to erase prior memory.

Resolve every supplied participant exactly once to `you`, an existing Person ID, or a declared Person node. Return
JSON matching the schema."""
    user = f"""EXISTING ENTITY PROFILES:
{registry}

FIXED SUBJECT CENSUS:
{nodes}

SOURCE-GROUNDED EVIDENCE:
{evidence}"""
    return system, user


def claim_routing_prompt(registry: str, entity_plan: str, evidence: str) -> tuple[str, str]:
    system = """Route every supplied claim using the completed entity plan.

Make owner, relationship, and section decisions together so they form one coherent interpretation. Use only exact
stable entity IDs and declared section keys. If no materialized or provisionally reusable identity can reliably own
a claim, leave owner_entity and section empty; do not invent an identity.

The owner is the identity whose lasting state, plans, requirements, responsibilities, relationships, or history the
claim changes. `you` is not a catchall. Once a Project exists, its purpose, scope, requirements, decisions, status,
deadlines, work products, and next steps belong to the Project even when phrased as “I want,” “I prefer,” or “I
require.” A named person's own responsibility, commitment, completion, view, or personal history belongs to that
Person. Context does not determine ownership by itself.

Resolve explicit subject and object endpoints plus useful context endpoints. `project_role` means the claim explicitly
assigns a continuing responsibility or accountable role to a Person/You within one Project; ordinary participation,
one completed task, or topical context is `other` or `none`. Do not add endpoints merely because they appear nearby.

Choose the section by the claim's meaning and current temporal role, not its source kind. For people, use profile for
stable identity, current_context for present circumstances, interests_views for views, goals_plans for intentions,
shared_projects for continuing project roles, timeline for completed events, and needs_review for unresolved claims.
For Projects and Artifacts, use overview for identity and purpose, objective for intended outcomes, current_status for
present condition, requirements_constraints for operating boundaries, decisions for chosen direction,
next_steps_deadlines for future work, people_organizations for roles, timeline for completed events,
research_references for supporting findings, and needs_review for unresolved claims. Use the analogous declared
headings for other page types. Return every claim exactly once and JSON matching the schema."""
    user = f"""ENTITY REGISTRY AND ALLOWED SECTIONS:
{registry}

RESOLVED ENTITY PLAN:
{entity_plan}

SOURCE-GROUNDED CLAIMS:
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
speaker, confidence, optional replaceable-state slot, and open facets. Evidence modality describes
the observation channel, never whether a claim is inferred: use speech for spoken or written
conversation, visual for visible evidence, tool for tool observations, and mixed only when multiple
channels directly support one claim. Put exact time wording in
facets.when for event times and facets.deadline for due dates. Never convert relative time yourself;
preserve phrases such as “by Friday” or “in three days” exactly so the deterministic resolver can anchor
them to their evidence time. When timestamped segments are supplied, a claim with relative time must copy the
one cited segment ID containing that time expression into temporal_anchor_segment_id. Otherwise leave
temporal_anchor_segment_id empty and the date will remain unresolved. Set evidence_type=explicit for
every directly stated claim. Set evidence_type=inferred for a claim that is not directly stated but
follows with high certainty from the cited evidence; every such claim must include
facets.inference_basis and confidence at most 0.7. Do not label a derived conclusion explicit merely
because its premises are explicit.

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
