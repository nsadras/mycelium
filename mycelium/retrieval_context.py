"""Budgeted rendering of selected claims, facts, and source evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
import json
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
    EvidenceTime,
    MemoryEvidence,
)
from mycelium.store import WikiStore


@dataclass(frozen=True)
class _RetrievedRecord:
    text: str
    claims: tuple[MemoryClaim, ...]


def render_memory_evidence(evidence: MemoryEvidence) -> str:
    """Render the shared model-facing evidence contract as valid JSON."""
    return json.dumps(asdict(evidence), indent=2, ensure_ascii=False)


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
        return MemoryEvidence(records=tuple(records))

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
        cited_by_source: dict[str, set[str]] = defaultdict(set)
        for claim in claims:
            for provenance in claim.provenance:
                cited_by_source[provenance.source_id].update(provenance.segment_ids)

        sources: list[EvidenceSource] = []
        truncated = False
        for source_id, cited_ids in cited_by_source.items():
            try:
                source = self.artifacts.get_source(source_id)
            except FileNotFoundError:
                continue
            selected_ids = self._neighbor_segment_ids(source.segments, cited_ids)
            ordered = [
                segment
                for segment in source.segments
                if segment.segment_id in cited_ids
            ] + [
                segment
                for segment in source.segments
                if segment.segment_id in selected_ids
                and segment.segment_id not in cited_ids
            ]
            accepted: list[EvidenceSegment] = []
            for segment in ordered:
                candidate = EvidenceSegment(
                    segment_id=segment.segment_id,
                    relationship=(
                        "cited" if segment.segment_id in cited_ids else "context"
                    ),
                    speaker=segment.speaker,
                    content=" ".join(segment.content.split()),
                )
                trial_source = EvidenceSource(
                    source_id=source.source_id,
                    conversation_time=source.occurred_at or source.recorded_at,
                    segments=tuple([*accepted, candidate]),
                )
                trial = MemoryEvidence(sources=tuple([*sources, trial_source]))
                if count_tokens(render_memory_evidence(trial)) > budget_tokens:
                    truncated = True
                    continue
                accepted.append(candidate)
            if accepted:
                sources.append(
                    EvidenceSource(
                        source_id=source.source_id,
                        conversation_time=source.occurred_at or source.recorded_at,
                        segments=tuple(accepted),
                    )
                )
        return MemoryEvidence(sources=tuple(sources), truncated=truncated)

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
