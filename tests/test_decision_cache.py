import asyncio
from types import SimpleNamespace
from typing import Literal
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from mycelium.database import MemoryDatabase, UnitOfWork
from mycelium.ollama import OllamaClient


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Literal["first", "second"]


def client():
    llm = OllamaClient("http://localhost:11434", "test", reasoning_enabled=False)
    llm.client.list = AsyncMock(return_value={"models": [{"model": "test:latest", "digest": "weights-1"}]})
    llm.client.chat = AsyncMock(return_value=SimpleNamespace(message=SimpleNamespace(content='{"value":"first"}'), done_reason="stop"))
    return llm


async def decide(llm, db, *, system="contract", user="evidence", schema=Decision, **kwargs):
    return await llm.call_structured(system, user, schema, cache_store=db, **kwargs)


@pytest.mark.asyncio
async def test_success_survives_restart_and_aborted_canonical_operation(tmp_path):
    db = MemoryDatabase(tmp_path)
    llm = client()
    unit = UnitOfWork(db)
    unit.put("claims", "uncommitted", {"text": "Uncommitted input"})
    assert await decide(llm, unit) == {"value": "first"}
    unit.close()
    assert db.ids("claims") == []
    assert len(db.ids("model-decisions")) == 1
    db.close()
    db = MemoryDatabase(tmp_path)
    restarted = client()
    try:
        assert await decide(restarted, db) == {"value": "first"}
        restarted.client.chat.assert_not_awaited()
        assert restarted._call_log[-1]["metadata"]["cache_hit"]
    finally:
        db.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["system", "evidence", "schema", "model", "weights", "temperature", "top_p", "top_k", "context", "output", "reasoning", "endpoint"])
async def test_every_inference_dependency_invalidates_reuse(tmp_path, change):
    db = MemoryDatabase(tmp_path)
    llm = client()
    await decide(llm, db)
    kwargs = {}
    if change == "system":
        kwargs["system"] = "new contract"
    elif change == "evidence":
        kwargs["user"] = "revised evidence"
    elif change == "schema":
        class NewDecision(Decision):
            value: Literal["first"]
        kwargs["schema"] = NewDecision
    elif change in {"model", "weights"}:
        if change == "model":
            llm.model = "other"
        llm.client.list.return_value = {"models": [{"model": llm.model + ":latest", "digest": "weights-2"}]}
    elif change == "temperature":
        llm.temperature = .3
    elif change == "top_p":
        llm.top_p = .8
    elif change == "top_k":
        llm.top_k = 32
    elif change == "context":
        llm.context_window_tokens = 65536
    elif change == "output":
        kwargs["num_predict"] = 2048
    elif change == "reasoning":
        llm.reasoning_enabled = True
        kwargs["think"] = True
    else:
        llm.url = "http://127.0.0.1:11434"
    try:
        await decide(llm, db, **kwargs)
        assert llm.client.chat.await_count == 2
    finally:
        db.close()


@pytest.mark.asyncio
async def test_concurrent_identical_calls_share_one_success(tmp_path):
    db = MemoryDatabase(tmp_path)
    llm = client()
    try:
        values = await asyncio.gather(decide(llm, db), decide(llm, db))
        assert values == [{"value": "first"}] * 2
        assert llm.client.chat.await_count == 1
        assert len(db.ids("model-decisions")) == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_invalid_or_cancelled_generation_is_never_cached(tmp_path):
    db = MemoryDatabase(tmp_path)
    llm = client()
    llm.client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content='{"value":"invalid"}'), done_reason="stop")
    try:
        with pytest.raises(ValueError, match="contract"):
            await decide(llm, db, max_retries=1)
        assert db.ids("model-decisions") == []
        llm.client.chat.side_effect = asyncio.CancelledError()
        with pytest.raises(asyncio.CancelledError):
            await decide(llm, db)
        assert db.ids("model-decisions") == []
    finally:
        db.close()


@pytest.mark.asyncio
async def test_corrupt_cached_output_fails_validation(tmp_path):
    db = MemoryDatabase(tmp_path)
    llm = client()
    try:
        await decide(llm, db)
        key = db.ids("model-decisions")[0]
        record = db.get("model-decisions", key)
        record["response"] = {"value": "invented"}
        db.put("model-decisions", key, record)
        with pytest.raises(ValidationError):
            await decide(llm, db)
        assert llm.client.chat.await_count == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_unknown_weights_prevent_reuse(tmp_path):
    db = MemoryDatabase(tmp_path)
    llm = client()
    try:
        await decide(llm, db)
        llm.client.list.return_value = {"models": []}
        with pytest.raises(ValueError, match="weights"):
            await decide(llm, db)
        assert llm.client.chat.await_count == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_model_change_during_generation_does_not_cache_under_old_digest(tmp_path):
    db = MemoryDatabase(tmp_path)
    llm = client()

    async def generate(**kwargs):
        llm.client.list.return_value = {"models": [{"model": "test:latest", "digest": "changed-weights"}]}
        return SimpleNamespace(message=SimpleNamespace(content='{"value":"first"}'), done_reason="stop")

    llm.client.chat.side_effect = generate
    try:
        with pytest.raises(ValueError, match="weights changed"):
            await decide(llm, db)
        assert db.ids("model-decisions") == []
    finally:
        db.close()
