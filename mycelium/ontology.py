"""Authoritative entity, claim, and wiki-section ontology."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CLAIM_TYPES = (
    "identity",
    "state",
    "event",
    "preference",
    "plan",
    "belief",
    "relationship",
    "decision",
    "commitment",
    "interaction",
    "observation",
    "unknown",
)
ClaimType = Literal.__getitem__(CLAIM_TYPES)


@dataclass(frozen=True)
class SectionDefinition:
    key: str
    title: str
    description: str


@dataclass(frozen=True)
class EntityTypeDefinition:
    key: str
    label: str
    plural_label: str
    description: str
    sections: tuple[SectionDefinition, ...]
    default_sections: tuple[tuple[str, str], ...]
    project_role_section: str | None = None
    discoverable: bool = True

    def section_keys(self) -> tuple[str, ...]:
        return tuple(section.key for section in self.sections)

    def section_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple((section.key, section.title) for section in self.sections)

    def defaults(self) -> dict[str, str]:
        return dict(self.default_sections)


@dataclass(frozen=True)
class SubjectScopeDefinition:
    """One representation scope available after identity and type are fixed."""

    key: str
    description: str
    persisted_scope: str
    page_state: str


# These policies live beside the entity ontology so extraction, census, planning,
# and routing share one authority for what enters the subject graph.
SUBJECT_CENSUS_POLICY = """Build a complete list of the distinct subjects represented by the supplied candidate mentions.

A stored claim is a source-supported memory assertion. A subject candidate is a person, organization, continuing
effort, recurring series, meaningful artifact, abstract topic, place, or bounded event named by extraction. A subject
node groups candidate mentions that refer to one real-world subject within this batch. The registry lists identities
already stored, but matching nodes to those identities happens later.

The input uses short aliases so the output can cite exact records: C... identifies a stored claim, P... identifies a
source-declared participant, and N... identifies a subject node created in this step. `you` is the reserved identity
for the configured user.

Use the candidate list as the boundary of this task:
1. Examine every candidate. Create one N001-style node for each distinct subject and merge repeated mentions only when
   the evidence shows that they refer to the same subject.
2. Include every candidate marked `subject`, `owner`, or `source_participant`, except the reserved user identity `you`.
   Include a `participant` candidate when a claim uses that person as a relationship or interaction endpoint.
3. Use a supplied candidate name as the title. Cite every C... claim alias and P... participant alias that directly
   supports the node. For a named human source participant, include its P... alias in both evidence lists.

