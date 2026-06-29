import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import BaseModel

from mycelium.core import Mycelium
from mycelium.openai_compatible import OpenAICompatibleClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.requests = []

    async def post(self, endpoint, json):
        self.requests.append({"endpoint": endpoint, "json": deepcopy(json)})
        return FakeResponse(self.payloads.pop(0))


def chat_payload(content, *, tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
    }


class AnswerOutput(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_call_messages_uses_openai_compatible_chat_completion():
    client = OpenAICompatibleClient("http://localhost:8000/v1", "test-model", temperature=0.3)
    fake_http = FakeHttpClient(chat_payload("hello"))
    client.client = fake_http
    messages = [{"role": "user", "content": "question"}]

    response = await client.call_messages(messages, enable_tools=False, num_predict=128)

    assert response.content == "hello"
    assert fake_http.requests == [
        {
            "endpoint": "http://localhost:8000/v1/chat/completions",
            "json": {
                "model": "test-model",
                "messages": messages,
                "temperature": 0.3,
                "stream": False,
                "max_tokens": 128,
            },
        }
    ]
    assert response.metadata["finish_reason"] == "stop"


@pytest.mark.asyncio
async def test_call_structured_sends_json_schema_response_format():
    client = OpenAICompatibleClient("http://localhost:8000/v1", "test-model")
    fake_http = FakeHttpClient(chat_payload('{"answer": "yes"}'))
    client.client = fake_http

    response = await client.call_structured("system prompt", "user prompt", AnswerOutput, num_predict=256)

    assert response == {"answer": "yes"}
    payload = fake_http.requests[0]["json"]
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "mycelium_response",
            "schema": AnswerOutput.model_json_schema(),
            "strict": True,
        },
    }
    assert payload["max_tokens"] == 256


@pytest.mark.asyncio
async def test_call_messages_executes_openai_tool_calls(monkeypatch):
    client = OpenAICompatibleClient("http://localhost:8000/v1", "test-model")
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "web_search", "arguments": json.dumps({"query": "diffusiongemma"})},
        }
    ]
    fake_http = FakeHttpClient(chat_payload("", tool_calls=tool_calls), chat_payload("final answer"))
    client.client = fake_http
    monkeypatch.setattr(client, "_run_tool", lambda name, args: f"{name}: {args['query']}")

    response = await client.call_messages([{"role": "user", "content": "search"}])

    assert response.content == "final answer"
    assert response.tool_events[0].tool_name == "web_search"
    assert response.tool_events[0].arguments == {"query": "diffusiongemma"}
    second_messages = fake_http.requests[1]["json"]["messages"]
    assert second_messages[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "name": "web_search",
        "content": "web_search: diffusiongemma",
    }


def test_mycelium_builds_openai_compatible_provider(tmp_path):
    store_path = tmp_path / "store"
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text(
        "\n".join(
            [
                "[store]",
                f'path = "{store_path}"',
                "",
                "[llm]",
                'provider = "vllm"',
                'url = "http://localhost:8000/v1"',
                'model = "google/diffusiongemma-26B-A4B-it"',
            ]
        ),
        encoding="utf-8",
    )

    mem = Mycelium(store_path=Path(store_path), config_path=config_path)

    assert isinstance(mem.llm, OpenAICompatibleClient)
    assert mem.llm.url == "http://localhost:8000/v1"
    assert mem.llm.model == "google/diffusiongemma-26B-A4B-it"
