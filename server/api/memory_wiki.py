"""Wiki and durable-log read endpoints."""

from fastapi import APIRouter, HTTPException

from server.api.memory_contracts import wiki_page_response
from server.runtime import get_mem

router = APIRouter()


@router.get("/wiki")
async def list_wiki():
    mem = get_mem()
    pages = mem.wiki.list_all()
    return [
        {
            "slug": p.slug,
            "title": p.title,
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