Attributes, preferences, quantities, reasons, and other descriptive details remain information about a subject rather
than separate nodes. A date, time, duration, deadline, or age is not a subject by itself. Do not choose identity,
ontology type, containment, or page visibility here. Return schema-valid JSON; use an empty node list only when the
candidate list contains no representable subject."""

EXTRACTION_SUBJECT_POLICY = """The `about` list is the complete set of named identities needed by later identity
resolution and routing. Use `subject` for the primary person or identity whose action or state the sentence directly
asserts. Use `owner` for a different durable identity when the proposition asserts that identity's own operations,
requirements, plans, decisions, status, or history, even when a person performs the action. Use `participant` for
another named relationship endpoint. A claim may have both a subject and an owner. Work that operates or changes a
named Organization or Project belongs to that identity as owner. A personal commitment to visit, join, help, or
volunteer with another identity belongs to the person; the other identity is a participant. Include every explicitly
named durable identity in `about`."""

ROUTING_SUBJECT_POLICY = """For a general route, `subject_entity` is the identity grammatically described by the claim,
`object_entities` are explicit relationship endpoints, and `contextual_entities` are useful secondary endpoints.
Nearby or incidental identities are not endpoints."""

ROUTING_OWNERSHIP_POLICY = """Every materialized identity type can own claims about its own durable record. Choose the
identity whose record would be incomplete without the claim. An Organization owns its operations, policies, decisions,
offerings, obligations, and history. A Project owns its purpose, scope, requirements, decisions, status, deadlines,
work products, and next steps. A Person owns that person's commitments, actions, views, relationships, and personal
history. A person speaking about or acting within another identity does not by itself make the person the owner. Keep
other explicitly involved identities as relationship or context endpoints."""

FACT_EVIDENCE_POLICY = """Use the claim sentence, cited evidence, and structured temporal record as truth-bearing
content. A resolved temporal start or end may be rendered as its absolute date. Linked entities and the linked
registry are navigation context; their presence alone does not assert involvement or require mention in the display
sentence. An unresolved temporal status means that a relative expression has not been mapped to an absolute calendar
interval; the expression itself remains supported exactly as stated."""

SUBJECT_SCOPE_ONTOLOGY: tuple[SubjectScopeDefinition, ...] = (
    SubjectScopeDefinition(
        "materialized",
        """is an independent subject with useful memory continuity. It has no parent. Use it only when the
  supplied evidence spans multiple source episodes or explicitly describes prior history plus present or future
  continuation, or when the schema permits `direct_encounter` for a Person structurally identified as a named source
  participant. State the allowed continuity_basis. The age, era, or background history of an object is not history of
  an effort concerning it. Multiple details, requirements, decisions, or work items inside one episode do not
  establish memory continuity.""",
        "independent",
        "materialized",
    ),
    SubjectScopeDefinition(
        "provisional",
        "is a plausible independent subject whose continuity is not established yet. It has no parent.",
        "independent",
        "provisional",
    ),
    SubjectScopeDefinition(
        "component",
        """is a dependent non-Event part of exactly one Project or Series. It has an exact parent and always uses
  no page.""",
        "component",
        "no_page",
    ),
    SubjectScopeDefinition(
        "occurrence",
        """is one bounded Event within exactly one Project or Series. It has an exact parent and always uses
  no page.""",
        "occurrence",
        "no_page",
    ),
    SubjectScopeDefinition(
        "standalone_event",
        "is a bounded Event with no supported Project or Series parent. It has no page and no parent.",
        "standalone_event",
        "no_page",
    ),
    SubjectScopeDefinition(
        "context",
        "is an incidental non-event subject, attribute, or object with no independent page and no parent.",
        "context",
        "no_page",
    ),
)
SUBJECT_SCOPES = tuple(definition.key for definition in SUBJECT_SCOPE_ONTOLOGY)
SUBJECT_SCOPES_BY_KEY = {
    definition.key: definition for definition in SUBJECT_SCOPE_ONTOLOGY
}
SUBJECT_PERSISTED_SCOPES = tuple(dict.fromkeys(
    definition.persisted_scope for definition in SUBJECT_SCOPE_ONTOLOGY
))
SUBJECT_PAGE_STATES = tuple(dict.fromkeys(
    definition.page_state for definition in SUBJECT_SCOPE_ONTOLOGY
))
INDEPENDENT_SUBJECT_SCOPES = tuple(
    definition.key
    for definition in SUBJECT_SCOPE_ONTOLOGY
    if definition.persisted_scope == "independent"
)

SUBJECT_SCOPE_CONTAINMENT_POLICY = """- Require affirmative parent evidence. Related domain, organization, people, timing, or an available registry option
  is not containment. A separately named effort remains separate unless evidence places it inside a parent."""

SUBJECT_PAGE_STATE_POLICY = """Page state:
- Scope directly determines page state: materialized creates a page, provisional preserves an identity without a
  page, and component, occurrence, standalone_event, and context have no page.
- A Series is independent only when evidence treats recurrence as a shared frame with its own evolving state, plans,
  decisions, or history. A person's occupation, habit, hobby, or repeated background activity is not itself a Series.
