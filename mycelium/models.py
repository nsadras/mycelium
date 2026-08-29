from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

PageType = Literal[
    'you', 'person', 'project', 'series', 'event', 'artifact', 'topic',
    'organization', 'place'
]
PAGE_TYPES: tuple[PageType, ...] = (
    'you', 'person', 'project', 'series', 'event', 'artifact', 'topic',
    'organization', 'place'
)

PAGE_SECTION_KEYS: dict[PageType, tuple[tuple[str, str], ...]] = {
    "you": (
        ("profile", "Profile"),
        ("current_context", "Current Context"),
        ("priorities_plans", "Priorities & Plans"),
        ("preferences_working_style", "Preferences & Working Style"),
        ("important_relationships", "Important Relationships"),
        ("memory_map", "Memory Map"),
        ("recent_changes", "Recent Changes"),
        ("needs_review", "Needs Review"),
    ),
    "person": (
        ("relationship_to_you", "Relationship to You"),
        ("profile", "Profile"),
        ("current_context", "Current Context"),
        ("interests_views", "Interests & Views"),
        ("goals_plans", "Goals & Plans"),
        ("shared_projects", "Shared Projects"),
        ("timeline", "Timeline"),
        ("research_references", "Research & References"),
        ("needs_review", "Needs Review"),
    ),
    "project": (
        ("overview", "Overview"),
        ("objective", "Objective"),
        ("current_status", "Current Status"),
        ("requirements_constraints", "Requirements & Constraints"),
        ("decisions", "Decisions"),
        ("next_steps_deadlines", "Next Steps & Deadlines"),
        ("people_organizations", "People & Organizations"),
        ("timeline", "Timeline"),
        ("research_references", "Research & References"),
        ("needs_review", "Needs Review"),
    ),
    "series": (
        ("overview", "Overview"),
        ("schedule_pattern", "Schedule & Pattern"),
        ("current_context", "Current Context"),
        ("participants", "Participants"),
        ("occurrences", "Occurrences"),
        ("related_topics", "Related Topics"),
        ("research_references", "Research & References"),
        ("needs_review", "Needs Review"),
    ),
    "artifact": (
        ("overview", "Overview"),
        ("purpose", "Purpose"),
        ("current_state", "Current State"),
        ("requirements_constraints", "Requirements & Constraints"),
        ("decisions", "Decisions"),
        ("related_projects", "Related Projects"),
        ("timeline", "Timeline"),
        ("research_references", "Research & References"),
        ("needs_review", "Needs Review"),
    ),
    "topic": (
        ("why_it_matters", "Why It Matters"),
        ("current_understanding", "Current Understanding"),
        ("preferences_positions", "Preferences & Positions"),
        ("related_projects", "Related Projects"),
        ("timeline", "Timeline"),
        ("research_references", "Research & References"),
        ("needs_review", "Needs Review"),
    ),
    "organization": (
        ("overview", "Overview"),
        ("relationship_to_you", "Relationship to You"),
        ("people", "People"),
        ("related_projects", "Related Projects"),
        ("current_context", "Current Context"),
        ("timeline", "Timeline"),
        ("research_references", "Research & References"),
        ("needs_review", "Needs Review"),
    ),
    "place": (
        ("overview", "Overview"),
        ("why_it_matters", "Why It Matters"),
        ("current_context", "Current Context"),
        ("associated_people_projects", "Associated People & Projects"),
        ("visits_events", "Visits & Events"),
        ("research_references", "Research & References"),
        ("needs_review", "Needs Review"),
    ),
    "event": (
        ("summary", "Summary"),
        ("date_location", "Date & Location"),
        ("participants", "Participants"),
        ("what_happened", "What Happened"),
        ("outcomes_decisions", "Outcomes & Decisions"),
        ("follow_ups", "Follow-ups"),
        ("evidence", "Evidence"),
        ("needs_review", "Needs Review"),
    ),
}

@dataclass
class Edge:
    target: str                          # slug of target wiki page
    relation: Literal[
        'causes', 'contradicts', 'exemplifies',
        'generalizes', 'precedes', 'enables', 'informs'
    ]
    weight: float = 1.0

@dataclass
class UpdateLogEntry:
    version: int
    date: datetime
    session_id: str
    trigger: Literal['reconsolidation', 'dream', 'manual']
    reason: str
    previous_confidence: float
    new_confidence: float

@dataclass
class WikiPage:
    slug: str                            # filename without .md
    title: str
    content: str                         # full markdown body (no frontmatter)
    created: datetime
    last_updated: datetime
    version: int
    confidence: float                    # 0.0–1.0
    importance: float                    # 0.0–1.0
    page_type: PageType | None = None    # explicit null means classification is pending
    tags: list[str] = field(default_factory=list)
    related: list[Edge] = field(default_factory=list)
    source_log_entries: list[str] = field(default_factory=list)
    update_log: list[UpdateLogEntry] = field(default_factory=list)
    source_context: str = field(default='', repr=False)
    entity_id: str = ""
    entity_status: Literal["active", "archived", "merged"] = "active"
    aliases: list[str] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)

@dataclass
class LogEntry:
    entry_id: str                        # e.g. "2026-05-10#entry-1"
    session_id: str
    timestamp: datetime
    content: str
    importance: float
    status: Literal['raw', 'consolidated', 'archived']
    durability: Literal['ephemeral', 'session', 'durable'] = 'durable'
    consolidated: bool = False

@dataclass
class DreamReport:
    pages_updated: int
    pages_created: int
    entries_consolidated: int
    completed_source_ids: list[str] = field(default_factory=list)
    pending_source_ids: list[str] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    reconsolidation_proposal_ids: list[str] = field(default_factory=list)
