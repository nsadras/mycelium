"""Typed inputs and outputs for the public memory lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from mycelium.artifacts import SourceSegment
from mycelium.models import DreamReport, LogEntry, WikiPage


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
    status: Literal["empty", "complete", "incomplete"]
    log_entries: tuple[LogEntry, ...] = ()
    source_ids: tuple[str, ...] = ()
    episode_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    operation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    budget_tokens: int | None = None
    query_time: datetime | None = None


@dataclass(frozen=True)
class RetrievalResult:
    pages: tuple[WikiPage, ...]
    rendered_context: str


@dataclass(frozen=True)
class ConsolidationRequest:
    dry_run: bool = False
    include_deferred: bool = True


@dataclass(frozen=True)
class ConsolidationResult:
    report: DreamReport
    retried_episode_ids: tuple[str, ...] = ()