- Existing materialized identities remain usable even when this cohort is thin; do not treat scope as a request
  to erase prior memory."""


def _section(key: str, title: str, description: str) -> SectionDefinition:
    return SectionDefinition(key, title, description)


ENTITY_ONTOLOGY: tuple[EntityTypeDefinition, ...] = (
    EntityTypeDefinition(
        "you",
        "You",
        "You",
        "The configured user whose personal context and preferences the memory serves.",
        (
            _section("profile", "Profile", "stable identity and background"),
            _section(
                "current_context",
                "Current Context",
                "present circumstances and active context",
            ),
            _section(
                "priorities_plans",
                "Priorities & Plans",
                "goals, decisions, commitments, and future work",
            ),
            _section(
                "preferences_working_style",
                "Preferences & Working Style",
                "preferences, beliefs, and working style",
            ),
            _section(
                "important_relationships",
                "Important Relationships",
                "durable relationships and interactions",
            ),
            _section(
                "memory_map",
                "Memory Map",
                "orientation links to important memory areas",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "profile"),
            ("state", "current_context"),
            ("preference", "preferences_working_style"),
            ("belief", "preferences_working_style"),
            ("plan", "priorities_plans"),
            ("commitment", "priorities_plans"),
            ("decision", "priorities_plans"),
            ("relationship", "important_relationships"),
            ("event", "current_context"),
            ("interaction", "important_relationships"),
            ("observation", "current_context"),
            ("unknown", "current_context"),
        ),
        project_role_section="priorities_plans",
        discoverable=False,
    ),
    EntityTypeDefinition(
        "project",
        "Project",
        "Projects",
        "An intentional continuing effort toward an outcome.",
        (
            _section("overview", "Overview", "identity, scope, and purpose"),
            _section("objective", "Objective", "intended outcomes"),
            _section(
                "current_status", "Current Status", "present condition and progress"
            ),
            _section(
                "requirements_constraints",
                "Requirements & Constraints",
                "requirements, constraints, preferences, desired properties, and operating boundaries",
            ),
            _section(
                "decisions", "Decisions", "chosen directions and resolved choices"
            ),
            _section(
                "next_steps_deadlines",
                "Next Steps & Deadlines",
                "future work, scheduled future events, commitments, and deadlines",
            ),
            _section(
                "people_organizations",
                "People & Organizations",
                "continuing roles and involved organizations",
            ),
            _section(
                "timeline",
                "Timeline",
                "completed events and historical changes, excluding current preferences and future work",
            ),
            _section(
                "research_references",
                "Research & References",
                "supporting external findings and references",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "overview"),
            ("state", "current_status"),
            ("preference", "requirements_constraints"),
            ("belief", "requirements_constraints"),
            ("plan", "next_steps_deadlines"),
            ("commitment", "next_steps_deadlines"),
            ("decision", "decisions"),
            ("relationship", "people_organizations"),
            ("event", "timeline"),
            ("interaction", "timeline"),
            ("observation", "overview"),
            ("unknown", "overview"),
        ),
        project_role_section="people_organizations",
    ),
    EntityTypeDefinition(
        "series",
        "Series",
        "Series",
        "An explicitly organized recurring frame with its own identity, state, plans, or history.",
        (
            _section("overview", "Overview", "identity, purpose, and scope"),
            _section(
                "schedule_pattern",
                "Schedule & Pattern",
                "recurrence, schedule, and planned cadence",
            ),
            _section(
                "current_context",
                "Current Context",
                "present state and active decisions",
            ),
            _section(
                "participants", "Participants", "continuing participant relationships"
            ),
            _section(
                "occurrences", "Occurrences", "individual occurrences and interactions"
            ),
            _section(
                "related_topics", "Related Topics", "related subjects and context"
            ),
            _section(
                "research_references",
                "Research & References",
                "supporting external findings and references",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "overview"),
            ("state", "current_context"),
            ("preference", "current_context"),
            ("belief", "current_context"),
            ("plan", "schedule_pattern"),
            ("commitment", "schedule_pattern"),
            ("decision", "current_context"),
            ("relationship", "participants"),
            ("event", "occurrences"),
            ("interaction", "occurrences"),
            ("observation", "overview"),
            ("unknown", "overview"),
        ),
    ),
    EntityTypeDefinition(
        "person",
        "Person",
        "People",
        "A human other than the configured user.",
        (
            _section(
                "relationship_to_you",
                "Relationship to You",
                "the person's relationship to the user",
            ),
            _section("profile", "Profile", "stable identity and background"),
            _section(
                "current_context",
                "Current Context",
                "present circumstances and active state",
            ),
            _section(
                "interests_views",
                "Interests & Views",
                "preferences, beliefs, and viewpoints",
            ),
            _section(
                "goals_plans",
                "Goals & Plans",
                "the person's personal intentions, decisions, and commitments outside continuing project roles",
            ),
            _section(
                "shared_projects",
                "Shared Projects",
                "continuing responsibilities, commitments, and roles within shared projects",
            ),
            _section(
                "timeline", "Timeline", "completed events and interaction history"
            ),
            _section(
                "research_references",
                "Research & References",
                "supporting external findings and references",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "profile"),
            ("state", "current_context"),
            ("preference", "interests_views"),
            ("belief", "interests_views"),
            ("plan", "goals_plans"),
            ("commitment", "goals_plans"),
            ("decision", "goals_plans"),
            ("relationship", "relationship_to_you"),
            ("event", "timeline"),
            ("interaction", "timeline"),
            ("observation", "current_context"),
            ("unknown", "current_context"),
        ),
        project_role_section="shared_projects",
    ),
    EntityTypeDefinition(
        "artifact",
        "Artifact",
        "Artifacts",
        "A made physical or digital object, including a document, tool, product, model, or deliverable.",
        (
            _section("overview", "Overview", "identity and high-level description"),
            _section("purpose", "Purpose", "intended use and outcomes"),
            _section(
                "current_state",
                "Current State",
                "present condition, plans, and commitments",
            ),
            _section(
                "requirements_constraints",
                "Requirements & Constraints",
                "requirements, preferences, and operating boundaries",
            ),
            _section(
                "decisions", "Decisions", "chosen directions and resolved choices"
            ),
            _section(
                "related_projects",
                "Related Projects",
                "relationships to projects and other owners",
            ),
            _section("timeline", "Timeline", "completed events and change history"),
            _section(
                "research_references",
                "Research & References",
                "supporting external findings and references",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "overview"),
            ("state", "current_state"),
            ("preference", "requirements_constraints"),
            ("belief", "requirements_constraints"),
            ("plan", "current_state"),
            ("commitment", "current_state"),
            ("decision", "decisions"),
            ("relationship", "related_projects"),
            ("event", "timeline"),
            ("interaction", "timeline"),
            ("observation", "overview"),
            ("unknown", "overview"),
        ),
    ),
    EntityTypeDefinition(
        "topic",
        "Topic",
        "Topics",
        "An abstract subject, field, idea, question, or body of knowledge.",
        (
            _section(
                "why_it_matters",
                "Why It Matters",
                "relevance, purpose, and intended use",
            ),
            _section(
                "current_understanding",
                "Current Understanding",
                "current state, decisions, and understanding",
            ),
            _section(
                "preferences_positions",
                "Preferences & Positions",
                "preferences, beliefs, and positions",
            ),
            _section(
                "related_projects",
                "Related Projects",
                "relationships to active projects",
            ),
            _section("timeline", "Timeline", "events and evolution over time"),
            _section(
                "research_references",
                "Research & References",
                "supporting external findings and references",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "why_it_matters"),
            ("state", "current_understanding"),
            ("preference", "preferences_positions"),
            ("belief", "preferences_positions"),
            ("plan", "why_it_matters"),
            ("commitment", "why_it_matters"),
            ("decision", "current_understanding"),
            ("relationship", "related_projects"),
            ("event", "timeline"),
            ("interaction", "timeline"),
            ("observation", "current_understanding"),
            ("unknown", "current_understanding"),
        ),
    ),
    EntityTypeDefinition(
        "organization",
        "Organization",
        "Organizations",
        "A durable group or institution.",
        (
            _section("overview", "Overview", "identity and high-level description"),
            _section(
                "relationship_to_you",
                "Relationship to You",
                "the organization's relationship to the user",
            ),
            _section("people", "People", "people and roles in the organization"),
            _section(
                "related_projects", "Related Projects", "relationships to projects"
            ),
            _section(
                "current_context",
                "Current Context",
                "present state, plans, decisions, and commitments",
            ),
            _section("timeline", "Timeline", "events and interaction history"),
            _section(
                "research_references",
                "Research & References",
                "supporting external findings and references",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "overview"),
            ("state", "current_context"),
            ("preference", "current_context"),
            ("belief", "current_context"),
            ("plan", "current_context"),
            ("commitment", "current_context"),
            ("decision", "current_context"),
            ("relationship", "relationship_to_you"),
            ("event", "timeline"),
            ("interaction", "timeline"),
            ("observation", "current_context"),
            ("unknown", "current_context"),
        ),
    ),
    EntityTypeDefinition(
        "place",
        "Place",
        "Places",
        "A physical or geographic location, never a temporal expression.",
        (
            _section("overview", "Overview", "identity and high-level description"),
            _section(
                "why_it_matters",
                "Why It Matters",
                "relevance, preferences, and beliefs",
            ),
            _section(
                "current_context",
                "Current Context",
                "present state, plans, decisions, and commitments",
            ),
            _section(
                "associated_people_projects",
                "Associated People & Projects",
                "relationships to people and projects",
            ),
            _section(
                "visits_events", "Visits & Events", "visits, events, and interactions"
            ),
            _section(
                "research_references",
                "Research & References",
                "supporting external findings and references",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "overview"),
            ("state", "current_context"),
            ("preference", "why_it_matters"),
            ("belief", "why_it_matters"),
            ("plan", "current_context"),
            ("commitment", "current_context"),
            ("decision", "current_context"),
            ("relationship", "associated_people_projects"),
            ("event", "visits_events"),
            ("interaction", "visits_events"),
            ("observation", "current_context"),
            ("unknown", "current_context"),
        ),
    ),
    EntityTypeDefinition(
        "event",
        "Event",
        "Events",
        "One bounded occurrence, including a particular session or appointment.",
        (
            _section("summary", "Summary", "identity and concise overview"),
            _section("date_location", "Date & Location", "time and location"),
            _section(
                "participants", "Participants", "people and organizations involved"
            ),
            _section(
                "what_happened", "What Happened", "states, events, and interactions"
            ),
            _section(
                "outcomes_decisions", "Outcomes & Decisions", "decisions and outcomes"
            ),
            _section("follow_ups", "Follow-ups", "plans, commitments, and next steps"),
            _section(
                "evidence",
                "Evidence",
                "observations, preferences, beliefs, and external findings",
            ),
            _section(
                "needs_review",
                "Needs Review",
                "unresolved or ambiguous memory requiring review",
            ),
        ),
        (
            ("identity", "summary"),
            ("state", "what_happened"),
            ("preference", "evidence"),
            ("belief", "evidence"),
            ("plan", "follow_ups"),
            ("commitment", "follow_ups"),
            ("decision", "outcomes_decisions"),
            ("relationship", "participants"),
            ("event", "what_happened"),
            ("interaction", "what_happened"),
            ("observation", "evidence"),
            ("unknown", "summary"),
        ),
    ),
)

ENTITY_TYPES = tuple(definition.key for definition in ENTITY_ONTOLOGY)
PageType = Literal.__getitem__(ENTITY_TYPES)
ENTITY_TYPES_BY_KEY = {definition.key: definition for definition in ENTITY_ONTOLOGY}
DISCOVERABLE_ENTITY_TYPES = tuple(
    definition.key for definition in ENTITY_ONTOLOGY if definition.discoverable
)
DiscoverableEntityType = Literal.__getitem__(DISCOVERABLE_ENTITY_TYPES)


def entity_type_definition(entity_type: str) -> EntityTypeDefinition:
    try:
        return ENTITY_TYPES_BY_KEY[entity_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported entity type: {entity_type}") from exc


def subject_scope_definition(scope: str) -> SubjectScopeDefinition:
    try:
        return SUBJECT_SCOPES_BY_KEY[scope]
    except KeyError as exc:
        raise ValueError(f"Unsupported subject scope: {scope}") from exc


def section_keys(entity_type: str) -> tuple[str, ...]:
    return entity_type_definition(entity_type).section_keys()


def section_pairs(entity_type: str) -> tuple[tuple[str, str], ...]:
    return entity_type_definition(entity_type).section_pairs()


def project_role_section(entity_type: str) -> str:
    section = entity_type_definition(entity_type).project_role_section
    if section is None:
        raise ValueError(f"Project roles cannot render on {entity_type} entities")
    return section


def default_section(
    entity_type: str,
    claim_type: str,
    predicate: str | None,
) -> str:
    definition = entity_type_definition(entity_type)
    if (
        claim_type == "relationship"
        and predicate == "project_role"
        and definition.project_role_section is not None
    ):
        return project_role_section(entity_type)
    try:
        return definition.defaults()[claim_type]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported claim type {claim_type!r} for {entity_type}"
        ) from exc


def entity_type_prompt_catalog(*, discoverable_only: bool = False) -> str:
    definitions = (
        [item for item in ENTITY_ONTOLOGY if item.discoverable]
        if discoverable_only
        else ENTITY_ONTOLOGY
    )
    return "\n".join(
        f"- {item.label} (`{item.key}`): {item.description}" for item in definitions
    )


def subject_scope_prompt_catalog() -> str:
    """Render the authoritative subject-scope definitions for model decisions."""
    lines = ["Scope variants:"]
    lines.extend(
        f"- `{definition.key}` {definition.description}"
        for definition in SUBJECT_SCOPE_ONTOLOGY
    )
    lines.append(SUBJECT_SCOPE_CONTAINMENT_POLICY)
    return "\n".join(lines)


def section_prompt_catalog() -> str:
    lines: list[str] = []
    for definition in ENTITY_ONTOLOGY:
        sections = "; ".join(
            f"{section.key}={section.description}" for section in definition.sections
        )
        lines.append(f"- type={definition.key}; sections: {sections}")
    return "\n".join(lines)


def ontology_response() -> dict:
    return {
        "claim_types": list(CLAIM_TYPES),
        "entity_types": [
            {
                "key": definition.key,
                "label": definition.label,
                "plural_label": definition.plural_label,
                "description": definition.description,
                "discoverable": definition.discoverable,
                "sections": [
                    {
                        "key": section.key,
                        "title": section.title,
                        "description": section.description,
                    }
                    for section in definition.sections
                ],
                "default_sections": dict(definition.default_sections),
                "project_role_section": definition.project_role_section,
            }
            for definition in ENTITY_ONTOLOGY
        ],
    }
