"""Entity, fact, organization, and reconsolidation curation endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

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
    FactEditRequest,
    FactGroupRequest,
    FactMoveRequest,
    FactSplitRequest,
    IdentityReviewRequest,
    PlacementUpdateRequest,
    ProposalReviewRequest,
    SourceRetractionRequest,
)
from server.runtime import get_mem, run_dream as run_dream_process

router = APIRouter()


def _review_service():
    mem = get_mem()
    return ReconsolidationReviewService(
        mem.artifacts,
        mem.dream_process.materializer,
        mem.dream_process.fact_resolver,
    )


def _curation_service():
    mem = get_mem()
    return EntityCurationService(
        mem.artifacts, mem.wiki, mem.dream_process.materializer
    )


def _fact_curation_service():
    mem = get_mem()
    return FactCurationService(mem.artifacts, mem.dream_process.materializer)


def _claim_lifecycle_service():
    mem = get_mem()
    return ClaimLifecycleService(
        mem.artifacts,
        mem.dream_process.materializer,
        mem.dream_process.fact_resolver,
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


@router.patch("/facts/{fact_id}")
async def edit_fact(fact_id: str, req: FactEditRequest):
    try:
        return _fact_curation_response(
            _fact_curation_service().edit(fact_id, req.text, reason=req.reason)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Fact not found") from exc
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
        )
        reroute = await run_dream_process()
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
