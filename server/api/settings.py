from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from server.runtime import list_llm_models, llm_presets, llm_settings, update_llm_settings

router = APIRouter()


class LLMSettingsUpdate(BaseModel):
    provider: str
    model: str
    url: str
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout_seconds: int | None = Field(default=None, ge=1)
    max_retries: int | None = Field(default=None, ge=1)


@router.get("/llm")
async def get_llm_settings() -> dict[str, Any]:
    settings = llm_settings()
    return {
        "settings": settings,
        "presets": await llm_presets(),
        "models": (await list_llm_models(provider=settings["provider"], url=settings["url"]))["models"],
    }


@router.put("/llm")
async def put_llm_settings(req: LLMSettingsUpdate) -> dict[str, Any]:
    try:
        settings = update_llm_settings(
            provider=req.provider,
            model=req.model,
            url=req.url,
            temperature=req.temperature,
            timeout_seconds=req.timeout_seconds,
            max_retries=req.max_retries,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "settings": settings,
        "presets": await llm_presets(),
        "models": (await list_llm_models(provider=settings["provider"], url=settings["url"]))["models"],
    }


@router.get("/llm/models")
async def get_llm_models(
    provider: str | None = Query(default=None),
    url: str | None = Query(default=None),
) -> dict[str, Any]:
    return await list_llm_models(provider=provider, url=url)
