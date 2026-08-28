"""Production prompts for extraction, routing, and reconsolidation."""


def entity_discovery_prompt(index_content: str, evidence: str) -> tuple[str, str]:
    system = """Discover durable semantic entities that deserve their own wiki pages.

This is entity discovery, not claim placement. Return only genuinely new entities absent from the
registry. Projects are named outcomes or continuing endeavors with commitment or multiple
supporting claims; they do not require a brand name. Examples include opening a dance studio or building
an online clothing store. People need a durable relationship or recurring substantive relevance. Topics
are abstract subjects and need intentional ongoing research or two non-equivalent claims. A recurring
Series groups related occurrences. Artifacts are made objects such as documents, tools, products, and
deliverables. Organizations and places need lasting relevance. Events must be named, substantial, and
consequential. Do not create pages for incidental
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
- Project is an intentional effort toward an outcome whose plans, work, decisions, or status continue over time.
- Series is a recurring frame that groups related occurrences. It is not one occurrence. If recurring work is
  organized around a continuing outcome, use Project for the effort and Event for each occurrence; use Series when
  the recurrence itself is the lasting subject without a Project outcome.
- Event is one bounded occurrence. A session or appointment is an Event even when it belongs to a Project or Series.
- Artifact is a made physical or digital object, including a document, tool, product, model, or deliverable.
- Topic is an abstract subject, field, idea, question, or body of knowledge. Do not use Topic as a fallback for an
  Artifact, Project component, service, feature, issue, or unknown subject.
- Place is a physical or geographic location only. Never create nodes for temporal expressions.

Whenever the evidence identifies a particular occurrence by its time, place, participants, outcome, or record,
represent that occurrence as an Event distinct from its Project or Series. Do not create a Topic merely to restate
what a Project or Event concerns; the evidence must identify the Topic as a distinct subject of memory.
An Event never contains multiple occurrences. Evidence about a repeated practice, multiple sessions, or both a
current practice and a next occurrence requires a separate Project or Series frame even when that frame has no
proper name.

Define every subject once with an N001-style ID. Edge direction is always source then target:
- dependent component -> `component_of` -> parent Project or Series;
- Event -> `occurrence_of` -> parent Project or Series;
- Person, Organization, or `you` -> `participant_in` -> Project, Series, or Event;
- Project, Series, Event, or Artifact -> `about` -> abstract Topic;
- located subject -> `located_at` -> physical Place;
- activity or Agent -> `uses` -> Artifact;
- Artifact -> `produced_by` -> producing activity.
Use `related_to` only when none of the more precise relations applies. A tool used by a Project is not automatically
part of that Project. Every edge endpoint must be a declared node or
an exact stable ID copied from the supplied registry. Use a stable registry endpoint when the subject is already
unambiguous; do not duplicate that known subject as a new node. Use an N001-style node only when identity still
needs resolution. Never place an N-style ID in an edge unless that exact ID is present in the returned nodes array;
omit an unsupported edge rather than inventing an endpoint. Before returning, verify every edge endpoint against
the nodes array and supplied registry. Cite only supplied C001-style claims or
P001-style participants. Resolve every supplied participant exactly once to `you`, an exact existing Person ID, or
a declared Person node. Cite evidence but do not add explanatory prose to nodes or edges. Do not decide whether a
node deserves a page."""
    user = f"""ENTITY REGISTRY CONTEXT:
{index_content}

SOURCE-GROUNDED GRAPH EVIDENCE:
{evidence}"""
    return system, user


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


def subject_relationship_prompt(
    index_content: str,
    nodes: str,
    evidence: str,
) -> tuple[str, str]:
    system = """Build one simple containment hierarchy for an already-declared subject census and resolve source participants.

This call cannot create, rename, retype, or omit nodes. Every edge endpoint must be copied exactly from the supplied
node census or stable registry. Use stable registry endpoints for already-known parents. Return no edge when the
evidence does not support containment.

Edge direction is always source then target:
- dependent component -> `component_of` -> parent Project or Series;
- Event -> `occurrence_of` -> parent Project or Series;

Each declared node can have at most one parent. Do not emit participation, topical, location, tool-use, production,
or generic relatedness edges; later claim-level decisions handle those relationships. A phase, pilot, workstream,
feature, issue, build, deliverable, or bounded activity is a component when the evidence places it inside a larger
continuing effort. A particular interview, meeting, appointment, or other bounded occurrence is an occurrence when
the evidence places it inside a continuing Project or Series. Consider every Event and workstream-like node before
returning so supported containment is not left implicit. Require affirmative parent evidence: the source must name,
possessively identify, or unambiguously continue the parent. Shared type, vocabulary, organization, participants,
domain, timing, or being the only available Project endpoint is not containment evidence. A separately named effort
remains separate unless the source places it inside the parent. A tool merely used by a Project is not its component.

Resolve every supplied participant exactly once to `you`, an exact existing Person ID, or a declared Person node.
Cite only supplied evidence aliases and return JSON matching the schema."""
    user = f"""ENTITY REGISTRY:
{index_content}

DECLARED SUBJECT NODES:
{nodes}

SOURCE-GROUNDED RELATIONSHIP EVIDENCE:
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
    system = """Classify every resolved subject-graph node for personal-memory admission.

