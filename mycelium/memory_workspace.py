"""Runtime-owned accumulated evidence for one assistant response."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

from mycelium.operations import (
    EvidenceSource,
    EvidenceSourceCitation,
    MemoryEvidence,
    MemoryWorkspace,
    MemoryWorkspaceOperation,
)


class MemoryWorkspaceAccumulator:
    """Accumulate complete typed evidence without asking the model to manage state."""

    def __init__(
        self,
        request: str,
        initial_evidence: MemoryEvidence,
        *,
        remaining_searches: int,
        remaining_evidence_tokens: int,
    ) -> None:
        self.request = request
        self.evidence = initial_evidence
        self.operations: list[MemoryWorkspaceOperation] = []
        self.remaining_searches = remaining_searches
        self.remaining_evidence_tokens = remaining_evidence_tokens

    @property
    def snapshot(self) -> MemoryWorkspace:
        return MemoryWorkspace(
            revision=len(self.operations),
            request=self.request,
            evidence=self.evidence,
            operations=tuple(self.operations),
            remaining_searches=self.remaining_searches,
            remaining_evidence_tokens=self.remaining_evidence_tokens,
        )

    def record_success(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        evidence: MemoryEvidence,
        *,
        remaining_searches: int,
        remaining_evidence_tokens: int,
    ) -> MemoryWorkspace:
        previous_record_ids = {
            record.record_id for record in self.evidence.records
        }
        previous_source_ids = {
            source.source_id for source in self.evidence.sources
        }
        self.evidence = merge_memory_evidence(self.evidence, evidence)
        self.remaining_searches = remaining_searches
        self.remaining_evidence_tokens = remaining_evidence_tokens
        self.operations.append(
            MemoryWorkspaceOperation(
                sequence=len(self.operations) + 1,
                tool_name=_memory_tool_name(tool_name),
                status="complete",
                query=(
                    str(arguments.get("query") or "").strip()
                    if tool_name == "memory_search"
                    else None
                ),
                requested_claim_ids=(
                    tuple(str(value) for value in arguments.get("claim_ids", []))
                    if tool_name == "memory_sources"
                    else ()
                ),
                added_record_ids=tuple(
                    record.record_id
                    for record in evidence.records
                    if record.record_id not in previous_record_ids
                ),
                added_source_ids=tuple(
                    source.source_id
                    for source in evidence.sources
                    if source.source_id not in previous_source_ids
                ),
            )
        )
        return self.snapshot

    def record_failure(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        error: str,
        *,
        remaining_searches: int,
        remaining_evidence_tokens: int,
    ) -> MemoryWorkspace:
        self.remaining_searches = remaining_searches
        self.remaining_evidence_tokens = remaining_evidence_tokens
        self.operations.append(
            MemoryWorkspaceOperation(
                sequence=len(self.operations) + 1,
                tool_name=_memory_tool_name(tool_name),
                status="failed",
                query=(
                    str(arguments.get("query") or "").strip()
                    if tool_name == "memory_search"
                    else None
                ),
                requested_claim_ids=(
                    tuple(str(value) for value in arguments.get("claim_ids", []))
                    if tool_name == "memory_sources"
                    else ()
                ),
                error=error,
            )
        )
        return self.snapshot


def merge_memory_evidence(
    current: MemoryEvidence, incoming: MemoryEvidence
) -> MemoryEvidence:
    """Merge evidence by declared IDs while preserving complete evidence units."""
    records = {record.record_id: record for record in current.records}
    for record in incoming.records:
        records.setdefault(record.record_id, record)

    sources = {source.source_id: source for source in current.sources}
    for source in incoming.sources:
        prior = sources.get(source.source_id)
        sources[source.source_id] = (
            source if prior is None else _merge_source(prior, source)
        )

    return MemoryEvidence(
        records=tuple(records.values()),
        sources=tuple(sources.values()),
        more_available=current.more_available or incoming.more_available,
    )


def _merge_source(current: EvidenceSource, incoming: EvidenceSource) -> EvidenceSource:
    citations: dict[str, list[str]] = {}
    for citation in (*current.citations, *incoming.citations):
        segment_ids = citations.setdefault(citation.claim_id, [])
        segment_ids.extend(
            value for value in citation.segment_ids if value not in segment_ids
        )

    segments = {segment.segment_id: segment for segment in current.segments}
    for segment in incoming.segments:
        segments.setdefault(segment.segment_id, segment)
    ordered_segments = tuple(
        sorted(segments.values(), key=lambda item: (item.index, item.segment_id))
    )
    accepted_ids = {segment.segment_id for segment in ordered_segments}

    return replace(
        current,
        conversation_time=current.conversation_time or incoming.conversation_time,
        citations=tuple(
            EvidenceSourceCitation(
                claim_id=claim_id,
                segment_ids=tuple(
                    segment_id
                    for segment_id in segment_ids
                    if segment_id in accepted_ids
                ),
            )
            for claim_id, segment_ids in citations.items()
        ),
        segments=ordered_segments,
    )


def _memory_tool_name(
    value: str,
) -> Literal["memory_search", "memory_sources"]:
    if value == "memory_search":
        return "memory_search"
    if value == "memory_sources":
        return "memory_sources"
    raise ValueError(f"Unsupported memory workspace operation: {value}")
