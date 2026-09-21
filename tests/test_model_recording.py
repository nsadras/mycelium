import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from ollama import ChatResponse, ResponseError
from pydantic import BaseModel

from benchmarks.shared.model_recording import RecordingClient
from benchmarks.experiments.compact_probe import BudgetClient, metrics
from mycelium.ollama import OllamaClient


def response():
    return ChatResponse(model="test", done=True, done_reason="stop",
                        message={"role": "assistant", "content": '{"value":"done"}'})


@pytest.mark.asyncio
async def test_recorders_keep_requests_unchanged_and_never_overwrite_between_checkpoints(tmp_path):
    client = AsyncMock()
    client.chat.return_value = response()
    request = {"model": "test", "messages": [{"role": "user", "content": "A request"}],
               "options": {"temperature": 1.0}, "tools": [{"type": "function", "function": {"name": "inspect"}}]}
    for _ in range(2):
        assert await RecordingClient(client, tmp_path).chat(**request) == response()
    assert all(call.kwargs == request for call in client.chat.await_args_list)
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 2
    assert not list(tmp_path.glob("*.tmp"))
    for path in files:
        recorded = json.loads(path.read_text())
        assert recorded["request"] == request and recorded["status"] == "complete"
        assert recorded["seconds"] >= 0


@pytest.mark.asyncio
async def test_native_recordings_link_failed_and_successful_attempts_to_timing_rows(tmp_path):
    class Output(BaseModel):
        value: str

    client = AsyncMock()
    client.chat.side_effect = [ResponseError("Temporary error", status_code=503), response()]
    llm = OllamaClient(url="http://unused", model="test", trace_path=tmp_path / "calls.jsonl")
    llm.client = RecordingClient(client, tmp_path / "requests")
    assert await llm.call_structured("Return the value.", "An input", Output, max_retries=2) == {"value": "done"}
    requests = sorted((json.loads(p.read_text()) for p in (tmp_path / "requests").glob("*.json")),
                      key=lambda r: r["trace"]["llm_attempt"])
    assert [r["status"] for r in requests] == ["failed", "complete"]
    assert "Temporary error" in requests[0]["error"]
    calls = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert {(r["trace"]["llm_call_id"], r["trace"]["llm_attempt"]) for r in requests} == {
        (r["call_id"], r["attempt"]) for r in calls}


@pytest.mark.asyncio
@pytest.mark.parametrize("deadline", [False, True])
async def test_cancelled_calls_are_not_transport_failures_or_complete_usage(tmp_path, deadline):
    started = asyncio.Event()
    async def pending(**kwargs):
        started.set()
        await asyncio.Event().wait()
    recorder = RecordingClient(AsyncMock(chat=AsyncMock(side_effect=pending)), tmp_path / "requests")
    if deadline:
        with pytest.raises(TimeoutError):
            await BudgetClient(recorder, .01, 1).chat(model="test")
    else:
        task = asyncio.create_task(recorder.chat(model="test"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    recorded, = [json.loads(p.read_text()) for p in (tmp_path / "requests").glob("*.json")]
    assert recorded["status"] == "cancelled"
    assert recorded["cancellation_reason"] == ("deadline" if deadline else "cancelled")
    result = metrics(tmp_path)
    assert result["transport_failures"] == result["unfinished_requests"] == 0
    assert result["cancelled_requests"] == 1
    assert result["deadline_cancellations"] == int(deadline)
    assert not result["usage_complete"]
    assert result["client_seconds"] >= 0


def test_unfinished_recording_and_missing_usage_remain_visible(tmp_path):
    root = tmp_path / "requests"
    root.mkdir()
    (root / "aborted.json").write_text(json.dumps({"status": "running"}))
    result = metrics(tmp_path)
    assert result["unfinished_requests"] == 1 and not result["usage_complete"]
    assert result["transport_failures"] == 0
    (root / "aborted.json").write_text(json.dumps({"status": "complete", "response": {}}))
    assert not metrics(tmp_path)["usage_complete"]
