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


# These policies intentionally preserve the current model-facing language. They live
# beside the entity ontology so extraction, census, planning, and routing do not each
# become independent authorities for what enters the subject graph.
SUBJECT_CENSUS_POLICY = """This call declares nodes only. Do not decide identity matches, page admission, claim ownership, relationships, or
participant resolution. The registry's `you` identity is reserved and must not appear as a node. Include distinct
real subjects needed as stable identity or relationship endpoints, including meaningful components, occurrences,
people, and artifacts. Do not create a node for every noun or mentioned object: a person's attributes and practices,
and contextual inputs or descriptive content, can remain in the claim without becoming graph identities. Merge
repeated mentions of the same subject within the cohort and combine their cited evidence.
When the registry contains a provisional identity and the supplied evidence adds personal history, state, plans, or
relationships about it, declare a candidate node for that subject again. Identity resolution will match it back to
the stable ID so admission can reconsider whether its page is now mature; do not omit it merely because it is already
known provisionally.

For a human subject who is a named source participant, put the exact `P...` alias in participant_evidence. Use an
empty participant_evidence list for every other node. Keep all cited claim and participant aliases in
supporting_evidence.

A workstream, feature, milestone, issue, tool, deliverable, recurring frame, or bounded occurrence may need a node so
its identity or relationship can be decided later, but local details and incidental nouns do not. Preserve genuinely
distinct subjects without deciding their ontology type. Use N001-style IDs and cite only supplied evidence aliases."""

EXTRACTION_SUBJECT_POLICY = """The about list is semantic routing data, not a keyword list. Include the primary subject whose state,
belief, preference, plan, relationship, or action the claim predicates, with role=subject. Include a
different durable entity with role=owner when the claim chiefly changes that entity (for example, a
project requirement). Other named participants may use role=participant. Do not put incidental objects,
generic activities, or predicate complements in about merely because their words occur in the claim."""

ROUTING_SUBJECT_POLICY = """Resolve explicit subject and object endpoints plus useful context endpoints, but
do not add endpoints merely because they appear nearby."""

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
