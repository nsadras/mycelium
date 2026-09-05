"""Explicit correction and retraction of canonical memory evidence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    ExtractionBatchState,
    ExtractionSegmentDisposition,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.facts import FactResolutionResult, FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.reconsolidation import add_claim_link


class ClaimLifecycleConflictError(RuntimeError):
    """The requested canonical-memory change is no longer applicable."""


@dataclass(frozen=True)
class ClaimLifecycleResult:
    claim_ids: list[str]
    source_ids: list[str]
    pages_updated: list[str]
    pages_deleted: list[str]


class ClaimLifecycleService:
    """Apply user-authorized evidence changes and repair derived memory."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        materializer: PageMaterializer,
        resolver: FactResolver,
    ) -> None:
        self.artifacts = artifacts
        self.materializer = materializer
        self.resolver = resolver

    async def correct_claim(
        self,
        claim_id: str,
        text: str,
        *,
        reason: str,
        claim_type: str | None = None,
        predicate: str | None = None,
        temporal_status: str | None = None,
    ) -> ClaimLifecycleResult:
        target = self.artifacts.get_claim(claim_id)
        if target.status != "active":
            raise ClaimLifecycleConflictError("Only active claims can be corrected")
        corrected_text = " ".join(text.split()).strip()
        if not corrected_text:
            raise ValueError("A correction requires replacement claim text")
        correction_reason = " ".join(reason.split()).strip()
        if not correction_reason:
            raise ValueError("A correction requires a reason")

        now = datetime.now().astimezone().isoformat()
        short_id = uuid.uuid4().hex[:12]
        source_id = f"source-correction-{short_id}"
        segment_id = f"{source_id}#seg-0001"
        replacement_id = f"claim-correction-{short_id}"
        source = SourceDocument(
            source_id=source_id,
            source_type="manual_correction",
            session_id=f"correction-{claim_id}",
            recorded_at=now,
            occurred_at=now,
            participants=["user"],
            segments=[SourceSegment(
                segment_id=segment_id,
                index=0,
                content=corrected_text,
                speaker="user",
                role="user",
            )],
            metadata={
                "corrected_claim_id": claim_id,
                "correction_reason": correction_reason,
            },
        )
        replacement = MemoryClaim(
            claim_id=replacement_id,
            text=corrected_text,
            about=[dict(item) for item in target.about],
            provenance=[ClaimProvenance(
                source_id=source_id,
                segment_ids=[segment_id],
                speaker="user",
                evidence_type="explicit",
            )],
            recorded_at=now,
            confidence=1.0,
            slot=target.slot,
            facets=dict(target.facets),
            claim_type=claim_type or target.claim_type,
            predicate=predicate if predicate is not None else target.predicate,
            evidence_modality="speech",
            temporal_status=temporal_status or target.temporal_status,
            dream_disposition=(
                "routed"
                if (
                    (placement := self.artifacts.placement_for_claim(claim_id))
                    and placement.status == "placed"
                )
                else "pending"
            ),
            dream_disposition_reason="Explicit user correction.",
            dream_disposition_at=now,
        )
        add_claim_link(replacement, "supersedes", target.claim_id)
        add_claim_link(target, "superseded_by", replacement.claim_id)

        self.artifacts.save_source(source)
        self.artifacts.save_episode(EpisodeManifest(
            episode_id=f"episode-correction-{short_id}",
            source_id=source_id,
            source_type=source.source_type,
            occurred_at=source.occurred_at,
            participants=list(source.participants),
            segment_ids=[segment_id],
            claim_ids=[replacement_id],
            segment_dispositions=[ExtractionSegmentDisposition(
                segment_id=segment_id,
                disposition="claimed",
                claim_ids=[replacement_id],
            )],
            extraction_batches=[ExtractionBatchState(
                batch_id=f"batch-correction-{short_id}",
                batch_index=1,
                segment_ids=[segment_id],
                status="complete",
                attempt_count=1,
            )],
            extraction_status="complete",
        ))
        target.status = "superseded"
        self.artifacts.save_claim(target)
        self.artifacts.save_claim(replacement)

        affected_entity_ids: set[str] = set()
        if placement and placement.owner_entity_id:
            affected_entity_ids.add(placement.owner_entity_id)
            self.artifacts.save_placement(replace(
                placement,
                claim_id=replacement_id,
                reason=f"Explicit correction of {claim_id}.",
                created_at=now,
                updated_at=now,
            ))
        pages = await self._rebuild(
            affected_entity_ids,
            operation_id=f"correction-{short_id}",
        )
        return ClaimLifecycleResult(
            claim_ids=[replacement_id],
            source_ids=[source_id],
            pages_updated=sorted(pages.updated_slugs | pages.created_slugs),
            pages_deleted=sorted(pages.deleted_slugs),
        )

    async def retract_source(
        self, source_id: str, *, reason: str
    ) -> ClaimLifecycleResult:
        source = self.artifacts.get_source(source_id)
        retraction_reason = " ".join(reason.split()).strip()
        if not retraction_reason:
            raise ValueError("A source retraction requires a reason")
        now = datetime.now().astimezone().isoformat()
        if source.status == "active":
            source.status = "retracted"
            source.retracted_at = now
            source.retraction_reason = retraction_reason
            self.artifacts.save_source(source)

        affected_claims = self.artifacts.claims_for_sources(
            [source_id], active_only=False
        )
        affected_entity_ids = {
            placement.owner_entity_id
            for claim in affected_claims
            if (placement := self.artifacts.placement_for_claim(claim.claim_id))
            and placement.owner_entity_id
        }
        retracted_claim_ids: list[str] = []
        for claim in affected_claims:
            if claim.status != "active":
                continue
            supporting_sources = {
                provenance.source_id for provenance in claim.provenance
            }
            has_active_support = any(
                self.artifacts.get_source(supporting_source_id).status == "active"
                for supporting_source_id in supporting_sources
            )
            if has_active_support:
                continue
            claim.status = "retracted"
            claim.dream_disposition_reason = (
                "All supporting sources have been retracted."
            )
            claim.dream_disposition_at = now
            self.artifacts.save_claim(claim)
            retracted_claim_ids.append(claim.claim_id)

        pages = await self._rebuild(
            {value for value in affected_entity_ids if value},
            operation_id=f"retraction-{source_id}",
        )
        return ClaimLifecycleResult(
            claim_ids=sorted(retracted_claim_ids),
            source_ids=[source_id],
            pages_updated=sorted(pages.updated_slugs | pages.created_slugs),
            pages_deleted=sorted(pages.deleted_slugs),
        )

    async def _rebuild(self, entity_ids: set[str], *, operation_id: str):
        resolution = await self.resolver.resolve(
            [],
            affected_entity_ids=entity_ids,
            incoming_claim_ids=set(),
            dream_run_id=operation_id,
        )
        self._persist_resolution(resolution)
        return self.materializer.regenerate(entity_ids)

    def _persist_resolution(self, resolution: FactResolutionResult) -> None:
        if resolution.failures:
            raise ClaimLifecycleConflictError(resolution.failures[0].reason)
        for placement in resolution.placements:
            self.artifacts.save_placement(placement)
        for fact_id in resolution.deleted_fact_ids:
            self.artifacts.delete_consolidated_fact(fact_id)
        for fact in resolution.facts:
            self.artifacts.save_consolidated_fact(fact)
