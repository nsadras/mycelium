from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

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
    discrepancy_score: float
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
    stability_days: float = 14.0
    difficulty: float = 0.4
    retrievability: float = 1.0
    last_accessed: Optional[datetime] = None
    last_reviewed: Optional[datetime] = None
    review_count: int = 0
    reinforced_count: int = 0
    conflict_count: int = 0
    pinned: bool = False
    tags: list[str] = field(default_factory=list)
    related: list[Edge] = field(default_factory=list)
    source_log_entries: list[str] = field(default_factory=list)
    labile: bool = False
    labile_session: Optional[str] = None
    update_log: list[UpdateLogEntry] = field(default_factory=list)

    # Set after retrieval, not stored on disk
    was_flagged: bool = field(default=False, repr=False)
    discrepancy_score: float = field(default=0.0, repr=False)
    discrepancy_explanation: str = field(default='', repr=False)
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
    decay_score: float = 1.0

@dataclass
class PredictionError:
    conflict_type: Literal['none', 'additive', 'partial', 'major']
    discrepancy_score: float             # 0.0–1.0
    explanation: str
    suggested_update: Optional[str]

@dataclass
class DreamReport:
    pages_updated: int
    pages_created: int
    entries_consolidated: int
    conflicts_found: list[str]           # page slugs
    conflicts_resolved: int
    completed_source_ids: list[str] = field(default_factory=list)
    pending_source_ids: list[str] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)

@dataclass
class MemoryResult:
    page: WikiPage
    load_priority: int
    tokens_used: int
