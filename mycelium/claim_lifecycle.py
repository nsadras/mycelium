"""Explicit correction and retraction of canonical memory evidence."""

from __future__ import annotations

import uuid
import json
from dataclasses import asdict, dataclass, replace
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
from mycelium.views import ViewOrganizer
from mycelium.retention import Retainer
from mycelium import memory_contract
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


class ClaimLifecycleConflictError(RuntimeError):
    """The requested canonical-memory change is no longer applicable."""


@dataclass(frozen=True)
class ClaimLifecycleResult:
    claim_ids: list[str]
    source_ids: list[str]
    pages_updated: list[str]
    pages_deleted: list[str]


def correct_identity_wording(artifacts, decision, texts, now):
    """Apply user-reviewed identity wording, retaining original time anchors.

    This is an identity-only edit. Other factual/date corrections use correct_claim
    and its date preview. No model decides the identity selected by the user.
    The caller owns the transaction, including the identity reference changes.
    """
    if not texts.keys() <= set(decision.supporting_claim_ids):
        raise ValueError("Wording changes must belong to the reviewed identity")
    replacements = {}
    for cid, text in texts.items():
        target = artifacts.get_claim(cid)
        text = text.strip()
        if target.status != "active" or not text:
            raise ValueError("Identity wording requires an active claim and nonempty text")
        if text == target.text:
            continue
        suffix = uuid.uuid4().hex[:12]
        source_id, claim_id = f"source-identity-{suffix}", f"claim-identity-{suffix}"
        segment_id = source_id + "#seg-0001"
        artifacts.save_source(SourceDocument(source_id, "manual_correction", f"identity-{decision.decision_id}",
            now, now, ["user"], [SourceSegment(segment_id, 0, text, speaker="user", role="user")],
            metadata={"identity_decision_id": decision.decision_id, "corrected_claim_id": cid,
                      "correction_scope": "identity_only"}))
        replacement = replace(target, claim_id=claim_id, text=text, about=[], recorded_at=now,
            provenance=[ClaimProvenance(source_id, [segment_id], speaker="user"),
                        *[replace(p, evidence_type="context") for p in target.provenance]],
            links=[{"relation": "supersedes", "target": cid}], confidence=1.0,
            dream_disposition="pending", dream_disposition_reason="Explicit identity correction",
            dream_run_id=None, dream_disposition_at=now)
        artifacts.save_claim(replacement)
        for ref in artifacts.list_entity_references(claim_id=cid, status="active"):
            artifacts.save_entity_reference(replace(ref, reference_id=f"ref-{uuid.uuid4().hex[:12]}",
                                                   claim_id=claim_id, created_at=now))
        add_claim_link(target, "superseded_by", claim_id)
        target.status = "superseded"
        artifacts.save_claim(target)
        artifacts.save_episode(EpisodeManifest(f"episode-identity-{suffix}", source_id, "manual_correction",
            now, ["user"], [segment_id], claim_ids=[claim_id], extraction_status="complete",
            segment_dispositions=[ExtractionSegmentDisposition(segment_id, "claimed", [claim_id])],
            extraction_batches=[ExtractionBatchState(f"batch-identity-{suffix}", 0, [segment_id], status="complete")]))
        replacements[cid] = claim_id
    for item in artifacts.list_entity_resolution_decisions():
        if replacements.keys() & set(item.supporting_claim_ids):
            item.supporting_claim_ids = [replacements.get(cid, cid) for cid in item.supporting_claim_ids]
            item.identity_evidence_claim_ids = [replacements.get(cid, cid) for cid in item.identity_evidence_claim_ids]
            # Keep both the original source and the user's correction inspectable.
            claims = [artifacts.get_claim(cid) for cid in item.supporting_claim_ids]
            item.source_ids = sorted({p.source_id for c in claims for p in c.provenance} | set(item.source_ids))
            item.supporting_segment_ids = sorted({sid for c in claims for p in c.provenance for sid in p.segment_ids}
                                                | set(item.supporting_segment_ids))
            artifacts.save_entity_resolution_decision(item)
    for proposal in artifacts.list_reconsolidation_proposals(status="pending"):
        if replacements.keys() & set(proposal.incoming_claim_ids + proposal.target_claim_ids):
            proposal.status = "stale"
            proposal.application_error = "Identity wording changed referenced evidence"
            artifacts.save_reconsolidation_proposal(proposal)


class ClaimLifecycleService:
    """Apply user-authorized evidence changes and repair derived memory."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        materializer: PageMaterializer,
        views: ViewOrganizer,
    ) -> None:
        self.artifacts = artifacts
        self.materializer = materializer
        self.views = views

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
                    artifacts, materializer, ViewOrganizer(self.views.llm, artifacts, materializer, self.views.config)
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
                await self.views.llm.call_structured(
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
        affected_entity_ids = self.artifacts.entities_for_claims({claim_id})
        context_ids = {claim_id} | {cid for fact in self.artifacts.facts_for_claim(claim_id) for cid in fact.member_claim_ids}
        retainer = Retainer(self.views.llm, self.artifacts, self.views.config)
        payload = await retainer.prepare_retention_input(source, source.segments, f"correction-{short_id}", prior_claim_ids=sorted(context_ids))
        retained = await memory_contract.retain(self.views.llm, payload)
        # Validate against the original evidence before this transaction replaces
        # it. The model may correctly propose the very replacement being reviewed.
        retainer.save_retained_memories(source, f"correction-{short_id}", payload, retained, replacement=replacement)
        target.status = "superseded"
        self.artifacts.save_claim(target)
        reconsider = self._invalidate_reviews({claim_id}, affected_entity_ids)
        pages = await self.views.refresh_views(
            {claim_id, replacement_id, *reconsider}, context_ids=context_ids,
            entity_ids=affected_entity_ids, run_id=f"correction-{short_id}",
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
        affected_entity_ids = self.artifacts.entities_for_claims({c.claim_id for c in affected_claims})
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
        for cid in reconsider:
            claim = self.artifacts.get_claim(cid)
            claim.dream_disposition = "pending"
            self.artifacts.save_claim(claim)
        pages = self.materializer.regenerate(affected_entity_ids)
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
