from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel

from server.runtime import (
    clear_memory_store,
    clear_wiki_store,
    flush_idle_episodes,
    flush_session_episode,
    get_mem,
    load_meta,
    run_dream as run_dream_process,
)
from mycelium.reconsolidation import ReconsolidationReviewService, ReviewConflictError

router = APIRouter()


class FlushRequest(BaseModel):
    session_id: str | None = None


class IdleFlushRequest(BaseModel):
    idle_minutes: int = 20
    max_turns: int = 25
    force: bool = False


class ProposalReviewRequest(BaseModel):
    reviewer_note: str | None = None


def wiki_page_response(page):
    return {
        "slug": page.slug,
        "title": page.title,
        "content": page.content,
        "version": page.version,
        "confidence": page.confidence,
        "importance": page.importance,
        "tags": page.tags,
        "source_log_entries": page.source_log_entries,
        "related": [{"target": r.target, "relation": r.relation} for r in page.related],
        "update_log": [{"version": u.version, "reason": u.reason, "date": u.date.isoformat()} for u in page.update_log],
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
    pages = {page.slug for page in mem.wiki.list_all()}
    logs = {entry.entry_id for entry in mem.log_store.list_entries(days=None)}

    source_by_id = {source.source_id: source for source in sources}
    episode_source_ids = {episode.source_id for episode in episodes}
    claim_by_id = {claim.claim_id: claim for claim in claims}
    proposals = mem.artifacts.list_reconsolidation_proposals()

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
        "claims_missing_pages": sorted(
            f"{claim.claim_id}:{page_slug}"
            for claim in claims
            for page_slug in claim.page_slugs
            if page_slug not in pages
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
    page_counts = [len(claim.page_slugs) for claim in claims]
    assigned_page_counts = [count for count in page_counts if count]
    page_assignments = sum(page_counts)
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
        "projection": {
            "page_assignments": page_assignments,
            "assigned_claims": len(assigned_page_counts),
            "multi_page_claims": sum(count > 1 for count in page_counts),
            "average_pages_per_claim": (
                page_assignments / len(assigned_page_counts) if assigned_page_counts else 0.0
            ),
            "max_pages_per_claim": max(page_counts, default=0),
        },
        "integrity": _artifact_integrity(mem),
        "dream_audit": {
            "runs": len(mem.artifacts.list_dream_runs()),
            "claim_dispositions": disposition_counts,
        },
        "reconsolidation_proposals": proposal_status_counts,
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
    return [asdict(claim) for claim in get_mem().artifacts.list_claims()]


@router.get("/artifacts/claims/{claim_id}")
async def get_artifact_claim(claim_id: str):
    try:
        return asdict(get_mem().artifacts.get_claim(claim_id))
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
            "importance": p.importance,
            "tags": p.tags,
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

@router.post("/logs/{filename}/unconsolidate")
async def unconsolidate_log(filename: str):
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid log filename")
    
    date_str = filename.replace(".md", "")
    mem = get_mem()
    mem.log_store.mark_unconsolidated(date_str)
    
    log_path = mem.log_store.logs_dir / filename
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Log not found")
    with open(log_path, "r", encoding="utf-8") as f:
        return {"filename": filename, "content": f.read(), "status": "success"}

@router.post("/dream")
async def run_dream():
    return await run_dream_process()


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
