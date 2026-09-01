from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from mycelium.ontology import PageType

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

@dataclass
class WikiPage:
    slug: str                            # filename without .md
    title: str
    content: str                         # full markdown body (no frontmatter)
    created: datetime
    last_updated: datetime
    version: int
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
