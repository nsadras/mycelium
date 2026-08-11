from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

PageType = Literal[
    'you', 'person', 'project', 'topic', 'organization', 'place', 'event'
]
PAGE_TYPES: tuple[PageType, ...] = (
    'you', 'person', 'project', 'topic', 'organization', 'place', 'event'
)

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
    taxonomy_failures: list[dict[str, str]] = field(default_factory=list)
    reconsolidation_proposal_ids: list[str] = field(default_factory=list)

@dataclass
class MemoryResult:
    page: WikiPage
    load_priority: int
    tokens_used: int
