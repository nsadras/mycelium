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

    operation_history_limit = 8

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
        self.revision = 0
        self.remaining_searches = remaining_searches
        self.remaining_evidence_tokens = remaining_evidence_tokens

    @property
    def snapshot(self) -> MemoryWorkspace:
        return MemoryWorkspace(
            revision=self.revision,
            request=self.request,
            evidence=self.evidence,
            operations=tuple(self.operations),
            remaining_searches=self.remaining_searches,
            remaining_evidence_tokens=self.remaining_evidence_tokens,
            last_operation_status=self.operations[-1].status
            if self.operations
            else "none",
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
        previous_record_ids = {record.record_id for record in self.evidence.records}
        previous_source_ids = {source.source_id for source in self.evidence.sources}
        self.evidence = merge_memory_evidence(self.evidence, evidence)
        self.remaining_searches = remaining_searches
        self.remaining_evidence_tokens = remaining_evidence_tokens
        self._append_operation(
            MemoryWorkspaceOperation(
                sequence=self.revision + 1,
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
        self._append_operation(
            MemoryWorkspaceOperation(
                sequence=self.revision + 1,
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

    def _append_operation(self, operation: MemoryWorkspaceOperation) -> None:
        self.revision = operation.sequence
        self.operations.append(operation)
        del self.operations[: -self.operation_history_limit]


def merge_memory_evidence(
    current: MemoryEvidence, incoming: MemoryEvidence
) -> MemoryEvidence:
    """Merge evidence by declared IDs while preserving complete evidence units."""
    records = {record.record_id: record for record in current.records}
    for record in incoming.records:
        prior = records.get(record.record_id)
        if prior is None or record.revision > prior.revision:
            records[record.record_id] = record
        elif record.revision == prior.revision:
            records[record.record_id] = replace(
                prior,
                claim_ids=tuple(dict.fromkeys((*prior.claim_ids, *record.claim_ids))),
                canonical_claims=tuple(
                    {
                        c.claim_id: c
                        for c in (*prior.canonical_claims, *record.canonical_claims)
                    }.values()
                ),
                citations=tuple(dict.fromkeys((*prior.citations, *record.citations))),
                temporal=tuple(dict.fromkeys((*prior.temporal, *record.temporal))),
                reviews=tuple(
                    {
                        r.proposal_id: r for r in (*prior.reviews, *record.reviews)
                    }.values()
                ),
                uncertainty=tuple(
                    dict.fromkeys((*prior.uncertainty, *record.uncertainty))
                ),
                revisions=tuple(
                    {
                        (r["relation"], r["claim_id"]): r
                        for r in (*prior.revisions, *record.revisions)
                    }.values()
                ),
            )

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
        build_incomplete=current.build_incomplete or incoming.build_incomplete,
    )


def _merge_source(current: EvidenceSource, incoming: EvidenceSource) -> EvidenceSource:
    if incoming.revision > current.revision:
        return incoming
    if incoming.revision < current.revision:
        return current
    citations: dict[str, list[str]] = {}
    for citation in (*current.citations, *incoming.citations):
        segment_ids = citations.setdefault(citation.claim_id, [])
        segment_ids.extend(
            value for value in citation.segment_ids if value not in segment_ids
        )

    segments = {segment.segment_id: segment for segment in current.segments}
    for segment in incoming.segments:
        segments.setdefault(segment.segment_id, segment)
    cited_ids = {sid for ids in citations.values() for sid in ids}
    ordered_segments = tuple(
        replace(
            segment,
            relationship="cited" if segment.segment_id in cited_ids else "context",
        )
        for segment in sorted(
            segments.values(), key=lambda item: (item.index, item.segment_id)
        )
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
