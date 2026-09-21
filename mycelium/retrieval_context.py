"""Budgeted rendering of selected claims, facts, and source evidence."""

from __future__ import annotations

from collections import defaultdict
from functools import cached_property
from dataclasses import replace
from html import escape
from typing import Callable, Literal

from mycelium.artifacts import (
    ArtifactStore,
    MemoryClaim,
    SourceSegment,
)
from mycelium.budget import count_tokens
from mycelium.claim_index import ClaimSearchHit
from mycelium.operations import (
    EvidenceCitation,
    EvidenceClaim,
    EvidenceReview,
    EvidenceRecord,
    EvidenceSegment,
    EvidenceSource,
    EvidenceSourceCitation,
    EvidenceTime,
    MemoryEvidence,
    MemoryWorkspace,
    RetrievalError,
    WikiPageReference,
)
from mycelium.store import WikiStore
from mycelium.source_references import segment_references
from mycelium.temporal import temporal_records


def fit_memory_evidence(
    evidence: MemoryEvidence, fits: Callable[[MemoryEvidence], bool]
) -> MemoryEvidence:
    """Admit complete records and source groups in order under the caller's budget."""
    if fits(evidence):
        return evidence
    # Reserve the omission notice so adding it cannot overflow the budget.
    selected = MemoryEvidence(more_available=True, build_incomplete=evidence.build_incomplete)
    if not fits(selected):
        raise ValueError("Evidence budget is smaller than the empty evidence envelope")
    for record in evidence.records:
        trial = replace(selected, records=(*selected.records, record))
        if fits(trial):
            selected = trial
    for source in evidence.sources:
        trial = replace(selected, sources=(*selected.sources, source))
        if fits(trial):
            selected = trial
    return selected


def render_memory_evidence(evidence: MemoryEvidence) -> str:
    """Render initial evidence with the shared model-facing representation."""
    return _render_evidence_envelope("memory-evidence", evidence)


