"""Explicit correction and retraction of canonical memory evidence."""

from __future__ import annotations

import uuid
import json
from dataclasses import asdict, dataclass
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
from mycelium.lifecycle_transaction import LifecycleTransaction, mutation_lock
from mycelium.store import WikiStore
from mycelium.structured_outputs import ReplacementMetadata
from mycelium.prompting import render_prompt
from mycelium.correction_review import (
    CorrectionPreview,
    create_draft,
    load_review,
    relative_times,
    resolved_correction_facets,
    review_is_current,
    preview as correction_preview,
)
from mycelium.consolidation import ClaimRouter, placement_from_route
from mycelium.consolidation_models import ClaimEvidence


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
        reason: str = "User correction",
        claim_type: str | None = None,
        predicate: str | None = None,
        temporal_status: str | None = None,
        draft_id: str | None = None,
        time_references: dict[str, str] | None = None,
    ) -> ClaimLifecycleResult | CorrectionPreview:
        return await self._transaction(
            "correct",
            dict(
                claim_id=claim_id,
                text=text,
                reason=reason,
                claim_type=claim_type,
                predicate=predicate,
                temporal_status=temporal_status,
                draft_id=draft_id,
                time_references=time_references,
            ),
        )

    async def retract_source(
        self, source_id: str, *, reason: str
    ) -> ClaimLifecycleResult:
        return await self._transaction(
            "retract", dict(source_id=source_id, reason=reason)
        )

    async def _transaction(
        self, kind: str, inputs: dict
    ) -> ClaimLifecycleResult | CorrectionPreview:
        async with mutation_lock(self.artifacts.root):
            transaction = LifecycleTransaction(
                self.artifacts.root, self.materializer.wiki.wiki_dir
            )
            transaction.recover()
            operation_id = transaction.operation_id(kind, inputs)
            prior = transaction.completed(operation_id)
            if prior is not None:
                if prior.get("status") == "review_required":
                    draft = self.artifacts.db.get(
                        "correction-drafts", prior["draft_id"]
                    )
                    if draft["status"] == "applied":
                        return ClaimLifecycleResult(**draft["result"])
                    if review_is_current(self.artifacts, draft):
                        return correction_preview(draft)
                else:
                    return ClaimLifecycleResult(**prior)
            async with transaction.stage() as (paths, before):
                artifacts = ArtifactStore(self.artifacts.root, db=paths["db"])
                materializer = PageMaterializer(
                    WikiStore(self.materializer.wiki.wiki_dir, db=paths["db"]),
                    artifacts,
                    self.materializer.config,
                )
                service = ClaimLifecycleService(
                    artifacts, materializer, FactResolver(self.resolver.llm, artifacts, self.resolver.config)
                )
                action = (
                    service._correct_claim
                    if kind == "correct"
                    else service._retract_source
                )
                result = await action(**inputs)
                recorded = (
                    {"status": "review_required", "draft_id": result.draft_id}
                    if isinstance(result, CorrectionPreview)
                    else asdict(result)
                )
                transaction.publish(operation_id, paths, before, recorded)
                return result

    async def _correct_claim(
        self,
        claim_id: str,
        text: str,
        *,
        reason: str,
        claim_type: str | None = None,
        predicate: str | None = None,
        temporal_status: str | None = None,
        draft_id: str | None,
        time_references: dict[str, str] | None,
    ) -> ClaimLifecycleResult | CorrectionPreview:
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
        inputs = dict(
            text=corrected_text,
            reason=correction_reason,
            claim_type=claim_type,
            predicate=predicate,
            temporal_status=temporal_status,
        )
        draft = None
        if draft_id is not None:
            draft = load_review(
                self.artifacts, target, draft_id, inputs, time_references
            )
            metadata = ReplacementMetadata.model_validate(draft["metadata"])
        else:
            if time_references is not None:
                raise ValueError("Time choices require a saved correction preview")
            metadata = ReplacementMetadata.model_validate(
                await self.resolver.llm.call_structured(
                    render_prompt("memory/correction.system.jinja"),
                    json.dumps(
                        {
                            "original_statement": target.text,
                            "replacement": corrected_text,
                        }
                    ),
                    ReplacementMetadata,
                    num_predict=2048,
                    debug_label="memory-correction",
                )
            )
            if relative_times(metadata):
                return create_draft(self.artifacts, target, metadata, inputs, now)
        source_time = draft["created_at"] if draft is not None else now
        short_id = uuid.uuid4().hex[:12]
        source_id = f"source-correction-{short_id}"
        segment_id = f"{source_id}#seg-0001"
        replacement_id = f"claim-correction-{short_id}"
        source = SourceDocument(
            source_id=source_id,
            source_type="manual_correction",
            session_id=f"correction-{claim_id}",
            recorded_at=now,
            occurred_at=source_time,
            participants=["user"],
            segments=[
                SourceSegment(
                    segment_id=segment_id,
                    index=0,
                    content=corrected_text,
                    speaker="user",
                    role="user",
                    timestamp=source_time,
                )
            ],
            metadata={
                "corrected_claim_id": claim_id,
                "correction_reason": correction_reason,
            },
        )
        facets, context_refs = resolved_correction_facets(
            metadata, segment_id, draft, time_references
        )
        provenance = [
            ClaimProvenance(
                source_id=source_id,
                segment_ids=[segment_id],
                speaker="user",
                evidence_type="explicit",
            )
        ]
        for context_source_id, context_ids in context_refs.items():
            context_source = self.artifacts.get_source(context_source_id)
            provenance.append(
                ClaimProvenance(
                    source_id=context_source_id,
                    segment_ids=sorted(context_ids),
                    raw_log_entry_id=context_source.raw_log_entry_id,
                    evidence_type="context",
                )
            )
        if draft is not None:
            draft.update(
                status="applied",
                replacement_claim_id=replacement_id,
                choices=time_references,
            )
            self.artifacts.db.put("correction-drafts", draft["draft_id"], draft)
        replacement = MemoryClaim(
            claim_id=replacement_id,
            text=corrected_text,
            about=[item.model_dump() for item in metadata.about],
            provenance=provenance,
            recorded_at=now,
            confidence=1.0,
            facets=facets,
            claim_type=claim_type or metadata.claim_type,
            predicate=predicate if predicate is not None else metadata.predicate,
            evidence_modality="speech",
            temporal_status=temporal_status or metadata.temporal_status,
            dream_disposition="pending",
            dream_disposition_reason="Explicit user correction.",
            dream_disposition_at=now,
        )
        add_claim_link(replacement, "supersedes", target.claim_id)
        add_claim_link(target, "superseded_by", replacement.claim_id)

        self.artifacts.save_source(source)
        self.artifacts.save_episode(
            EpisodeManifest(
                episode_id=f"episode-correction-{short_id}",
                source_id=source_id,
                source_type=source.source_type,
                occurred_at=source.occurred_at,
                participants=list(source.participants),
                segment_ids=[segment_id],
                claim_ids=[replacement_id],
                segment_dispositions=[
                    ExtractionSegmentDisposition(
                        segment_id=segment_id,
                        disposition="claimed",
                        claim_ids=[replacement_id],
                    )
                ],
                extraction_batches=[
                    ExtractionBatchState(
                        batch_id=f"batch-correction-{short_id}",
                        batch_index=1,
                        segment_ids=[segment_id],
                        status="complete",
                        attempt_count=1,
                    )
                ],
                extraction_status="complete",
            )
        )
        target.status = "superseded"
        self.artifacts.save_claim(target)
        self.artifacts.save_claim(replacement)

        affected_entity_ids: set[str] = set()
        placement = self.artifacts.placement_for_claim(claim_id)
        if placement and placement.owner_entity_id:
            affected_entity_ids.add(placement.owner_entity_id)
        routing = await ClaimRouter(self.resolver.llm, self.artifacts, self.materializer.config).route(
            [ClaimEvidence(replacement, source)],
            dream_run_id=f"correction-{short_id}",
        )
        if routing.failures:
            raise ClaimLifecycleConflictError(routing.failures[0].reason)
        for entity in routing.new_entities:
            self.artifacts.save_entity(entity)
        for decision in routing.entity_decisions:
            self.artifacts.save_entity_resolution_decision(decision)
        self.artifacts.replace_automatic_entity_references(
            [route.claim_id for route in routing.routes],
            routing.entity_references,
            dream_run_id=f"correction-{short_id}",
        )
        for route in routing.routes:
            self.artifacts.save_placement(placement_from_route(route))
            replacement.dream_disposition = "routed" if route.placed else "deferred"
            replacement.dream_disposition_reason = route.reason
            if route.owner_entity_id:
                affected_entity_ids.add(route.owner_entity_id)
        self.artifacts.save_claim(replacement)
        reconsider = self._invalidate_reviews({claim_id}, affected_entity_ids)
        pages = await self._rebuild(
            affected_entity_ids,
            incoming_claim_ids={replacement_id, *reconsider},
            operation_id=f"correction-{short_id}",
        )
        result = ClaimLifecycleResult(
            claim_ids=[replacement_id],
            source_ids=[source_id],
            pages_updated=sorted(pages.updated_slugs | pages.created_slugs),
            pages_deleted=sorted(pages.deleted_slugs),
        )
        if draft is not None:
            draft["result"] = asdict(result)
            self.artifacts.db.put("correction-drafts", draft["draft_id"], draft)
        return result

    async def _retract_source(
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

        reconsider = self._invalidate_reviews(
            set(retracted_claim_ids), affected_entity_ids
        )
        pages = await self._rebuild(
            {value for value in affected_entity_ids if value},
            incoming_claim_ids=reconsider,
            operation_id=f"retraction-{source_id}",
        )
        return ClaimLifecycleResult(
            claim_ids=sorted(retracted_claim_ids),
            source_ids=[source_id],
            pages_updated=sorted(pages.updated_slugs | pages.created_slugs),
            pages_deleted=sorted(pages.deleted_slugs),
        )

    def _invalidate_reviews(
        self, inactive_ids: set[str], affected: set[str]
    ) -> set[str]:
        # A pending transition must refer to current canonical claims. Reconsider
        # its surviving incoming evidence after a user changes either side.
        reconsider: set[str] = set()
        for proposal in self.artifacts.list_reconsolidation_proposals(status="pending"):
            if not inactive_ids.intersection(
                [*proposal.incoming_claim_ids, *proposal.target_claim_ids]
            ):
                continue
            proposal.status = "stale"
            proposal.application_error = (
                "Referenced evidence changed through user correction or retraction."
            )
            self.artifacts.save_reconsolidation_proposal(proposal)
            affected.update(proposal.affected_entity_ids)
            reconsider.update(
                cid
                for cid in proposal.incoming_claim_ids
                if self.artifacts.get_claim(cid).status == "active"
            )
        return reconsider

    async def _rebuild(
        self,
        entity_ids: set[str],
        *,
        operation_id: str,
        incoming_claim_ids: set[str] | None = None,
    ):
        resolution = await self.resolver.resolve(
            [],
            affected_entity_ids=entity_ids,
            incoming_claim_ids=incoming_claim_ids or set(),
            dream_run_id=operation_id,
        )
        self._persist_resolution(resolution)
        affected = entity_ids | {eid for proposal in resolution.proposals for eid in proposal.affected_entity_ids}
        return self.materializer.regenerate(affected)

    def _persist_resolution(self, resolution: FactResolutionResult) -> None:
        if resolution.failures:
            raise ClaimLifecycleConflictError(resolution.failures[0].reason)
        for proposal in resolution.proposals:
            self.artifacts.save_reconsolidation_proposal(proposal)
        for placement in resolution.placements:
            self.artifacts.save_placement(placement)
        for fact_id in resolution.deleted_fact_ids:
            self.artifacts.delete_consolidated_fact(fact_id)
        for fact in resolution.facts:
            self.artifacts.save_consolidated_fact(fact)
