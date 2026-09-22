"""Fit complete evidence records and source segments without reading storage."""

from dataclasses import replace
from typing import Callable

from mycelium.operations import MemoryEvidence, EvidenceSource


def fit_memory_evidence(
    evidence: MemoryEvidence, fits: Callable[[MemoryEvidence], bool]
) -> MemoryEvidence:
    """Fit complete records and transcript segments inside the caller's envelope."""
    if fits(evidence):
        return evidence
    # Reserve the omission notice so adding it cannot overflow the budget.
    selected = MemoryEvidence(
        more_available=True, build_incomplete=evidence.build_incomplete
    )
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
            continue
        accepted = set()
        partial = None
        for segment in source.segments:
            candidate = source_subset(source, accepted | {segment.segment_id})
            if fits(replace(selected, sources=(*selected.sources, candidate))):
                accepted.add(segment.segment_id)
                partial = candidate
        if partial is not None:
            selected = replace(selected, sources=(*selected.sources, partial))
    return selected


def source_subset(source: EvidenceSource, segment_ids: set[str]) -> EvidenceSource:
    """Keep exact segment/citation associations when fitting a source excerpt."""
    return replace(
        source,
        segments=tuple(s for s in source.segments if s.segment_id in segment_ids),
        citations=tuple(
            replace(
                c, segment_ids=tuple(sid for sid in c.segment_ids if sid in segment_ids)
            )
            for c in source.citations
            if any(sid in segment_ids for sid in c.segment_ids)
        ),
    )
