"""Entity, fact, organization, and reconsolidation curation endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from mycelium.lifecycle_transaction import LifecycleTransaction, mutation_lock

from mycelium.claim_lifecycle import (
    ClaimLifecycleConflictError,
    ClaimLifecycleService,
)
from mycelium.organization import (
    EntityCurationService,
    FactCurationService,
    IdentityReviewService,
    OrganizationReviewService,
)
from mycelium.reconsolidation import ReconsolidationReviewService, ReviewConflictError
from server.api.memory_contracts import (
    ClaimCorrectionRequest,
    EntityMergeRequest,
    EntitySplitRequest,
    EntityUpdateRequest,
    FactGroupRequest,
    FactMoveRequest,
    FactSplitRequest,
    IdentityReviewRequest,
    PlacementUpdateRequest,
    ProposalReviewRequest,
    SourceRetractionRequest,
)
from server.runtime import get_mem

async def memory_mutation():
    mem = get_mem()
    async with mutation_lock(mem.artifacts.root):
        LifecycleTransaction(mem.artifacts.root, mem.wiki.wiki_dir).recover()
        yield


router = APIRouter(dependencies=[Depends(memory_mutation)])


def _review_service():
    mem = get_mem()
    return ReconsolidationReviewService(
        mem.artifacts,
        mem.consolidator.materializer,
        mem.consolidator.views,
    )


def _curation_service():
    mem = get_mem()
    return EntityCurationService(
        mem.artifacts, mem.wiki, mem.consolidator.materializer
    )


def _fact_curation_service():
    mem = get_mem()
    return FactCurationService(mem.artifacts, mem.consolidator.materializer)


def _claim_lifecycle_service():
    mem = get_mem()
    return ClaimLifecycleService(
        mem.artifacts,
        mem.consolidator.materializer,
        mem.consolidator.views,
    )


def _fact_curation_response(result):
    return {
        "facts": [asdict(fact) for fact in result.facts],
        "pages_updated": result.pages_updated,
    }


def _curation_response(result):
    if result is None:
        return {"entity": None, "pages_updated": [], "pages_deleted": []}
    return {
        "entity": asdict(result.entity),
        "pages_updated": result.pages_updated,
        "pages_deleted": result.pages_deleted,
    }


def _claim_lifecycle_response(result):
    return asdict(result)


@router.post("/claims/{claim_id}/correct")
async def correct_claim(claim_id: str, req: ClaimCorrectionRequest):
    try:
        result = await _claim_lifecycle_service().correct_claim(
            claim_id,
            req.text,
            reason=req.reason,
            claim_type=req.claim_type,
            predicate=req.predicate,
            temporal_status=req.temporal_status,
            draft_id=req.draft_id,
            time_references=req.time_references,
        )
        return _claim_lifecycle_response(result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claim not found") from exc
    except (ClaimLifecycleConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/sources/{source_id}/retract")
async def retract_source(source_id: str, req: SourceRetractionRequest):
    try:
        result = await _claim_lifecycle_service().retract_source(
            source_id, reason=req.reason
        )
        return _claim_lifecycle_response(result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source not found") from exc
    except (ClaimLifecycleConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/entities/{entity_id}")
async def update_entity(entity_id: str, req: EntityUpdateRequest):
    try:
        return _curation_response(
            _curation_service().update_entity(
                entity_id,
                title=req.title,
                slug=req.slug,
                aliases=req.aliases,
                entity_type=req.entity_type,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Entity not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/archive")
async def archive_entity(entity_id: str):
    try:
        return _curation_response(_curation_service().set_status(entity_id, "archived"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Entity not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/reactivate")
async def reactivate_entity(entity_id: str):
    try:
        return _curation_response(_curation_service().set_status(entity_id, "active"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Entity not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/merge")
async def merge_entity(entity_id: str, req: EntityMergeRequest):
    try:
        return _curation_response(
            _curation_service().merge(entity_id, req.target_entity_id)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Entity not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/split")
async def split_entity(entity_id: str, req: EntitySplitRequest):
    try:
        return _curation_response(
            _curation_service().split(
                entity_id,
                req.claim_ids,
                title=req.title,
                entity_type=req.entity_type,
                aliases=req.aliases,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Entity or claim not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/placements/{claim_id}")
async def update_placement(claim_id: str, req: PlacementUpdateRequest):
    try:
        return _curation_response(
            _curation_service().move_claim(
                claim_id,
                req.owner_entity_id,
                req.section_key,
                linked_entity_ids=req.linked_entity_ids,
                reason=req.reason,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Claim or entity not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/facts/{fact_id}/move")
async def move_fact(fact_id: str, req: FactMoveRequest):
    try:
        return _fact_curation_response(
            _fact_curation_service().move(
                fact_id,
                req.owner_entity_id,
                req.section_key,
                linked_entity_ids=req.linked_entity_ids,
                reason=req.reason,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Fact, claim, or entity not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/facts/group")
async def group_facts(req: FactGroupRequest):
    try:
        return _fact_curation_response(
            _fact_curation_service().group(req.fact_ids, req.text, reason=req.reason)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Fact not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/facts/{fact_id}/split")
async def split_fact(fact_id: str, req: FactSplitRequest):
    try:
        return _fact_curation_response(
            _fact_curation_service().split(
                fact_id,
                [group.model_dump() for group in req.groups],
                reason=req.reason,
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Fact not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/organization/proposals/{proposal_id}/{decision}")
async def review_organization_proposal(
    proposal_id: str, decision: str, req: ProposalReviewRequest
):
    mem = get_mem()
    try:
        proposal = OrganizationReviewService(mem.artifacts, _curation_service()).review(
            proposal_id, decision, reviewer_note=req.reviewer_note
        )
        return asdict(proposal)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Organization proposal not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/identity-decisions/{decision_id}/{action}")
async def review_identity_decision(
    decision_id: str, action: str, req: IdentityReviewRequest
):
    mem = get_mem()
    try:
        previous = mem.artifacts.get_entity_resolution_decision(decision_id)
        record = IdentityReviewService(mem.artifacts).review(
            decision_id,
            action,
            reviewer_note=req.reviewer_note,
            entity_id=req.entity_id,
            entity_type=req.entity_type,
            title=req.title,
            scope=req.scope,
            page_state=req.page_state,
            parent_entity_id=req.parent_entity_id,
            claim_texts=req.claim_texts,
        )
        try:
            pages = await mem.consolidator.views.refresh_views(
                set(previous.supporting_claim_ids) | set(record.supporting_claim_ids),
                context_ids=[], entity_ids={eid for eid in (previous.entity_id, record.entity_id) if eid},
                run_id=f"identity-review-{decision_id}-{record.reviewed_at}")
            reroute = {"status": "complete", "pages_updated": sorted(pages.created_slugs | pages.updated_slugs)}
        except Exception as exc:
            # The explicit review remains durable; pending claims allow a later
            # Build to retry presentation without losing the user's correction.
            reroute = {"status": "pending", "error": f"{type(exc).__name__}: {exc}"}
        mem.db.publish()
        return {"decision": asdict(record), "reroute": reroute}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Identity decision not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _review_response(result):
    return {
        "proposal": asdict(result.proposal),
        "pages_updated": result.pages_updated,
        "pages_deleted": result.pages_deleted,
    }


@router.post("/reconsolidation/proposals/{proposal_id}/approve")
async def approve_reconsolidation_proposal(
    proposal_id: str, req: ProposalReviewRequest
):
    try:
        return _review_response(await _review_service().approve(
            proposal_id, reviewer_note=req.reviewer_note
        ))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Reconsolidation proposal not found"
        ) from exc
    except ReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/reconsolidation/proposals/{proposal_id}/reject")
async def reject_reconsolidation_proposal(proposal_id: str, req: ProposalReviewRequest):
    try:
        return _review_response(await _review_service().reject(
            proposal_id, reviewer_note=req.reviewer_note
        ))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Reconsolidation proposal not found"
        ) from exc
    except ReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
