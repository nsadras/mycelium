"""Shared deterministic mapping from claim semantics to typed wiki sections."""

import re

from mycelium.artifacts import MemoryClaim


DEFAULT_SECTIONS: dict[str, dict[str, str]] = {
    "you": {
        "identity": "profile", "state": "current_context", "preference": "preferences_working_style",
        "belief": "preferences_working_style", "plan": "priorities_plans", "commitment": "priorities_plans",
        "decision": "priorities_plans", "relationship": "important_relationships", "event": "current_context",
        "interaction": "important_relationships", "observation": "current_context", "unknown": "current_context",
    },
    "person": {
        "identity": "profile", "state": "current_context", "preference": "interests_views",
        "belief": "interests_views", "plan": "goals_plans", "commitment": "goals_plans",
        "decision": "goals_plans", "relationship": "relationship_to_you", "event": "timeline",
        "interaction": "timeline", "observation": "current_context", "unknown": "current_context",
    },
    "project": {
        "identity": "overview", "state": "current_status", "preference": "requirements_constraints",
        "belief": "requirements_constraints", "plan": "next_steps_deadlines",
        "commitment": "next_steps_deadlines", "decision": "decisions", "relationship": "people_organizations",
        "event": "timeline", "interaction": "timeline", "observation": "overview", "unknown": "overview",
    },
    "series": {
        "identity": "overview", "state": "current_context", "preference": "current_context",
        "belief": "current_context", "plan": "schedule_pattern", "commitment": "schedule_pattern",
        "decision": "current_context", "relationship": "participants", "event": "occurrences",
        "interaction": "occurrences", "observation": "overview", "unknown": "overview",
    },
    "artifact": {
        "identity": "overview", "state": "current_state", "preference": "requirements_constraints",
        "belief": "requirements_constraints", "plan": "current_state", "commitment": "current_state",
        "decision": "decisions", "relationship": "related_projects", "event": "timeline",
        "interaction": "timeline", "observation": "overview", "unknown": "overview",
    },
    "topic": {
        "identity": "why_it_matters", "state": "current_understanding", "preference": "preferences_positions",
        "belief": "preferences_positions", "plan": "why_it_matters", "commitment": "why_it_matters",
        "decision": "current_understanding", "relationship": "related_projects", "event": "timeline",
        "interaction": "timeline", "observation": "current_understanding", "unknown": "current_understanding",
    },
    "organization": {
        "identity": "overview", "state": "current_context", "preference": "current_context",
        "belief": "current_context", "plan": "current_context", "commitment": "current_context",
        "decision": "current_context", "relationship": "relationship_to_you", "event": "timeline",
        "interaction": "timeline", "observation": "current_context", "unknown": "current_context",
    },
    "place": {
        "identity": "overview", "state": "current_context", "preference": "why_it_matters",
        "belief": "why_it_matters", "plan": "current_context", "commitment": "current_context",
        "decision": "current_context", "relationship": "associated_people_projects", "event": "visits_events",
        "interaction": "visits_events", "observation": "current_context", "unknown": "current_context",
    },
    "event": {
        "identity": "summary", "state": "what_happened", "preference": "evidence", "belief": "evidence",
        "plan": "follow_ups", "commitment": "follow_ups", "decision": "outcomes_decisions",
        "relationship": "participants", "event": "what_happened", "interaction": "what_happened",
        "observation": "evidence", "unknown": "summary",
    },
}


def is_project_role(claim: MemoryClaim) -> bool:
    """Return whether a claim is the canonical relationship for a project role."""
    predicate = re.sub(r"[^a-z0-9]+", "_", str(claim.predicate or "").lower()).strip("_")
    return claim.claim_type == "relationship" and predicate == "project_role"


def project_role_section(entity_type: str) -> str:
    """Map one project-role relationship into an endpoint's human-facing view."""
    sections = {
        "you": "priorities_plans",
        "person": "shared_projects",
        "project": "people_organizations",
    }
    if entity_type not in sections:
        raise ValueError(f"Project roles cannot render on {entity_type} entities")
    return sections[entity_type]


def default_section(entity_type: str, claim: MemoryClaim) -> str:
    if claim.evidence_modality == "tool":
        return "evidence" if entity_type == "event" else "research_references"
    if is_project_role(claim) and entity_type in {"you", "person", "project"}:
        return project_role_section(entity_type)
    return DEFAULT_SECTIONS[entity_type][claim.claim_type]
