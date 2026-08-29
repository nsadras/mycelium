from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field

from server.runtime import (
    clear_memory_store,
    clear_wiki_store,
    flush_idle_episodes,
    flush_session_episode,
    get_mem,
    load_meta,
    run_dream as run_dream_process,
    run_dream_if_ready as run_dream_if_ready_process,
)
from mycelium.reconsolidation import ReconsolidationReviewService, ReviewConflictError
from mycelium.organization import (
    EntityCurationService,
    FactCurationService,
    OrganizationReviewService,
)

router = APIRouter()


class FlushRequest(BaseModel):
    session_id: str | None = None


class IdleFlushRequest(BaseModel):
    idle_minutes: int = 20
    max_turns: int = 25
    force: bool = False


class ProposalReviewRequest(BaseModel):
    reviewer_note: str | None = None


class EntityUpdateRequest(BaseModel):
    title: str | None = None
    slug: str | None = None
    aliases: list[str] | None = None
    entity_type: str | None = None


class EntityMergeRequest(BaseModel):
    target_entity_id: str


class EntitySplitRequest(BaseModel):
    claim_ids: list[str] = Field(min_length=1)
    title: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)


class PlacementUpdateRequest(BaseModel):
    owner_entity_id: str | None = None
    section_key: str | None = None
    linked_entity_ids: list[str] = Field(default_factory=list)
    reason: str = "Manual wiki organization"


class FactEditRequest(BaseModel):
    text: str = Field(min_length=1)
    reason: str = "Manual fact correction"


class FactMoveRequest(BaseModel):
    owner_entity_id: str
    section_key: str
    linked_entity_ids: list[str] = Field(default_factory=list)
    reason: str = "Manual fact organization"


class FactGroupRequest(BaseModel):
    fact_ids: list[str] = Field(min_length=2)
    text: str = Field(min_length=1)
    reason: str = "Manual fact grouping"


class FactSplitGroup(BaseModel):
    claim_ids: list[str] = Field(min_length=1)
    text: str = Field(min_length=1)


class FactSplitRequest(BaseModel):
    groups: list[FactSplitGroup] = Field(min_length=2)
    reason: str = "Manual fact split"


def wiki_page_response(page):
    return {
        "slug": page.slug,
        "title": page.title,
        "content": page.content,
        "version": page.version,
        "confidence": page.confidence,
        "page_type": page.page_type,
        "tags": page.tags,
        "source_log_entries": page.source_log_entries,
        "related": [{"target": r.target, "relation": r.relation} for r in page.related],
        "update_log": [{"version": u.version, "reason": u.reason, "date": u.date.isoformat()} for u in page.update_log],
        "entity_id": page.entity_id,
        "entity_status": page.entity_status,
        "aliases": page.aliases,
        "sections": page.sections,
    }


def _stored_memory_file(path: Path) -> dict[str, str]:
    return {
        "filename": path.name,
        "content": path.read_text(encoding="utf-8"),
    }


