"""Typed inputs and outputs for the public memory lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from mycelium.artifacts import SourceSegment
from mycelium.models import DreamReport, LogEntry


@dataclass(frozen=True)
class SourceInput:
    transcript: str
    session_id: str
    source_type: str = "agent_conversation"
    occurred_at: str | datetime | None = None
    participants: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    segments: tuple[SourceSegment | dict[str, Any], ...] | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class IngestionResult:
    status: Literal["empty", "captured"]
    log_entries: tuple[LogEntry, ...] = ()
    source_ids: tuple[str, ...] = ()
    episode_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    operation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    budget_tokens: int | None = None


@dataclass(frozen=True)
class EvidenceCitation:
    claim_id: str
    source_id: str
    segment_ids: tuple[str, ...]
    source_time: str | None = None


@dataclass(frozen=True)
class EvidenceTime:
    claim_id: str
    role: str
    start: str | None
    end: str | None = None
    expression: str | None = None
    target: str | None = None
    evidence_segment_id: str | None = None
    anchor_segment_id: str | None = None
    reference_reason: str | None = None
    status: Literal["resolved", "unresolved", "recurring"] = "resolved"
    resolution_reason: str | None = None


@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    text: str


@dataclass(frozen=True)
class EvidenceReview:
    proposal_id: str
    status: str
    relation: str
    incoming_claim_ids: tuple[str, ...]
    target_claim_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    record_type: Literal["claim", "fact"]
    statement: str
    subject_entity_id: str | None
    subject_name: str | None
    claim_ids: tuple[str, ...]
    state: str | None = None
    temporal: tuple[EvidenceTime, ...] = ()
    citations: tuple[EvidenceCitation, ...] = ()
    canonical_claims: tuple[EvidenceClaim, ...] = ()
    reviews: tuple[EvidenceReview, ...] = ()
    uncertainty: tuple[str, ...] = ()
    revisions: tuple[dict[str, str], ...] = ()
    revision: int = 0


@dataclass(frozen=True)
class EvidenceSegment:
    segment_id: str
    relationship: Literal["cited", "context"]
    speaker: str | None
    content: str
    index: int = 0


@dataclass(frozen=True)
class EvidenceSourceCitation:
    claim_id: str
    segment_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    conversation_time: str
    citations: tuple[EvidenceSourceCitation, ...]
    segments: tuple[EvidenceSegment, ...]
    status: str = "active"
    retraction_reason: str | None = None
    revision: int = 0


@dataclass(frozen=True)
class MemoryEvidence:
    records: tuple[EvidenceRecord, ...] = ()
    sources: tuple[EvidenceSource, ...] = ()
    more_available: bool = False

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                claim_id for record in self.records for claim_id in record.claim_ids
            )
        )


@dataclass(frozen=True)
class MemoryWorkspaceOperation:
    sequence: int
    tool_name: Literal["memory_search", "memory_sources"]
    status: Literal["complete", "failed"]
    query: str | None = None
    requested_claim_ids: tuple[str, ...] = ()
    added_record_ids: tuple[str, ...] = ()
    added_source_ids: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class MemoryWorkspace:
    revision: int
    request: str
    evidence: MemoryEvidence
    operations: tuple[MemoryWorkspaceOperation, ...]
    remaining_searches: int
    remaining_evidence_tokens: int
    last_operation_status: Literal["none", "complete", "failed"] = "none"


@dataclass(frozen=True)
class WikiPageReference:
    """Navigation metadata for a real wiki page, never model-facing evidence."""

    entity_id: str
    slug: str
    title: str
    version: int


@dataclass(frozen=True)
class RetrievalResult:
    page_references: tuple[WikiPageReference, ...]
    evidence: MemoryEvidence
    rendered_context: str
    trace: dict[str, Any] = field(default_factory=dict)


class RetrievalError(RuntimeError):
    """A retryable retrieval failure, distinct from a successful empty search."""

    def __init__(self, stage: str, detail: str):
        self.stage = stage
        self.detail = detail
        super().__init__(f"Memory retrieval failed at {stage}: {detail}")


@dataclass(frozen=True)
class ConsolidationRequest:
    dry_run: bool = False
    include_deferred: bool = True


@dataclass(frozen=True)
class ConsolidationResult:
    report: DreamReport
    processed_episode_ids: tuple[str, ...] = ()
