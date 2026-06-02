from fastapi import APIRouter, HTTPException
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from mycelium.decay import record_memory_event
from mycelium.models import UpdateLogEntry
from server.runtime import (
    clear_memory_store,
    clear_wiki_store,
    flush_idle_episodes,
    flush_session_episode,
    get_mem,
    resolve_session_reconsolidation,
    run_decay,
    run_dream as run_dream_process,
)

router = APIRouter()


class FlushRequest(BaseModel):
    session_id: str | None = None


class IdleFlushRequest(BaseModel):
    idle_minutes: int = 20
    max_turns: int = 25
    force: bool = False


class WikiPageUpdate(BaseModel):
    title: str
    content: str
    tags: list[str] = []
    confidence: float | None = None
    importance: float | None = None
    pinned: bool | None = None


def wiki_page_response(page):
    return {
        "slug": page.slug,
        "title": page.title,
        "content": page.content,
        "version": page.version,
        "confidence": page.confidence,
        "importance": page.importance,
        "stability_days": page.stability_days,
        "difficulty": page.difficulty,
        "retrievability": page.retrievability,
        "last_accessed": page.last_accessed.isoformat() if page.last_accessed else None,
        "last_reviewed": page.last_reviewed.isoformat() if page.last_reviewed else None,
        "review_count": page.review_count,
        "reinforced_count": page.reinforced_count,
        "conflict_count": page.conflict_count,
        "pinned": page.pinned,
        "tags": page.tags,
        "source_log_entries": page.source_log_entries,
        "related": [{"target": r.target, "relation": r.relation} for r in page.related],
        "update_log": [{"version": u.version, "reason": u.reason, "date": u.date.isoformat()} for u in page.update_log],
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
            "retrievability": p.retrievability,
            "stability_days": p.stability_days,
            "difficulty": p.difficulty,
            "last_accessed": p.last_accessed.isoformat() if p.last_accessed else None,
            "last_reviewed": p.last_reviewed.isoformat() if p.last_reviewed else None,
            "review_count": p.review_count,
            "reinforced_count": p.reinforced_count,
            "conflict_count": p.conflict_count,
            "pinned": p.pinned,
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


@router.put("/wiki/{slug}")
async def update_wiki_page(slug: str, req: WikiPageUpdate):
    mem = get_mem()
    try:
        page = mem.wiki.get(slug)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Page not found")

    previous_confidence = page.confidence
    page.title = req.title.strip() or page.title
    page.content = req.content
    page.tags = req.tags
    if req.confidence is not None:
        page.confidence = max(0.0, min(1.0, req.confidence))
    if req.importance is not None:
        page.importance = max(0.0, min(1.0, req.importance))
    if req.pinned is not None:
        page.pinned = req.pinned
    page.version += 1
    page.last_updated = datetime.now()
    page.update_log.append(
        UpdateLogEntry(
            version=page.version,
            date=page.last_updated,
            session_id="manual",
            trigger="manual",
            discrepancy_score=0.0,
            reason="Manual edit from web UI",
            previous_confidence=previous_confidence,
            new_confidence=page.confidence,
        )
    )
    record_memory_event(page, "manually_edited", now=page.last_updated)
    mem.wiki.save(page)
    return wiki_page_response(page)

@router.delete("/wiki/{slug}")
async def delete_wiki_page(slug: str):
    mem = get_mem()
    if not mem.wiki.exists(slug):
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Archive/soft-delete
    mem.wiki.archive(slug)
    
    # Remove from index file
    index_content = mem.wiki.get_index()
    lines = index_content.splitlines()
    new_lines = []
    for line in lines:
        if f"[[{slug}]]" not in line:
            new_lines.append(line)
    mem.wiki.save_index("\n".join(new_lines))
    
    return {"slug": slug, "status": "success"}

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


@router.post("/decay")
async def decay():
    return await run_decay()


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


@router.post("/reconsolidation/resolve")
async def resolve_reconsolidation(req: FlushRequest):
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    result = await resolve_session_reconsolidation(req.session_id)
    if result["status"] == "missing":
        raise HTTPException(status_code=404, detail="Session not found")
    return result
