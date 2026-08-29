"""Dream, reset, and episode lifecycle endpoints."""

from fastapi import APIRouter, HTTPException

from server.api.memory_contracts import FlushRequest, IdleFlushRequest
from server.runtime import (
    clear_memory_store,
    clear_wiki_store,
    flush_idle_episodes,
    flush_session_episode,
    get_mem,
    run_dream as run_dream_process,
    run_dream_if_ready as run_dream_if_ready_process,
)

router = APIRouter()


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
