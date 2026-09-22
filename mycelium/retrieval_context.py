"""Assemble and refresh evidence from canonical artifacts and exact sources."""

from __future__ import annotations

from collections import defaultdict
from functools import cached_property
from dataclasses import replace
from typing import Callable, Literal

from mycelium.artifacts import (
    ArtifactStore,
    ConsolidatedFact,
    MemoryClaim,
    SourceSegment,
)
from mycelium.budget import count_tokens
from mycelium.evidence_budget import fit_memory_evidence
from mycelium.evidence_rendering import render_memory_evidence
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
    RetrievalError,
    WikiPageReference,
)
from mycelium.store import WikiStore
from mycelium.temporal import temporal_records
from mycelium.retrieval_subjects import claim_subjects


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
        return replace(
            hit,
            claim_text=claim.text,
            memory_tier=self.artifacts.memory_tier(claim.claim_id),
            owner_entity_id=None,
            owner_title=None,
            page_slug=None,
            section_key=None,
        )

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
            if hit.claim_id in seen or len(selected) >= limit:
                continue
            selected.append(hit)
            seen.add(hit.claim_id)
        return selected

    def build(
        self,
        hits: list[ClaimSearchHit],
        *,
        budget_tokens: int,
        more_available: bool = False,
        record_limit: int | None = None,
    ) -> MemoryEvidence:
        evidence = replace(
            self.build_interpretation(hits), more_available=more_available
        )
        return self.attach_cited_sources(
            evidence,
            budget_tokens=budget_tokens,
            include_context=False,
            record_limit=record_limit,
        )

    def attach_cited_sources(
        self,
        evidence: MemoryEvidence,
        *,
        budget_tokens: int,
        include_context: bool,
        known_evidence: MemoryEvidence | None = None,
        record_limit: int | None = None,
    ) -> MemoryEvidence:
        """Fit complete interpretations, then add their exact cited source segments.

        When evidence is already known, only the added workspace size is charged.
        """
        from mycelium.memory_workspace import merge_memory_evidence

        known_tokens = (
            count_tokens(render_memory_evidence(known_evidence))
            if known_evidence is not None
            else 0
        )

        def fits(trial):
            if record_limit is not None and len(trial.records) > record_limit:
                return False
            if known_evidence is not None:
                return (
                    count_tokens(
                        render_memory_evidence(
                            merge_memory_evidence(known_evidence, trial)
                        )
                    )
                    - known_tokens
                    <= budget_tokens
                )
            return count_tokens(render_memory_evidence(trial)) <= budget_tokens

        # Retain canonical interpretation state before adding original wording.
        # Only exact citations of records that fit may contribute excerpts.
        evidence = fit_memory_evidence(evidence, fits)
        claims = [self.artifacts.get_claim(cid) for cid in evidence.claim_ids]
        return fit_memory_evidence(
            self._structured_source_evidence(
                claims,
                fits=fits,
                base=evidence,
                include_context=include_context,
                known_evidence=known_evidence,
            ),
            fits,
        )

    def build_selected_evidence(
        self,
        candidates: MemoryEvidence,
        selected_record_ids: tuple[str, ...],
        *,
        budget_tokens: int,
        record_limit: int,
    ) -> MemoryEvidence:
        """Carry the selected original records into answering with their sources."""
        records_by_id = {record.record_id: record for record in candidates.records}
        selected_records = tuple(
            records_by_id[record_id] for record_id in selected_record_ids
        )
        return self.attach_cited_sources(
            replace(candidates, records=selected_records, sources=()),
            budget_tokens=budget_tokens,
            include_context=False,
            record_limit=record_limit,
        )

    def page_references(
        self, evidence: MemoryEvidence
    ) -> tuple[WikiPageReference, ...]:
        references = []
        entity_ids = dict.fromkeys(
            entity_id
            for record in evidence.records
            for entity_id in (
                record.subject_entity_id,
                *(s.entity_id for s in record.subjects),
            )
            if entity_id is not None
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
        self,
        claim_ids: list[str],
        *,
        budget_tokens: int,
        known_evidence: MemoryEvidence | None = None,
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
        records = self.build_interpretation(
            [
                ClaimSearchHit(
                    c.claim_id, c.text, c.status, None, None, None, None, None
                )
                for c in claims.values()
            ]
        )
        # Carry interpretation status with transcript excerpts, so inspecting an
        # older source cannot silently revive a superseded interpretation.
        return self.attach_cited_sources(
            records,
            budget_tokens=budget_tokens,
            include_context=True,
            known_evidence=known_evidence,
        )

    def refresh_evidence(
        self, evidence: MemoryEvidence, *, budget_tokens: int
    ) -> MemoryEvidence:
        """Rebase a workspace on current canonical state before a tool result."""
        from mycelium.memory_workspace import merge_memory_evidence

        hits = []
        claim_ids = dict.fromkeys(
            [
                *evidence.claim_ids,
                *(
                    citation.claim_id
                    for source in evidence.sources
                    for citation in source.citations
                ),
            ]
        )
        for claim_id in claim_ids:
            try:
                claim = self.artifacts.get_claim(claim_id)
            except FileNotFoundError:
                continue
            if claim.status not in {"active", "superseded"}:
                continue
            hits.append(
                ClaimSearchHit(
                    claim_id, claim.text, claim.status, None, None, None, None, None
                )
            )
        # A refresh updates interpretation and previously inspected excerpts. It
        # must not discover more source text or consume the exploration allowance.
        records = self.build_interpretation(
            hits,
            fact_ids={r.record_id for r in evidence.records if r.record_type == "fact"},
        )
        shown_ids = {r.record_id for r in evidence.records}
        surviving_views = {
            r.record_id for r in records.records if r.record_type == "fact"
        }
        # When a displayed view loses valid support, carry the remaining claim
        # states instead. Otherwise its old sources could outlive the correction.
        shown_ids.update(
            cid
            for r in evidence.records
            if r.record_type == "fact" and r.record_id not in surviving_views
            for cid in r.claim_ids
        )
        records = replace(
            records,
            records=tuple(r for r in records.records if r.record_id in shown_ids),
        )

        return fit_memory_evidence(
            merge_memory_evidence(
                records,
                MemoryEvidence(
                    sources=self.refresh_sources(evidence.sources),
                    more_available=evidence.more_available,
                ),
            ),
            lambda trial: count_tokens(render_memory_evidence(trial)) <= budget_tokens,
        )

    def build_interpretation(
        self, hits: list[ClaimSearchHit], *, fact_ids: set[str] | None = None
    ) -> MemoryEvidence:
        """Read canonical matches and optional supported views, without source excerpts."""
        hits = [
            current for hit in hits if (current := self.current_hit(hit)) is not None
        ]
        claims = {hit.claim_id: self.artifacts.get_claim(hit.claim_id) for hit in hits}
        records = []
        for claim in claims.values():
            records.append(
                self._structured_record(
                    record_id=claim.claim_id,
                    record_type="claim",
                    statement=claim.text,
                    subject_entity_id=None,
                    subject_name=None,
                    claim_ids=(claim.claim_id,),
                    state="superseded"
                    if claim.status == "superseded"
                    else self.artifacts.memory_tier(claim.claim_id),
                    claims=[claim],
                )
            )

        # Views provide optional context. They cannot replace or precede a match.
        facts: dict[str, ConsolidatedFact] = {}
        for claim in claims.values():
            for fact in self._facts_for_claim(claim.claim_id):
                if fact_ids is None or fact.fact_id in fact_ids:
                    facts.setdefault(fact.fact_id, fact)
        for fact in facts.values():
            members = []
            for cid in fact.member_claim_ids:
                try:
                    member = self.artifacts.get_claim(cid)
                except FileNotFoundError:
                    break
                if member.status != "active":
                    break
                members.append(member)
            else:
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
        subjects = (
            claim_subjects(self.artifacts, claim_ids[0])
            if record_type == "claim"
            else ()
        )
        primary = {
            s.entity_id: s
            for s in subjects
            if s.role in {"subject", "identity_subject"}
        }
        if len(primary) == 1:
            subject = next(iter(primary.values()))
            subject_entity_id, subject_name = subject.entity_id, subject.name
        return EvidenceRecord(
            subjects=subjects,
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
                if record_type == "fact"
            ),
            reviews=tuple(
                {
                    r.proposal_id: r
                    for cid in claim_ids
                    for r in self.reviews_by_claim.get(cid, [])
                }.values()
            ),
            uncertainty=tuple(
                dict.fromkeys(
                    f"Identity unresolved; optional review {decision.decision_id}"
                    for decision in self.artifacts.list_entity_resolution_decisions(
                        review_state="review_required"
                    )
                    if set(claim_ids) & set(decision.supporting_claim_ids)
                )
            )
            + self._source_uncertainty(claims),
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
        fits: Callable[[MemoryEvidence], bool],
        base: MemoryEvidence,
        include_context: bool,
        known_evidence: MemoryEvidence | None = None,
    ) -> MemoryEvidence:
        cited_by_source: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for claim in claims:
            for provenance in claim.provenance:
                cited_by_source[provenance.source_id][claim.claim_id].update(
                    provenance.segment_ids
                )

        known_sources = (
            {s.source_id: s for s in known_evidence.sources} if known_evidence else {}
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
            if source_id in known_sources:
                selected_ids -= {
                    s.segment_id for s in known_sources[source_id].segments
                }
            if not selected_ids:
                continue
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
        if fits(complete):
            return complete

        sources: list[EvidenceSource] = []
        for source_evidence in available:
            cited_by_claim = {
                citation.claim_id: set(citation.segment_ids)
                for citation in source_evidence.citations
            }
            cited_segments = [
                s for s in source_evidence.segments if s.relationship == "cited"
            ]
            context_segments = [
                s for s in source_evidence.segments if s.relationship == "context"
            ]
            accepted_ids: set[str] = set()
            accepted_source = None
            for evidence_segment in [*cited_segments, *context_segments]:
                if (
                    evidence_segment.relationship == "context"
                    and not accepted_ids
                    and source_evidence.source_id not in known_sources
                ):
                    continue
                trial_ids = {*accepted_ids, evidence_segment.segment_id}
                trial_source = replace(
                    source_evidence,
                    citations=self._source_citations(cited_by_claim, trial_ids),
                    segments=tuple(
                        s for s in source_evidence.segments if s.segment_id in trial_ids
                    ),
                )
                # Reserve the omission notice while admitting complete segments.
                trial = replace(
                    base, sources=tuple([*sources, trial_source]), more_available=True
                )
                if not fits(trial):
                    continue
                accepted_ids.add(evidence_segment.segment_id)
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
                    if sid in available_ids and sid in citation.segment_ids
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