def _artifact_integrity(mem) -> dict:
    sources = mem.artifacts.list_sources()
    episodes = mem.artifacts.list_episodes()
    claims = mem.artifacts.list_claims()
    wiki_pages = mem.wiki.list_all()
    pages = {page.slug for page in wiki_pages}
    logs = {entry.entry_id for entry in mem.log_store.list_entries(days=None)}

    source_by_id = {source.source_id: source for source in sources}
    episode_source_ids = {episode.source_id for episode in episodes}
    claim_by_id = {claim.claim_id: claim for claim in claims}
    proposals = mem.artifacts.list_reconsolidation_proposals()
    entities = {entity.entity_id: entity for entity in mem.artifacts.list_entities()}
    placements = {item.claim_id: item for item in mem.artifacts.list_placements()}
    facts = mem.artifacts.list_consolidated_facts()

    issues = {
        "sources_without_episode": sorted(
            source_id for source_id in source_by_id if source_id not in episode_source_ids
        ),
        "episodes_missing_source": sorted(
            episode.episode_id for episode in episodes if episode.source_id not in source_by_id
        ),
        "episodes_missing_claims": sorted(
            f"{episode.episode_id}:{claim_id}"
            for episode in episodes
            for claim_id in episode.claim_ids
            if claim_id not in claim_by_id
        ),
        "claims_missing_episode": sorted(
            claim.claim_id
            for claim in claims
            if claim.provenance
            and not any(provenance.source_id in episode_source_ids for provenance in claim.provenance)
        ),
        "claims_missing_provenance": sorted(
            claim.claim_id for claim in claims if not claim.provenance
        ),
        "claims_missing_source": sorted(
            f"{claim.claim_id}:{provenance.source_id}"
            for claim in claims
            for provenance in claim.provenance
            if provenance.source_id not in source_by_id
        ),
        "claims_missing_segments": sorted(
            f"{claim.claim_id}:{segment_id}"
            for claim in claims
            for provenance in claim.provenance
            if provenance.source_id in source_by_id
            for segment_id in provenance.segment_ids
            if segment_id
            not in {
                segment.segment_id for segment in source_by_id[provenance.source_id].segments
            }
        ),
        "placements_missing_claims": sorted(
            claim_id for claim_id in placements if claim_id not in claim_by_id
        ),
        "placements_missing_entities": sorted(
            f"{placement.claim_id}:{placement.owner_entity_id}"
            for placement in placements.values()
            if placement.owner_entity_id and placement.owner_entity_id not in entities
        ),
        "facts_missing_claims": sorted(
            f"{fact.fact_id}:{claim_id}"
            for fact in facts
            for claim_id in fact.member_claim_ids
            if claim_id not in claim_by_id
        ),
        "facts_missing_entities": sorted(
            f"{fact.fact_id}:{fact.owner_entity_id}"
            for fact in facts
            if fact.owner_entity_id not in entities
        ),
        "entities_missing_pages": sorted(
            f"{entity.entity_id}:{entity.slug}"
            for entity in entities.values()
            if entity.status == "active" and entity.slug not in pages
        ),
        "sources_missing_raw_log": sorted(
            source.source_id
            for source in sources
            if source.raw_log_entry_id and source.raw_log_entry_id not in logs
        ),
        "proposals_missing_claims": sorted(
            f"{proposal.proposal_id}:{claim_id}"
            for proposal in proposals
            for claim_id in (proposal.incoming_claim_id, proposal.target_claim_id)
            if claim_id not in claim_by_id
        ),
        "pages_unclassified": sorted(
            page.slug for page in wiki_pages if page.page_type is None
        ),
    }
    return {
        "healthy": not any(issues.values()),
        "issues": issues,
    }


@router.get("/artifacts/overview")
async def artifact_overview():
    mem = get_mem()
    claims = mem.artifacts.list_claims()
    coverage = mem.artifacts.coverage_report()
    coverage["suppressed_claims"] = len(claims) - coverage["active_claims"]
    placements = mem.artifacts.list_placements()
    assigned = [placement for placement in placements if placement.status == "placed"]
    disposition_counts: dict[str, int] = {}
    for claim in claims:
        disposition_counts[claim.dream_disposition] = (
            disposition_counts.get(claim.dream_disposition, 0) + 1
        )
    proposal_status_counts: dict[str, int] = {}
    for proposal in mem.artifacts.list_reconsolidation_proposals():
        proposal_status_counts[proposal.status] = (
            proposal_status_counts.get(proposal.status, 0) + 1
        )
    return {
        "coverage": coverage,
        "short_term_memory": mem.short_term_memory_status().as_dict(),
        "projection": {
            "page_assignments": len(assigned),
            "assigned_claims": len(assigned),
            "multi_page_claims": 0,
            "average_pages_per_claim": (
                1.0 if assigned else 0.0
            ),
            "max_pages_per_claim": 1 if assigned else 0,
        },
        "integrity": _artifact_integrity(mem),
        "dream_audit": {
            "runs": len(mem.artifacts.list_dream_runs()),
            "claim_dispositions": disposition_counts,
        },
        "reconsolidation_proposals": proposal_status_counts,
        "organization_proposals": {
            status: sum(
                proposal.status == status
                for proposal in mem.artifacts.list_organization_proposals()
            )
            for status in {proposal.status for proposal in mem.artifacts.list_organization_proposals()}
        },
        "archived_pages": len(list(mem.wiki.archive_dir.glob("*.md"))),
    }


@router.get("/artifacts/chat-episodes")
async def list_chat_episode_state():
    return [
        {
            "session_id": session_id,
            "query": record.get("query", "New session"),
            "transcript_turns": len(record.get("transcript", [])),
            "episode_seq": record.get("episode_seq"),
            "active_episode": record.get("active_episode"),
            "encoded_episodes": record.get("encoded_episodes", []),
        }
        for session_id, record in load_meta().items()
    ]


