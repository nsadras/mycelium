"""Explicit memory build and development reset endpoints."""

from fastapi import APIRouter
from mycelium.lifecycle_transaction import mutation_lock
from server.runtime import (
    clear_memory_store,
    rebuild_wiki_store,
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
    async with mutation_lock(get_mem().artifacts.root):
        return clear_memory_store()


@router.post("/rebuild-wiki")
async def rebuild_wiki():
    async with mutation_lock(get_mem().artifacts.root):
        return rebuild_wiki_store()