def render_memory_workspace(
    workspace: MemoryWorkspace, *, include_request: bool = True
) -> str:
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
        attributes={
            "revision": str(workspace.revision),
            "last_operation_status": workspace.last_operation_status,
        },
        preamble=(
            *(
                [f"Original request: {_text(workspace.request)}"]
                if include_request
                else []
            ),
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
    return "\n".join(["<memory-tool-error>", _text(message), "</memory-tool-error>"])


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
    if evidence.build_incomplete:
        lines.append("Build Memory is incomplete. Captured conversations or view updates are still pending; this evidence may miss recent information.")
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
        for qualification in record.uncertainty:
            lines.append(f"Uncertainty: {_text(qualification)}")
        for revision in record.revisions:
            lines.append(
                f"Revision: {_text(revision['relation'])} `{_text(revision['claim_id'])}` "
                f"({_text(revision['status'])}): {_text(revision['text'])}"
            )
        lines.append("Supporting claims:")
        lines.extend(f"- `{_text(value)}`" for value in record.claim_ids)
        if record.canonical_claims:
            lines.append("Matched canonical assertions:")
            lines.extend(
                f"- `{_text(c.claim_id)}`: {_text(c.text)}"
                for c in record.canonical_claims
            )
        for review in record.reviews:
            lines.append(
                f"Review `{_text(review.proposal_id)}`: {_text(review.status)}; "
                f"relation: {_text(review.relation)}; incoming claims: "
                + ", ".join(_text(c) for c in review.incoming_claim_ids)
                + "; target claims: "
                + ", ".join(_text(c) for c in review.target_claim_ids)
                + ". This relationship is unresolved; incoming claims do not establish a replacement."
            )
        if record.temporal:
            lines.append("Timing:")
            for value in record.temporal:
                interval = _text(value.start) if value.start else _text(value.status)
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
                    + (f"; applies to: {_text(value.target)}" if value.target else "")
                    + (
                        f"; time evidence: `{_text(value.evidence_segment_id)}`"
                        if value.evidence_segment_id
                        else ""
                    )
                    + (
                        f"; reference date from: `{_text(value.anchor_segment_id)}`"
                        if value.anchor_segment_id
                        and value.anchor_segment_id != value.evidence_segment_id
                        else ""
                    )
                    + (
                        f"; reference choice: {_text(value.reference_reason)}"
                        if value.reference_reason
                        else ""
                    )
                    + (
                        f"; reason: {_text(value.resolution_reason)}"
                        if value.resolution_reason
                        else ""
                    )
                )
        if record.citations:
            lines.append("Evidence references:")
            for citation in record.citations:
                segments = segment_references(citation.source_id, citation.segment_ids)
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
                f"Source status: {_text(source.status)}"
                + (
                    f" — {_text(source.retraction_reason)}"
                    if source.retraction_reason
                    else ""
                ),
                "Supports claims:",
            ]
        )
        cited_claims_by_segment: dict[str, list[str]] = defaultdict(list)
        for citation in source.citations:
            segments = segment_references(source.source_id, citation.segment_ids)
            lines.append(
                f"- `{_text(citation.claim_id)}`: cited segments {segments or '(none)'}"
            )
            for segment_id in citation.segment_ids:
                cited_claims_by_segment[segment_id].append(citation.claim_id)
        lines.append("<transcript>")
        for segment in source.segments:
            claim_ids = cited_claims_by_segment.get(segment.segment_id, [])
            cited = (
                ' cited-for="'
                + " ".join(_attribute(value) for value in claim_ids)
                + '"'
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

    def _facts_for_claim(self, claim_id):
        return self.artifacts.facts_for_claim(claim_id)

    def current_hit(self, hit: ClaimSearchHit) -> ClaimSearchHit | None:
        """The index supplies identity/rank; canonical records supply interpretation."""
        try:
            claim = self.artifacts.get_claim(hit.claim_id)
        except FileNotFoundError:
            return None
        if claim.status not in {"active", "superseded"}:
            return None
        return replace(hit, claim_text=claim.text,
            memory_tier=self.artifacts.memory_tier(claim.claim_id),
            owner_entity_id=None, owner_title=None, page_slug=None, section_key=None)

    def _source_uncertainty(self, claims):
        notes = []
        for claim in claims:
            for provenance in claim.provenance:
                try:
                    source = self.artifacts.get_source(provenance.source_id)
                except FileNotFoundError as exc:
                    raise RetrievalError(
                        "evidence_integrity",
                        f"Claim {claim.claim_id} cites missing source {provenance.source_id}",
                    ) from exc
                missing = set(provenance.segment_ids) - {
                    s.segment_id for s in source.segments
                }
                if missing:
                    raise RetrievalError(
                        "evidence_integrity",
                        f"Claim {claim.claim_id} cites missing segments {sorted(missing)}",
                    )
                if source.status == "retracted":
                    notes.append(
                        f"Supporting source {source.source_id} is retracted; interpretation may be incomplete."
                    )
        return tuple(dict.fromkeys(notes))

    @cached_property
    def reviews_by_claim(self):
        result = defaultdict(list)
        for p in self.artifacts.list_reconsolidation_proposals(status="pending"):
            review = EvidenceReview(
                p.proposal_id,
                p.status,
                p.proposed_relation,
                tuple(p.incoming_claim_ids),
                tuple(p.target_claim_ids),
            )
            for claim_id in {*p.incoming_claim_ids, *p.target_claim_ids}:
                result[claim_id].append(review)
        return result

    def distinct_hits(self, hits, limit):
        selected, seen = [], set()
        for hit in hits:
            ids = {f.fact_id for f in self._facts_for_claim(hit.claim_id)} or {
                hit.claim_id
            }
            if ids <= seen:
                selected.append(hit)
                continue
            if len(seen) >= limit:
                continue
            selected.append(hit)
            seen.update(ids)
        return selected

    def build(
        self,
        hits: list[ClaimSearchHit],
        *,
        budget_tokens: int,
        more_available: bool = False,
    ) -> MemoryEvidence:
        evidence = replace(self._memory_evidence(hits), more_available=more_available)
        return self._with_sources(
            evidence, budget_tokens=budget_tokens, include_context=False
        )

    def _with_sources(
        self, evidence: MemoryEvidence, *, budget_tokens: int, include_context: bool
    ) -> MemoryEvidence:
        def fits(trial):
            return count_tokens(render_memory_evidence(trial)) <= budget_tokens

        # Retain canonical interpretation state before adding original wording.
        # Only exact citations of records that fit may contribute excerpts.
        evidence = fit_memory_evidence(evidence, fits)
        claims = [self.artifacts.get_claim(cid) for cid in evidence.claim_ids]
        return fit_memory_evidence(
            self._structured_source_evidence(
                claims,
                budget_tokens=budget_tokens,
                base=evidence,
                include_context=include_context,
            ),
            fits,
        )

    def page_references(
        self, evidence: MemoryEvidence
    ) -> tuple[WikiPageReference, ...]:
        references = []
        entity_ids = dict.fromkeys(
            record.subject_entity_id
            for record in evidence.records
            if record.subject_entity_id is not None
        )
        for entity_id in entity_ids:
            try:
                entity = self.artifacts.get_entity(entity_id)
            except FileNotFoundError:
                continue
            if self.wiki.exists(entity.slug):
                page = self.wiki.get(entity.slug)
                references.append(
                    WikiPageReference(
                        entity_id=entity_id,
                        slug=page.slug,
                        title=page.title,
                        version=page.version,
                    )
                )
        return tuple(references)

    def source_evidence(
        self, claim_ids: list[str], *, budget_tokens: int
    ) -> MemoryEvidence:
        """Return bounded structured source evidence for exact active claim IDs."""
        claims = {}
        for claim_id in dict.fromkeys(claim_ids):
            try:
                claim = self.artifacts.get_claim(claim_id)
            except FileNotFoundError:
                continue
            if claim.status in {"active", "superseded"}:
                claims[claim_id] = claim
        records = self._memory_evidence(
            [
                ClaimSearchHit(
                    c.claim_id, c.text, c.status, None, None, None, None, None
                )
                for c in claims.values()
            ]
        )
        # Carry interpretation status with transcript excerpts, so inspecting an
        # older source cannot silently revive a superseded interpretation.
        return self._with_sources(
            records,
            budget_tokens=budget_tokens,
            include_context=True,
        )

    def _memory_evidence(self, hits: list[ClaimSearchHit]) -> MemoryEvidence:
        hits = [
            current for hit in hits if (current := self.current_hit(hit)) is not None
        ]
        matched_ids = {hit.claim_id for hit in hits}
        facts_by_claim = {
            hit.claim_id: self._facts_for_claim(hit.claim_id) for hit in hits
        }
        wanted = matched_ids | {
            cid
            for hit in hits
            for f in facts_by_claim.get(hit.claim_id, [])
            for cid in f.member_claim_ids
        }
        claims = {}
        for cid in wanted:
            try:
                claims[cid] = self.artifacts.get_claim(cid)
            except FileNotFoundError:
                continue

        records: list[EvidenceRecord] = []
        seen_record_ids: set[str] = set()
        for hit in hits:
            claim = claims.get(hit.claim_id)
            if claim is None or claim.status not in {"active", "superseded"}:
                continue
            facts = [
                f
                for f in facts_by_claim.get(hit.claim_id, [])
                if all(
                    cid in claims and claims[cid].status == "active"
                    for cid in f.member_claim_ids
                )
            ]
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
                            matched_claim_ids=matched_ids,
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
                    state="superseded"
                    if claim.status == "superseded"
                    else self.artifacts.memory_tier(claim.claim_id),
                    claims=[claim],
                )
            )
            seen_record_ids.add(claim.claim_id)
        return MemoryEvidence(
            records=tuple(records),
            build_incomplete=self.artifacts.build_incomplete(),
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
        matched_claim_ids: set[str] | None = None,
    ) -> EvidenceRecord:
        temporal: list[EvidenceTime] = []
        citations: list[EvidenceCitation] = []
        seen_citations: set[tuple[str, str, tuple[str, ...]]] = set()
        for claim in claims:
            for value in temporal_records(claim.facets):
                temporal.append(
                    EvidenceTime(
                        claim_id=claim.claim_id,
                        role=value["role"],
                        start=value["start"],
                        end=value["end"],
                        expression=value["expression"],
                        target=value["target"],
                        evidence_segment_id=value["evidence_segment_id"],
                        status=value["status"],
                        anchor_segment_id=value["anchor_segment_id"],
                        reference_reason=value["reference_reason"],
                        resolution_reason=value["meaning"].get("reason")
                        or value["resolution_error"],
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
            revision=self.artifacts.db.evidence_revision(),
            record_id=record_id,
            record_type=record_type,
            statement=statement,
            subject_entity_id=subject_entity_id,
            subject_name=subject_name,
            claim_ids=claim_ids,
            state=state,
            temporal=tuple(temporal),
            citations=tuple(citations),
            canonical_claims=tuple(
                EvidenceClaim(c.claim_id, c.text)
                for c in claims
                if matched_claim_ids is None or c.claim_id in matched_claim_ids
            ),
            reviews=tuple(
                {
                    r.proposal_id: r
                    for cid in claim_ids
                    for r in self.reviews_by_claim.get(cid, [])
                }.values()
            ),
            uncertainty=tuple(dict.fromkeys(
                f"Identity unresolved; optional review {decision.decision_id}"
                for decision in self.artifacts.list_entity_resolution_decisions(review_state="review_required")
                if set(claim_ids) & set(decision.supporting_claim_ids)
            )) + self._source_uncertainty(claims),
            revisions=tuple(self._revisions(claims)),
        )

    def _revisions(self, claims):
        seen = set()
        for claim in claims:
            for link in claim.links:
                if link["relation"] not in {
                    "supersedes",
                    "superseded_by",
                    "contradicts",
                }:
                    continue
                key = (link["relation"], link["target"])
                if key in seen:
                    continue
                try:
                    other = self.artifacts.get_claim(link["target"])
                except FileNotFoundError:
                    continue
                seen.add(key)
                yield {
                    "relation": link["relation"],
                    "claim_id": other.claim_id,
                    "status": other.status,
                    "text": other.text,
                }

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
        self,
        claims: list[MemoryClaim],
        *,
        budget_tokens: int,
        base: MemoryEvidence,
        include_context: bool,
    ) -> MemoryEvidence:
        cited_by_source: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for claim in claims:
            for provenance in claim.provenance:
                cited_by_source[provenance.source_id][claim.claim_id].update(
                    provenance.segment_ids
                )

        available: list[EvidenceSource] = []
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
            selected_ids = (
                self._neighbor_segment_ids(source.segments, cited_ids)
                if include_context
                else cited_ids
            )
            available.append(
                EvidenceSource(
                    revision=self.artifacts.db.evidence_revision(),
                    source_id=source.source_id,
                    conversation_time=source.occurred_at or source.recorded_at,
                    citations=self._source_citations(cited_by_claim, selected_ids),
                    segments=tuple(
                        self._evidence_segment(segment, cited_ids)
                        for segment in source.segments
                        if segment.segment_id in selected_ids
                    ),
                    status=source.status,
                    retraction_reason=source.retraction_reason,
                )
            )
        complete = replace(base, sources=tuple(available))
        if count_tokens(render_memory_evidence(complete)) <= budget_tokens:
            return complete

        sources: list[EvidenceSource] = []
        for source in available:
            cited_by_claim = {
                citation.claim_id: set(citation.segment_ids)
                for citation in source.citations
            }
            cited_segments = [s for s in source.segments if s.relationship == "cited"]
            context_segments = [
                s for s in source.segments if s.relationship == "context"
            ]
            accepted_ids: set[str] = set()
            accepted_source = None
            for segment in [*cited_segments, *context_segments]:
                if segment.relationship == "context" and not accepted_ids:
                    continue
                trial_ids = {*accepted_ids, segment.segment_id}
                trial_source = replace(
                    source,
                    citations=self._source_citations(cited_by_claim, trial_ids),
                    segments=tuple(
                        s for s in source.segments if s.segment_id in trial_ids
                    ),
                )
                # Reserve the omission notice while admitting complete segments.
                trial = replace(
                    base, sources=tuple([*sources, trial_source]), more_available=True
                )
                if count_tokens(render_memory_evidence(trial)) > budget_tokens:
                    continue
                accepted_ids.add(segment.segment_id)
                accepted_source = trial_source
            if accepted_source is not None:
                sources.append(accepted_source)
        return replace(base, sources=tuple(sources), more_available=True)

    def refresh_sources(
        self, sources: tuple[EvidenceSource, ...]
    ) -> tuple[EvidenceSource, ...]:
        """Refresh only previously shown excerpts and currently valid citation links."""
        refreshed = []
        for prior in sources:
            try:
                source = self.artifacts.get_source(prior.source_id)
            except FileNotFoundError:
                continue
            shown_ids = {segment.segment_id for segment in prior.segments}
            segments = [
                segment
                for segment in source.segments
                if segment.segment_id in shown_ids
            ]
            available_ids = {segment.segment_id for segment in segments}
            cited_by_claim = {}
            for citation in prior.citations:
                try:
                    claim = self.artifacts.get_claim(citation.claim_id)
                except FileNotFoundError:
                    continue
                if claim.status not in {"active", "superseded"}:
                    continue
                cited_by_claim[claim.claim_id] = {
                    sid
                    for provenance in claim.provenance
                    if provenance.source_id == source.source_id
                    for sid in provenance.segment_ids
                    if sid in available_ids
                }
            citations = self._source_citations(cited_by_claim, available_ids)
            if not citations:
                continue
            cited_ids = {sid for citation in citations for sid in citation.segment_ids}
            refreshed.append(
                EvidenceSource(
                    source_id=source.source_id,
                    conversation_time=source.occurred_at or source.recorded_at,
                    citations=citations,
                    segments=tuple(
                        self._evidence_segment(segment, cited_ids)
                        for segment in segments
                    ),
                    status=source.status,
                    retraction_reason=source.retraction_reason,
                    revision=self.artifacts.db.evidence_revision(),
                )
            )
        return tuple(refreshed)

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