@router.get("/artifacts/sources")
async def list_artifact_sources():
    return [
        {
            "source_id": source.source_id,
            "source_type": source.source_type,
            "session_id": source.session_id,
            "recorded_at": source.recorded_at,
            "occurred_at": source.occurred_at,
            "participants": source.participants,
            "raw_log_entry_id": source.raw_log_entry_id,
            "metadata": source.metadata,
            "segment_count": len(source.segments),
        }
        for source in get_mem().artifacts.list_sources()
    ]


@router.get("/artifacts/sources/{source_id}")
async def get_artifact_source(source_id: str):
    try:
        return asdict(get_mem().artifacts.get_source(source_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source artifact not found") from exc


@router.get("/artifacts/episodes")
async def list_artifact_episodes():
    return [asdict(episode) for episode in get_mem().artifacts.list_episodes()]


@router.get("/artifacts/episodes/{episode_id}")
async def get_artifact_episode(episode_id: str):
    try:
        return asdict(get_mem().artifacts.get_episode(episode_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Episode artifact not found") from exc


@router.get("/artifacts/claims")
async def list_artifact_claims():
    artifacts = get_mem().artifacts
    return [
        {**asdict(claim), "placement": (
            asdict(placement) if (placement := artifacts.placement_for_claim(claim.claim_id)) else None
        )}
        for claim in artifacts.list_claims()
    ]


@router.get("/artifacts/claims/{claim_id}")
async def get_artifact_claim(claim_id: str):
    try:
        artifacts = get_mem().artifacts
        claim = artifacts.get_claim(claim_id)
        placement = artifacts.placement_for_claim(claim_id)
        return {**asdict(claim), "placement": asdict(placement) if placement else None}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claim artifact not found") from exc


@router.get("/artifacts/dream-runs")
async def list_artifact_dream_runs():
    return [asdict(run) for run in get_mem().artifacts.list_dream_runs()]


@router.get("/artifacts/dream-runs/{run_id}")
async def get_artifact_dream_run(run_id: str):
    try:
        return asdict(get_mem().artifacts.get_dream_run(run_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Dream run artifact not found") from exc


@router.get("/artifacts/reconsolidation-proposals")
async def list_reconsolidation_proposals():
    return [
        asdict(proposal)
        for proposal in get_mem().artifacts.list_reconsolidation_proposals()
    ]


@router.get("/artifacts/reconsolidation-proposals/{proposal_id}")
async def get_reconsolidation_proposal(proposal_id: str):
    try:
        return asdict(get_mem().artifacts.get_reconsolidation_proposal(proposal_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Reconsolidation proposal not found") from exc


@router.get("/artifacts/entities")
async def list_artifact_entities(status: str | None = None):
    return [asdict(entity) for entity in get_mem().artifacts.list_entities(status=status)]


@router.get("/artifacts/placements")
async def list_artifact_placements(status: str | None = None):
    return [asdict(item) for item in get_mem().artifacts.list_placements(status=status)]


@router.get("/artifacts/scope-decisions")
async def list_scope_decisions(claim_id: str | None = None, status: str | None = None):
    return [
        asdict(item)
        for item in get_mem().artifacts.list_scope_decisions(
            claim_id=claim_id, status=status
        )
    ]


@router.get("/artifacts/consolidated-facts")
async def list_consolidated_facts(
    owner_entity_id: str | None = None,
):
    return [
        asdict(item)
        for item in get_mem().artifacts.list_consolidated_facts(
            owner_entity_id=owner_entity_id
        )
    ]


@router.get("/artifacts/organization-proposals")
async def list_organization_proposals(status: str | None = None):
    return [
        asdict(item) for item in get_mem().artifacts.list_organization_proposals(status=status)
    ]


@router.get("/artifacts/files")
async def list_stored_memory_files():
    mem = get_mem()
    index_path = mem.wiki.wiki_dir / "_index.md"
    return {
        "wiki_index": _stored_memory_file(index_path) if index_path.exists() else None,
        "archived_pages": [
            _stored_memory_file(path) for path in sorted(mem.wiki.archive_dir.glob("*.md"))
        ],
    }

@router.get("/wiki")
async def list_wiki():
    mem = get_mem()
    pages = mem.wiki.list_all()
    return [
        {
            "slug": p.slug,
            "title": p.title,
            "confidence": p.confidence,
            "page_type": p.page_type,
            "tags": p.tags,
            "entity_id": p.entity_id,
            "entity_status": p.entity_status,
            "aliases": p.aliases,
        }
        for p in pages
    ]

@router.get("/wiki/{slug}")
async def get_wiki_page(slug: str):
    mem = get_mem()
    try:
        page = mem.wiki.get(slug)
        return wiki_page_response(page)
    except FileNotFoundError:
        entity = mem.artifacts.entity_for_slug(slug)
        if entity and entity.status == "merged" and entity.merged_into_entity_id:
            target = mem.artifacts.get_entity(entity.merged_into_entity_id)
            page = mem.wiki.get(target.slug)
            return {**wiki_page_response(page), "redirected_from": slug}
        raise HTTPException(status_code=404, detail="Page not found")


@router.get("/logs")
async def list_logs():
    mem = get_mem()
    logs_dir = mem.log_store.logs_dir
    if not logs_dir.exists():
        return []
    return [f.name for f in sorted(logs_dir.glob("*.md"), reverse=True)]

@router.get("/logs/{filename}")
async def get_log_content(filename: str):
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid log filename")
    mem = get_mem()
    log_path = mem.log_store.logs_dir / filename
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log not found")
    with open(log_path, "r", encoding="utf-8") as f:
        return {"filename": filename, "content": f.read()}

@router.post("/dream")
async def run_dream():
    return await run_dream_process()


@router.get("/dream/readiness")
async def dream_readiness():
    return get_mem().short_term_memory_status().as_dict()


@router.post("/dream/run-if-ready")
async def run_dream_if_ready():
    return await run_dream_if_ready_process()


@router.post("/dev/clear")
async def clear_memory():
    return clear_memory_store()


@router.post("/dev/clear-wiki")
async def clear_wiki():
    return clear_wiki_store()


@router.post("/episodes/flush")
async def flush_episode(req: FlushRequest):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    result = await flush_session_episode(req.session_id, reason="manual")
    if result["status"] == "missing":
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@router.post("/episodes/flush-idle")
async def flush_idle(req: IdleFlushRequest):
    return await flush_idle_episodes(
        idle_minutes=req.idle_minutes,
        max_turns=req.max_turns,
        force=req.force,
    )


@router.post("/episodes/flush-all")
async def flush_all():
    return await flush_idle_episodes(force=True)


def _review_service():
    mem = get_mem()
    return ReconsolidationReviewService(mem.artifacts, mem.dream_process.materializer)


def _curation_service():
    mem = get_mem()
    return EntityCurationService(mem.artifacts, mem.wiki, mem.dream_process.materializer)


def _fact_curation_service():
    mem = get_mem()
    return FactCurationService(mem.artifacts, mem.dream_process.materializer)


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


@router.patch("/entities/{entity_id}")
async def update_entity(entity_id: str, req: EntityUpdateRequest):
    try:
        return _curation_response(_curation_service().update_entity(
            entity_id,
            title=req.title,
            slug=req.slug,
            aliases=req.aliases,
            entity_type=req.entity_type,
        ))
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
        return _curation_response(_curation_service().merge(entity_id, req.target_entity_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Entity not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/entities/{entity_id}/split")
async def split_entity(entity_id: str, req: EntitySplitRequest):
    try:
        return _curation_response(_curation_service().split(
            entity_id,
            req.claim_ids,
            title=req.title,
            entity_type=req.entity_type,
            aliases=req.aliases,
        ))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Entity or claim not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/placements/{claim_id}")
async def update_placement(claim_id: str, req: PlacementUpdateRequest):
    try:
        return _curation_response(_curation_service().move_claim(
            claim_id,
            req.owner_entity_id,
            req.section_key,
            linked_entity_ids=req.linked_entity_ids,
            reason=req.reason,
        ))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claim or entity not found") from exc
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
        return _fact_curation_response(_fact_curation_service().move(
            fact_id,
            req.owner_entity_id,
            req.section_key,
            linked_entity_ids=req.linked_entity_ids,
            reason=req.reason,
        ))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Fact, claim, or entity not found") from exc
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
        return _fact_curation_response(_fact_curation_service().split(
            fact_id,
            [group.model_dump() for group in req.groups],
            reason=req.reason,
        ))
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
        raise HTTPException(status_code=404, detail="Organization proposal not found") from exc
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
        return _review_response(
            _review_service().approve(proposal_id, reviewer_note=req.reviewer_note)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Reconsolidation proposal not found") from exc
    except ReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/reconsolidation/proposals/{proposal_id}/reject")
async def reject_reconsolidation_proposal(
    proposal_id: str, req: ProposalReviewRequest
):
    try:
        return _review_response(
            _review_service().reject(proposal_id, reviewer_note=req.reviewer_note)
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Reconsolidation proposal not found") from exc
    except ReviewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
