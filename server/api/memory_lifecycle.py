"""Explicit memory build and development reset endpoints."""

from fastapi import APIRouter
from server.runtime import (
    clear_memory_store,
    clear_wiki_store,
    get_mem,
    run_consolidation,
)

router = APIRouter()


@router.post("/build")
async def build_memory():
    return await run_consolidation()


@router.get("/build/status")
async def build_status():
    return get_mem().consolidation_status().as_dict()


@router.post("/dev/clear")
async def clear_memory():
    return clear_memory_store()


@router.post("/dev/clear-wiki")
async def clear_wiki():
    return clear_wiki_store()
