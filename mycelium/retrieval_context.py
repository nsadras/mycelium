"""Budgeted rendering of selected claims, facts, and source evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Any, Literal

from mycelium.artifacts import (
    ArtifactStore,
    ConsolidatedFact,
    MemoryClaim,
    SourceSegment,
)
from mycelium.budget import count_tokens
from mycelium.claim_index import ClaimSearchHit
from mycelium.context import render_memory_context
from mycelium.models import WikiPage
from mycelium.operations import (
    EvidenceCitation,
    EvidenceRecord,
    EvidenceSegment,
    EvidenceSource,
    EvidenceSourceCitation,
    EvidenceTime,
    MemoryEvidence,
    MemoryWorkspace,
)
from mycelium.store import WikiStore


@dataclass(frozen=True)
class _RetrievedRecord:
    text: str
    claims: tuple[MemoryClaim, ...]


def render_memory_evidence(evidence: MemoryEvidence) -> str:
    """Render initial evidence with the shared model-facing representation."""
    return _render_evidence_envelope("memory-evidence", evidence)


def render_memory_workspace(workspace: MemoryWorkspace) -> str:
    """Render the one current accumulated evidence workspace for an agent round."""
    operation_lines: list[str] = []
    if workspace.operations:
        operation_lines.append("Completed memory operations:")
        for operation in workspace.operations:
            target = operation.query or ", ".join(operation.requested_claim_ids)
            additions = [
                *operation.added_record_ids,
                *operation.added_source_ids,
            ]
            detail = f"; target: {_text(target)}" if target else ""
            added = (
                "; added: " + ", ".join(f"`{_text(value)}`" for value in additions)
                if additions
                else "; added: none"
            )
            error = f"; error: {_text(operation.error)}" if operation.error else ""
            operation_lines.append(
                f"{operation.sequence}. {_text(operation.tool_name)} "
                f"({_text(operation.status)}){detail}{added}{error}"
            )
        operation_lines.append("")
    return _render_evidence_envelope(
        "memory-workspace",
        workspace.evidence,
        attributes={"revision": str(workspace.revision)},
        preamble=(
            f"Original request: {_text(workspace.request)}",
            f"Remaining searches: {workspace.remaining_searches}",
            f"Remaining evidence tokens: {workspace.remaining_evidence_tokens}",
            "",
            *operation_lines,
        ),
    )


def render_memory_search_result(
    evidence: MemoryEvidence,
    *,
    query: str,
    remaining_searches: int,
) -> str:
    """Render a complete, bounded memory-search result."""
    return _render_evidence_envelope(
        "memory-search-results",
        evidence,
        preamble=(
            f"Query: {_text(query)}",
            f"Remaining searches: {remaining_searches}",
        ),
    )


def render_memory_source_result(
    evidence: MemoryEvidence,
    *,
    requested_claim_ids: list[str],
) -> str:
    """Render complete source excerpts with explicit claim ownership."""
    requested = ", ".join(f"`{_text(value)}`" for value in requested_claim_ids)
    return _render_evidence_envelope(
        "memory-source-results",
        evidence,
        preamble=(f"Requested claims: {requested}",),
    )


def render_memory_tool_error(message: str) -> str:
    """Render a model-visible memory-tool failure without an ambiguous partial result."""
    return "\n".join(
        ["<memory-tool-error>", _text(message), "</memory-tool-error>"]
    )


def _render_evidence_envelope(
    tag: str,
    evidence: MemoryEvidence,
    *,
    preamble: tuple[str, ...] = (),
    attributes: dict[str, str] | None = None,
) -> str:
    rendered_attributes = "".join(
        f' {_attribute(key)}="{_attribute(value)}"'
        for key, value in (attributes or {}).items()
    )
    lines = [f"<{tag}{rendered_attributes}>", *preamble]
    if preamble and (evidence.records or evidence.sources):
        lines.append("")
    lines.extend(_render_records(evidence.records))
    if evidence.records and evidence.sources:
        lines.append("")
    lines.extend(_render_sources(evidence.sources))
    if not evidence.records and not evidence.sources:
        lines.append("No memory evidence found.")
    if evidence.more_available:
        lines.extend(["", "More evidence available: yes"])
    lines.append(f"</{tag}>")
    return "\n".join(lines)


def _render_records(records: tuple[EvidenceRecord, ...]) -> list[str]:
    lines: list[str] = []
    for index, record in enumerate(records):
        if index:
            lines.append("")
        lines.extend(
            [
                f"## Record `{_text(record.record_id)}`",
                f"Statement: {_text(record.statement)}",
                f"Type: {_text(record.record_type)}",
            ]
        )
        if record.subject_name or record.subject_entity_id:
            subject = _text(record.subject_name or "Unnamed subject")
            if record.subject_entity_id:
                subject += f" (`{_text(record.subject_entity_id)}`)"
            lines.append(f"Subject: {subject}")
        if record.state:
            lines.append(f"State: {_text(record.state)}")
        lines.append("Supporting claims:")
        lines.extend(f"- `{_text(value)}`" for value in record.claim_ids)
        if record.temporal:
            lines.append("Timing:")
            for value in record.temporal:
                interval = _text(value.start)
                if value.end and value.end != value.start:
                    interval += f" through {_text(value.end)}"
                expression = (
                    f"; source expression: {_text(value.expression)}"
                    if value.expression
                    else ""
                )
                lines.append(
                    f"- Claim `{_text(value.claim_id)}`: {_text(value.role)} "
                    f"{interval}{expression}"
                )
        if record.citations:
            lines.append("Evidence references:")
            for citation in record.citations:
                segments = ", ".join(
                    f"`{_text(value)}`" for value in citation.segment_ids
                )
                source_time = (
                    f"; conversation time: {_text(citation.source_time)}"
                    if citation.source_time
                    else ""
                )
                lines.append(
                    f"- Claim `{_text(citation.claim_id)}` → source "
                    f"`{_text(citation.source_id)}`{source_time}; cited segments: "
                    f"{segments or '(none)'}"
                )
    return lines


def _render_sources(sources: tuple[EvidenceSource, ...]) -> list[str]:
    lines: list[str] = []
    for index, source in enumerate(sources):
        if index:
            lines.append("")
        lines.extend(
            [
                f"## Source `{_text(source.source_id)}`",
                f"Conversation time: {_text(source.conversation_time)}",
                "Supports claims:",
            ]
        )
        cited_claims_by_segment: dict[str, list[str]] = defaultdict(list)
        for citation in source.citations:
            segments = ", ".join(
                f"`{_text(value)}`" for value in citation.segment_ids
            )
            lines.append(
                f"- `{_text(citation.claim_id)}`: cited segments "
                f"{segments or '(none)'}"
            )
            for segment_id in citation.segment_ids:
                cited_claims_by_segment[segment_id].append(citation.claim_id)
        lines.append("<transcript>")
        for segment in source.segments:
            claim_ids = cited_claims_by_segment.get(segment.segment_id, [])
            cited = (
                " cited-for=\""
                + " ".join(_attribute(value) for value in claim_ids)
                + "\""
                if claim_ids
                else ""
            )
            speaker = f"{_text(segment.speaker)}: " if segment.speaker else ""
            lines.append(
                f"[segment `{_text(segment.segment_id)}`{cited}] "
                f"{speaker}{_text(segment.content)}"
            )
        lines.append("</transcript>")
    return lines


def _text(value: object) -> str:
    return escape(str(value), quote=False)


def _attribute(value: object) -> str:
    return escape(str(value), quote=True)


class RetrievedContextBuilder:
    def __init__(self, wiki: WikiStore, artifacts: ArtifactStore) -> None:
        self.wiki = wiki
        self.artifacts = artifacts

    def build(
        self, hits: list[ClaimSearchHit], *, budget_tokens: int
    ) -> tuple[list[WikiPage], list[str], MemoryEvidence]:
        claims = {claim.claim_id: claim for claim in self.artifacts.list_claims()}
        facts_by_claim: dict[str, list[ConsolidatedFact]] = defaultdict(list)
        for fact in self.artifacts.list_consolidated_facts():
            for claim_id in fact.member_claim_ids:
                facts_by_claim[claim_id].append(fact)

        grouped: dict[str, dict[str, Any]] = {}
        rendered_claim_ids: list[str] = []
        rendered_fact_ids: set[str] = set()
        for hit in hits:
            claim = claims.get(hit.claim_id)
            if claim is None:
                continue
            all_facts = facts_by_claim.get(hit.claim_id, [])
            facts = [
                fact for fact in all_facts if fact.fact_id not in rendered_fact_ids
            ]
            if all_facts and not facts:
                rendered_claim_ids.append(hit.claim_id)
                continue
            group_key = hit.owner_entity_id or "_short-term-memory"
            group = grouped.setdefault(group_key, {"hit": hit, "records": []})
            records: list[_RetrievedRecord] = (
                [
                    self._fact_record(fact, claims)
                    for fact in sorted(facts, key=lambda item: item.fact_id)
                ]
                if facts
                else [self._claim_record(claim, hit.memory_tier)]
            )
            old_length = len(group["records"])
            group["records"].extend(records)
            if (
                count_tokens(render_memory_context(self._pages(grouped)))
                > budget_tokens
            ):
                del group["records"][old_length:]
                if not group["records"]:
                    grouped.pop(group_key)
                continue
            rendered_claim_ids.append(hit.claim_id)
            rendered_fact_ids.update(fact.fact_id for fact in facts)

        pages = self._pages(grouped)
        evidence = self._memory_evidence(hits, rendered_claim_ids)
        return pages, rendered_claim_ids, evidence

    def admission_content(self, hit: ClaimSearchHit) -> str:
        """Describe the evidence a hit can contribute before admission."""
        try:
            claim = self.artifacts.get_claim(hit.claim_id)
        except FileNotFoundError:
            return hit.claim_text

        lines = [f"Claim: {claim.text}", *self._timing_lines([claim])]
        facts = [
            fact
            for fact in self.artifacts.list_consolidated_facts()
            if hit.claim_id in fact.member_claim_ids
        ]
        if facts:
            lines.append("Consolidated representations:")
            lines.extend(
                f"- [{fact.state}] {fact.text}"
                for fact in sorted(facts, key=lambda item: item.fact_id)
            )
        return "\n".join(lines)

    def source_evidence(
        self, claim_ids: list[str], *, budget_tokens: int
    ) -> MemoryEvidence:
        """Return bounded structured source evidence for exact active claim IDs."""
        claims = {
            claim.claim_id: claim
            for claim in self.artifacts.list_claims(status="active")
        }
        return self._structured_source_evidence(
            [
                claims[claim_id]
                for claim_id in dict.fromkeys(claim_ids)
                if claim_id in claims
            ],
            budget_tokens=budget_tokens,
        )

    def _memory_evidence(
        self, hits: list[ClaimSearchHit], rendered_claim_ids: list[str]
    ) -> MemoryEvidence:
        rendered = set(rendered_claim_ids)
        claims = {claim.claim_id: claim for claim in self.artifacts.list_claims()}
        facts_by_claim: dict[str, list[ConsolidatedFact]] = defaultdict(list)
        for fact in self.artifacts.list_consolidated_facts():
            for claim_id in fact.member_claim_ids:
                facts_by_claim[claim_id].append(fact)

        records: list[EvidenceRecord] = []
        seen_record_ids: set[str] = set()
        for hit in hits:
            if hit.claim_id not in rendered:
                continue
            claim = claims.get(hit.claim_id)
            if claim is None:
                continue
            facts = facts_by_claim.get(hit.claim_id, [])
            if facts:
                for fact in sorted(facts, key=lambda item: item.fact_id):
                    if fact.fact_id in seen_record_ids:
                        continue
                    members = [
                        claims[claim_id]
                        for claim_id in fact.member_claim_ids
                        if claim_id in claims
                    ]
                    records.append(
                        self._structured_record(
                            record_id=fact.fact_id,
                            record_type="fact",
                            statement=fact.text,
                            subject_entity_id=fact.owner_entity_id,
                            subject_name=self._entity_title(fact.owner_entity_id),
                            claim_ids=tuple(fact.member_claim_ids),
                            state=fact.state,
                            claims=members,
                        )
                    )
                    seen_record_ids.add(fact.fact_id)
                continue
            if claim.claim_id in seen_record_ids:
                continue
            records.append(
                self._structured_record(
                    record_id=claim.claim_id,
                    record_type="claim",
                    statement=claim.text,
                    subject_entity_id=hit.owner_entity_id,
                    subject_name=hit.owner_title,
                    claim_ids=(claim.claim_id,),
                    state=hit.memory_tier,
                    claims=[claim],
                )
            )
            seen_record_ids.add(claim.claim_id)
        return MemoryEvidence(
            records=tuple(records),
            more_available=any(hit.claim_id not in rendered for hit in hits),
        )

    def _structured_record(
        self,
        *,
        record_id: str,
        record_type: Literal["claim", "fact"],
        statement: str,
        subject_entity_id: str | None,
        subject_name: str | None,
        claim_ids: tuple[str, ...],
        state: str | None,
        claims: list[MemoryClaim],
    ) -> EvidenceRecord:
        temporal: list[EvidenceTime] = []
        citations: list[EvidenceCitation] = []
        seen_citations: set[tuple[str, str, tuple[str, ...]]] = set()
        for claim in claims:
            value = claim.facets.get("temporal")
            if isinstance(value, dict) and value.get("start"):
                temporal.append(
                    EvidenceTime(
                        claim_id=claim.claim_id,
                        role=str(value.get("role") or "time"),
                        start=str(value["start"]),
                        end=str(value["end"]) if value.get("end") else None,
                        expression=(
                            str(value["expression"])
                            if value.get("expression")
                            else None
                        ),
                    )
                )
            for provenance in claim.provenance:
                key = (
                    claim.claim_id,
                    provenance.source_id,
                    tuple(provenance.segment_ids),
                )
                if key in seen_citations:
                    continue
                seen_citations.add(key)
                citations.append(
                    EvidenceCitation(
                        claim_id=claim.claim_id,
                        source_id=provenance.source_id,
                        segment_ids=tuple(provenance.segment_ids),
                        source_time=self._source_time(provenance.source_id),
                    )
                )
        return EvidenceRecord(
            record_id=record_id,
            record_type=record_type,
            statement=statement,
            subject_entity_id=subject_entity_id,
            subject_name=subject_name,
            claim_ids=claim_ids,
            state=state,
            temporal=tuple(temporal),
            citations=tuple(citations),
        )

    def _entity_title(self, entity_id: str | None) -> str | None:
        if not entity_id:
            return None
        try:
            return self.artifacts.get_entity(entity_id).title
        except FileNotFoundError:
            return None

    def _source_time(self, source_id: str) -> str | None:
        try:
            source = self.artifacts.get_source(source_id)
        except FileNotFoundError:
            return None
        return source.occurred_at or source.recorded_at

    def _structured_source_evidence(
        self, claims: list[MemoryClaim], *, budget_tokens: int
    ) -> MemoryEvidence:
        cited_by_source: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for claim in claims:
            for provenance in claim.provenance:
                cited_by_source[provenance.source_id][claim.claim_id].update(
                    provenance.segment_ids
                )

        sources: list[EvidenceSource] = []
        more_available = False
        for source_id, cited_by_claim in cited_by_source.items():
            try:
                source = self.artifacts.get_source(source_id)
            except FileNotFoundError:
                continue
            cited_ids = {
                segment_id
                for segment_ids in cited_by_claim.values()
                for segment_id in segment_ids
            }
            selected_ids = self._neighbor_segment_ids(source.segments, cited_ids)
            cited_segments = [
                segment
                for segment in source.segments
                if segment.segment_id in cited_ids
            ]
            context_segments = [
                segment
                for segment in source.segments
                if segment.segment_id in selected_ids
                and segment.segment_id not in cited_ids
            ]
            accepted_ids: set[str] = set()
            for segment in [*cited_segments, *context_segments]:
                trial_ids = {*accepted_ids, segment.segment_id}
                trial_segments = tuple(
                    self._evidence_segment(value, cited_ids)
                    for value in source.segments
                    if value.segment_id in trial_ids
                )
                trial_source = EvidenceSource(
                    source_id=source.source_id,
                    conversation_time=source.occurred_at or source.recorded_at,
                    citations=self._source_citations(cited_by_claim, trial_ids),
                    segments=trial_segments,
                )
                trial = MemoryEvidence(sources=tuple([*sources, trial_source]))
                if count_tokens(render_memory_evidence(trial)) > budget_tokens:
                    more_available = True
                    continue
                accepted_ids.add(segment.segment_id)
            if accepted_ids:
                sources.append(
                    EvidenceSource(
                        source_id=source.source_id,
                        conversation_time=source.occurred_at or source.recorded_at,
                        citations=self._source_citations(
                            cited_by_claim, accepted_ids
                        ),
                        segments=tuple(
                            self._evidence_segment(value, cited_ids)
                            for value in source.segments
                            if value.segment_id in accepted_ids
                        ),
                    )
                )
        return MemoryEvidence(
            sources=tuple(sources), more_available=more_available
        )

    @staticmethod
    def _evidence_segment(
        segment: SourceSegment, cited_ids: set[str]
    ) -> EvidenceSegment:
        return EvidenceSegment(
            segment_id=segment.segment_id,
            relationship="cited" if segment.segment_id in cited_ids else "context",
            speaker=segment.speaker,
            content=" ".join(segment.content.split()),
            index=segment.index,
        )

    @staticmethod
    def _source_citations(
        cited_by_claim: dict[str, set[str]], accepted_ids: set[str]
    ) -> tuple[EvidenceSourceCitation, ...]:
        return tuple(
            EvidenceSourceCitation(
                claim_id=claim_id,
                segment_ids=tuple(
                    sorted(
                        segment_id
                        for segment_id in segment_ids
                        if segment_id in accepted_ids
                    )
                ),
            )
            for claim_id, segment_ids in cited_by_claim.items()
            if any(segment_id in accepted_ids for segment_id in segment_ids)
        )

    def _pages(self, groups: dict[str, dict[str, Any]]) -> list[WikiPage]:
        now = datetime.now().astimezone()
        pages: list[WikiPage] = []
        for key, group in groups.items():
            hit: ClaimSearchHit = group["hit"]
            original = (
                self.wiki.get(hit.page_slug)
                if hit.page_slug and self.wiki.exists(hit.page_slug)
                else None
            )
            intro = (
                "The following records were selected for this request from canonical memory."
                if hit.owner_entity_id
                else "The following records are recent claims that have not entered the canonical wiki."
            )
            pages.append(
                WikiPage(
                    slug=(
                        original.slug
                        if original
                        else key
                        if key.startswith("_")
                        else f"_retrieved-{key}"
                    ),
                    title=original.title
                    if original
                    else (hit.owner_title or "Recent, unconsolidated memory"),
                    content="\n\n".join(
                        [
                            intro,
                            *(record.text for record in group["records"]),
                            self._source_evidence(
                                [
                                    claim
                                    for record in group["records"]
                                    for claim in record.claims
                                ]
                            ),
                        ]
                    ).strip(),
                    created=original.created if original else now,
                    last_updated=original.last_updated if original else now,
                    version=original.version if original else 1,
                    page_type=original.page_type if original else None,
                    tags=list(original.tags) if original else ["retrieved-memory"],
                    entity_id=hit.owner_entity_id or "_short-term-memory",
                )
            )
        return pages

    def _fact_record(
        self, fact: ConsolidatedFact, claims: dict[str, MemoryClaim]
    ) -> _RetrievedRecord:
        members = [claims[value] for value in fact.member_claim_ids if value in claims]
        header = f"- [{fact.state} fact] {fact.text} (fact: `{fact.fact_id}`)"
        return _RetrievedRecord(
            "\n".join(
                [
                    header,
                    *self._timing_lines(members),
                    *self._citation_lines(members),
                ]
            ),
            tuple(members),
        )

    def _claim_record(self, claim: MemoryClaim, tier: str) -> _RetrievedRecord:
        header = f"- [{tier} claim] {claim.text} (claim: `{claim.claim_id}`)"
        return _RetrievedRecord(
            "\n".join(
                [
                    header,
                    *self._timing_lines([claim]),
                    *self._citation_lines([claim]),
                ]
            ),
            (claim,),
        )

    @staticmethod
    def _timing_lines(claims: list[MemoryClaim]) -> list[str]:
        lines: list[str] = []
        seen: set[tuple[str, str, str, str]] = set()
        for claim in claims:
            temporal = claim.facets.get("temporal")
            if not isinstance(temporal, dict):
                continue
            role = str(temporal.get("role") or "time")
            start = str(temporal.get("start") or "")
            end = str(temporal.get("end") or "")
            expression = str(temporal.get("expression") or "")
            if not start:
                continue
            key = (role, start, end, expression)
            if key in seen:
                continue
            seen.add(key)
            interval = start if not end or end == start else f"{start} through {end}"
            source_phrase = f"; source expression: {expression}" if expression else ""
            lines.append(f"  - Structured timing: {role} {interval}{source_phrase}")
        return lines

    @staticmethod
    def _citation_lines(claims: list[MemoryClaim]) -> list[str]:
        lines: list[str] = []
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for claim in claims:
            for provenance in claim.provenance:
                key = (provenance.source_id, tuple(provenance.segment_ids))
                if key in seen:
                    continue
                seen.add(key)
                segments = ", ".join(f"`{value}`" for value in provenance.segment_ids)
                lines.append(
                    f"  - Cites `{provenance.source_id}`"
                    + (f" / {segments}" if segments else "")
                )
        return lines

    def _source_evidence(self, claims: list[MemoryClaim]) -> str:
        cited_by_source: dict[str, set[str]] = defaultdict(set)
        for claim in claims:
            for provenance in claim.provenance:
                cited_by_source[provenance.source_id].update(provenance.segment_ids)

        blocks: list[str] = []
        for source_id, cited_ids in cited_by_source.items():
            try:
                source = self.artifacts.get_source(source_id)
            except FileNotFoundError:
                continue
            selected_ids = self._neighbor_segment_ids(source.segments, cited_ids)
            if not selected_ids:
                continue
            lines = [
                f"### Source `{source.source_id}`",
                f"Conversation time: {source.occurred_at or source.recorded_at}",
                "Cited lines:",
            ]
            cited_segments = [
                segment
                for segment in source.segments
                if segment.segment_id in cited_ids
            ]
            context_segments = [
                segment
                for segment in source.segments
                if segment.segment_id in selected_ids
                and segment.segment_id not in cited_ids
            ]
            for marker, selected_segments in (
                ("cited", cited_segments),
                ("context", context_segments),
            ):
                if marker == "context" and selected_segments:
                    lines.append("Surrounding context (chronological):")
                for segment in selected_segments:
                    lines.append(self._source_segment_line(segment, marker))
            blocks.append("\n".join(lines))
        if not blocks:
            return ""
        return "\n\n".join(["## Source evidence", *blocks])

    @staticmethod
    def _source_segment_line(segment: SourceSegment, marker: str) -> str:
        label = segment.metadata.get("source_label")
        label_text = f"; label={label}" if label else ""
        speaker = f"{segment.speaker}: " if segment.speaker else ""
        content = " ".join(segment.content.split())
        if len(content) > 700:
            content = content[:697].rstrip() + "..."
        return (
            f"- [{marker}] {speaker}{content} "
            f"(segment=`{segment.segment_id}`{label_text})"
        )

    @staticmethod
    def _neighbor_segment_ids(
        segments: list[SourceSegment], cited_ids: set[str]
    ) -> set[str]:
        groups: list[tuple[object, list[SourceSegment]]] = []
        group_positions: dict[object, int] = {}
        for segment in segments:
            parent_index = segment.metadata.get("parent_segment_index")
            group_key: object = (
                ("turn", parent_index)
                if isinstance(parent_index, int)
                else ("segment", segment.index)
            )
            position = group_positions.get(group_key)
            if position is None:
                position = len(groups)
                group_positions[group_key] = position
                groups.append((group_key, []))
            groups[position][1].append(segment)

        cited_positions = {
            position
            for position, (_, group_segments) in enumerate(groups)
            if any(segment.segment_id in cited_ids for segment in group_segments)
        }
        selected_positions = {
            neighbor
            for position in cited_positions
            for neighbor in range(max(0, position - 2), min(len(groups), position + 2))
        }
        return {
            segment.segment_id
            for position in selected_positions
            for segment in groups[position][1]
        }
