"""Entity/claim types and optional section choices for human curation.

Build Memory generates natural headings; this registry does not route evidence.
"""

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
    discoverable: bool = True

    def section_keys(self) -> tuple[str, ...]:
        return tuple(section.key for section in self.sections)


# Persisted human-review choices; model presentation chooses useful cited views.
SUBJECT_PERSISTED_SCOPES = (
    "independent",
    "component",
    "occurrence",
    "standalone_event",
    "context",
)
SUBJECT_PAGE_STATES = ("materialized", "provisional", "no_page")


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
    ),
)

ENTITY_TYPES = tuple(definition.key for definition in ENTITY_ONTOLOGY)
PageType = Literal.__getitem__(ENTITY_TYPES)
ENTITY_TYPES_BY_KEY = {definition.key: definition for definition in ENTITY_ONTOLOGY}
DISCOVERABLE_ENTITY_TYPES = tuple(
    definition.key for definition in ENTITY_ONTOLOGY if definition.discoverable
)
DiscoverableEntityType = Literal.__getitem__(DISCOVERABLE_ENTITY_TYPES)


def section_keys(entity_type: str) -> tuple[str, ...]:
    try:
        return ENTITY_TYPES_BY_KEY[entity_type].section_keys()
    except KeyError as exc:
        raise ValueError(f"Unsupported entity type: {entity_type}") from exc


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
            }
            for definition in ENTITY_ONTOLOGY
        ],
    }
