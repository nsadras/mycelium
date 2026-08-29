"""Composed memory API router."""

from fastapi import APIRouter

from server.api.memory_artifacts import router as artifacts_router
from server.api.memory_curation import router as curation_router
from server.api.memory_lifecycle import router as lifecycle_router
from server.api.memory_wiki import router as wiki_router

router = APIRouter()
router.include_router(artifacts_router)
router.include_router(wiki_router)
router.include_router(lifecycle_router)
router.include_router(curation_router)