Judge three independent questions. `scope_role` says where the subject's memory belongs: `independent` means it can
hold useful personal history separately; `component` means its relevant state and history belong to a parent Project
or Series; `context_only` means it only helps explain this evidence and should not own memory. A graph relation alone
does not make a subject a component. The supplied node type and title are model proposals, not proof of scope or
maturity. Judge from the cited source evidence and the meaning of supported relations.

`memory_evidence` says how much source-grounded evidence supports accumulating personal memory: `accumulating`
means the supplied evidence already shows useful state, decisions, plans, relationship, or history that can grow over
time; `thin` means the subject is real but the supplied personal evidence is only a small or one-off detail; `unclear`
means the evidence does not support a reliable judgment. This is not a judgment of whether the subject itself is
real, stable, famous, named, recurring, or important in the wider world. Those facts alone never establish
accumulating personal memory. A person's occupation, habit, or recurring practice remains part of that person's
profile unless the evidence separately establishes plans, state, or history for an organized recurring frame. For a
Series, one statement that a person repeatedly performs an activity is thin or contextual; accumulating evidence must
organize occurrences as a continuing collection or give that recurring frame its own evolving state or plans.

`evidence_maturity` says whether the supplied evidence is sufficient to establish a lasting subject. `established`
requires support across distinct source episodes, explicit evidence of meaningful prior history, or an unambiguous
account of a continuing effort already underway together with another occurrence or next step. A stated wish,
proposal, or plan to begin an effort is still `emerging` until later evidence shows continuity. Several claims
extracted from one source do not by themselves establish maturity, but one source can do so when it explicitly
establishes both ongoing personal history and continuation. Maturity is not identity confidence and is not the same
as whether the real-world subject is stable.

A component may have accumulating information, but that information accumulates on its parent rather than a new
page. When evidence places a subject inside a larger Project or Series, classify it as a component even if the graph
omitted a supported containment edge. This includes phases, pilots, workstreams, features, issues, builds, and
deliverables described as part of a larger effort. Their own local goals, dates, or status do not establish an
independent page. An Event that is one occurrence remains distinct from its Project or Series as an identity, but its
memory normally belongs to that parent. An unnamed or merely upcoming occurrence is not an independent lasting
subject just because its date or status changes. A routine appointment, incidental
Place, mentioned Organization, or merely used Artifact is normally context-only or thin unless the evidence itself
shows independent personal history. Classify every supplied node exactly once. Do not change identities, infer from
general-world knowledge, or assign claim ownership."""
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
    system = """Verify one proposed existing-identity match.

Decide only whether the candidate and existing identity are the same continuing real subject. A shared entity type,
shared Project, related work, containment, participation, or being the only registry option is not evidence of
sameness. Require affirmative continuity: an explicit rename or alias, the same stable name, or source-grounded
defining details that unambiguously continue the existing subject's recorded history. A generic role or phrase such
as a pilot, interview, integration, build, or upcoming event does not become the larger Project merely because it
occurs within that Project. Different people, projects, organizations, topics, places, or events remain different
even when they are closely related.

Use the existing identity's supplied grounded profile as evidence, not general-world assumptions. The singleton
`you` identity can match a Person candidate only when the source evidence itself identifies that candidate as the
configured user; a different named person must never match `you`. When affirmative continuity is absent or the
evidence supports a distinct subject, return same_identity=false. Return the supplied candidate exactly once and
JSON matching the schema."""
    user = f"""PROPOSED IDENTITY MATCHES:
{matches}

SOURCE-GROUNDED EVIDENCE:
{evidence}"""
    return system, user


def series_subjecthood_prompt(candidate: str, evidence: str) -> tuple[str, str]:
    system = """Verify whether one proposed Series is a distinct recurring memory subject.

Use only cited source evidence. `independent_recurring_frame` requires the source to organize occurrences as a
continuing collection or give that frame its own shared plans, state, decisions, or history. Prior occurrences plus
a shared record or a plan for the next occurrence is sufficient; no formal organization or proper name is required.
Do not infer a shared frame from plural wording or from a person merely saying they repeatedly do their occupation,
hobby, habit, or background activity. `personal_attribute_or_context` means the evidence only says what a person
does or supplies context for another effort. A need for a tool that processes outputs of an activity is state of the
tool effort, not proof that the activity is an organized Series. The proposed title and type are hypotheses, not
evidence. Return JSON matching the schema."""
    user = f"""PROPOSED SERIES:
{candidate}

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

Distinguish a person's general preference or personal state from a choice, requirement, or goal scoped to one
endeavor. First-person wording does not make the person the owner: an intent that establishes a specific continuing
effort, and constraints or technology choices for that effort, change the Project once its identity exists. A true
personal preference applies to the person's own life or working style beyond merely defining one Project. Keep a
named person's assignment, responsibility, commitment, or completion as part of that Person's own role and history,
with the Project as context; do not transfer personal accountability to the Project merely because the work benefits
it. By contrast, an impersonal requirement, collective choice, capability, or deadline of the effort belongs to the
Project.

Once a Project identity exists, use it for the effort's purpose, scope boundary, operating requirement, project
preference, and next step even when the sentence uses “I want,” “I prefer,” or “I require,” or names `you` as the
actor. The `you` page is not a catch-all for first-person project work. Keep `you` for a durable personal profile,
general working style, or an explicit personal role or responsibility in the Project. A completed issue, feature, or
other routine project-state change performed by `you` belongs to the Project; a named non-user person's assignment,
commitment, or completed responsibility remains on that Person as described above.
A statement that two efforts must remain separate defines the scope boundary of the continuing effort it describes,
even when the speaker expresses that boundary as a personal preference.

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
relationship_kind is `project_role` only when a Person or `you` has an explicit role, assignment, responsibility,
or ongoing accountability in exactly one Project; use `other` for another explicit durable relationship and
`none` when the claim is not relational.
When the fixed owner is a Person or `you`, exactly one Project is contextual, and the claim says that person owns,
leads, is assigned, or will be responsible for work in that Project, classify it as `project_role`. A specific task
completion, status update, or one-off delivery is not by itself a continuing role; use `other` or `none` unless the
sentence also explicitly restates ongoing responsibility. Reserve `other` for relationships such as family,
acquaintance, membership without an accountable role, or another non-project relation.

The registry's `you` ID is the configured user's stable identity. When a claim explicitly relates multiple
registry identities, resolve every named participant: use object_entities for a non-owner relationship participant
and contextual_entities for the setting in which a relation or action occurs. For relationship_kind=project_role,
the Person or `you` is the fixed owner and subject, and exactly one Project must be contextual. Do not change the
supplied owner, add entities merely because they occur in the same cohort, or infer an endpoint without evidence.
Leave roles empty when the claim does not establish a stable endpoint. Return every claim alias exactly once and
JSON matching the schema."""
    user = f"""COMPLETED ENTITY REGISTRY:
{index_content}

OWNED SOURCE-GROUNDED CLAIMS:
{evidence}"""
    return system, user


def claim_section_prompt(evidence: str) -> tuple[str, str]:
    system = """Choose the single best human-facing wiki section for every already-owned claim.

The owner is fixed and every claim lists its exact allowed sections. Classify what the claim contributes to that
owner's page rather than relying only on its broad claim type, grammar, source kind, or evidence modality.

For Projects and Artifacts: overview states identity and purpose; objective states intended outcomes and success
measures; current status states present capabilities, readiness, or condition; requirements and constraints state
conditions that must hold; decisions state settled choices; next steps and deadlines state future action or current
target dates; timeline records dated past changes and superseded earlier states; research and references records
external findings, evaluated alternatives, and benchmark evidence; people and organizations records participation.
When a decision establishes an ongoing condition that the system or effort must satisfy—such as a release gate,
privacy rule, or required operating behavior—use requirements and constraints rather than decisions. Reserve
decisions for the choice itself when its continuing constraint is not the main information.
For a Person, an ongoing responsibility or role in a continuing effort belongs under shared projects, a future
personal aim under goals and plans, and completed dated work under timeline. For Events, distinguish date and
location, participants, what happened, outcomes, follow-ups, and supporting evidence by their meaning.

Keep a person's role in a named or clearly identified Project under shared projects. Tool-derived evidence is not
automatically research: a calendar item can describe a date, and an issue tracker can describe project status or
history. Use needs_review only when the claim itself is an unresolved alternative or uncertainty, not merely because
semantic classification is difficult. Do not change ownership, merge claims, or rewrite their meaning. Return every
supplied claim alias exactly once and JSON matching the schema."""
    return system, f"FIXED OWNERS AND SOURCE-GROUNDED CLAIMS:\n{evidence}"


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
