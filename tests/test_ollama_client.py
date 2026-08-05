import json
from types import SimpleNamespace
from copy import deepcopy

import pytest
from pydantic import BaseModel, RootModel

from mycelium.ollama import OllamaClient


def snapshot_call(kwargs):
    snap = dict(kwargs)
    if "messages" in snap:
        snap["messages"] = deepcopy(snap["messages"])
    if "tools" in snap and snap["tools"] is not None:
        snap["tools"] = list(snap["tools"])
    return snap


class FakeSdkClient:
    def __init__(self, content: str, *, done_reason: str = "stop", eval_count: int = 5, thinking: str = ""):
        self.content = content
        self.done_reason = done_reason
        self.eval_count = eval_count
        self.thinking = thinking
        self.chat_calls = []
        self.generate_calls = []

    async def chat(self, **kwargs):
        self.chat_calls.append(snapshot_call(kwargs))
        message = SimpleNamespace(content=self.content)
        if self.thinking:
            message.thinking = self.thinking
        return SimpleNamespace(
            message=message,
            done=True,
            done_reason=self.done_reason,
            prompt_eval_count=10,
            eval_count=self.eval_count,
        )

    async def generate(self, **kwargs):
        self.generate_calls.append(kwargs)
        return SimpleNamespace(response=self.content)


class FakeToolSdkClient:
    def __init__(self):
        self.chat_calls = []
        self.generate_calls = []

    async def chat(self, **kwargs):
        self.chat_calls.append(snapshot_call(kwargs))
        if len(self.chat_calls) == 1:
            return SimpleNamespace(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "web_search", "arguments": {"query": "ollama"}}}
                    ],
                }
            )
        return SimpleNamespace(message={"role": "assistant", "content": "final answer"})

    async def web_search(self, query: str, max_results: int = 3):
        return {
            "results": [{
                "title": "Result One",
                "url": "https://example.com/one",
                "content": f"result for {query}\\nsecond line",
            }]
        }

    async def web_fetch(self, url: str):
        return f"content for {url}"


class FakeWebClient:
    def web_search(self, query: str, max_results: int = 3):
        return {
            "results": [
                {
                    "title": "Result One",
                    "url": "https://example.com/one",
                    "content": f"result for {query}\\nsecond line",
                }
            ]
        }

    def web_fetch(self, url: str):
        return f"content for {url}"


@pytest.mark.asyncio
async def test_call_uses_official_sdk_chat():
    client = OllamaClient("http://localhost:11434", "test-model", temperature=0.3)
    fake_sdk = FakeSdkClient("hello")
    client.client = fake_sdk

    response = await client.call("system prompt", "user prompt")

    assert response == "hello"
    assert fake_sdk.chat_calls == [
        {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
            "stream": False,
            "format": None,
            "options": {"temperature": 0.3},
        }
    ]
    assert fake_sdk.generate_calls == []


@pytest.mark.asyncio
async def test_call_messages_uses_explicit_message_history():
    client = OllamaClient("http://localhost:11434", "test-model", temperature=0.3)
    fake_sdk = FakeSdkClient("hello")
    client.client = fake_sdk
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]

    response = await client.call_messages(messages)

    assert response.content == "hello"
    assert response.tool_events == []
    assert len(fake_sdk.chat_calls) == 1
    assert fake_sdk.chat_calls[0]["model"] == "test-model"
    assert fake_sdk.chat_calls[0]["messages"] == messages
    assert fake_sdk.chat_calls[0]["stream"] is False
    assert fake_sdk.chat_calls[0]["format"] is None
    assert fake_sdk.chat_calls[0]["options"] == {"temperature": 0.3}
    assert len(fake_sdk.chat_calls[0]["tools"]) == 2
    assert fake_sdk.chat_calls[0]["think"] is True
    assert fake_sdk.generate_calls == []


@pytest.mark.asyncio
async def test_call_messages_disables_thinking_when_tools_disabled():
    client = OllamaClient("http://localhost:11434", "test-model", temperature=0.3)
    fake_sdk = FakeSdkClient("hello")
    client.client = fake_sdk

    response = await client.call_messages([{"role": "user", "content": "question"}], enable_tools=False)

    assert response.content == "hello"
    assert fake_sdk.chat_calls[0]["tools"] is None
    assert fake_sdk.chat_calls[0]["think"] is False


@pytest.mark.asyncio
async def test_call_messages_passes_generation_options():
    client = OllamaClient("http://localhost:11434", "test-model", temperature=0.3)
    fake_sdk = FakeSdkClient("hello", done_reason="stop", eval_count=12)
    client.client = fake_sdk

    response = await client.call_messages(
        [{"role": "user", "content": "question"}],
        enable_tools=False,
        num_ctx=32768,
        num_predict=512,
        think=False,
    )

    assert response.content == "hello"
    assert response.metadata["done_reason"] == "stop"
    assert response.metadata["eval_count"] == 12
    assert fake_sdk.chat_calls[0]["options"] == {
        "temperature": 0.3,
        "num_ctx": 32768,
        "num_predict": 512,
    }
    assert fake_sdk.chat_calls[0]["think"] is False


@pytest.mark.asyncio
async def test_call_messages_executes_web_tools(monkeypatch):
    client = OllamaClient("http://localhost:11434", "test-model")
    fake_sdk = FakeToolSdkClient()
    client.client = fake_sdk
    messages = [{"role": "user", "content": "search"}]

    response = await client.call_messages(messages)

    assert response.content == "final answer"
    assert len(response.tool_events) == 1
    assert response.tool_events[0].tool_name == "web_search"
    assert response.tool_events[0].arguments == {"query": "ollama"}
    assert response.tool_events[0].result == "1. Result One\nhttps://example.com/one\nresult for ollama\nsecond line"
    assert response.tool_events[0].failed is False
    assert len(fake_sdk.chat_calls) == 2
    assert fake_sdk.chat_calls[1]["messages"][-1] == {
        "role": "tool",
        "content": "1. Result One\nhttps://example.com/one\nresult for ollama\nsecond line",
        "tool_name": "web_search",
    }


@pytest.mark.asyncio
async def test_call_structured_passes_schema_to_sdk_and_parses_content():
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    client = OllamaClient("http://localhost:11434", "test-model")
    fake_sdk = FakeSdkClient('{"answer": "yes"}')
    client.client = fake_sdk

    response = await client.call_structured("system prompt", "user prompt", schema)

    assert response == {"answer": "yes"}
    assert fake_sdk.chat_calls == [
        {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "user prompt"},
            ],
            "think": False,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0.0, "num_ctx": 32768, "num_predict": 4096},
        }
    ]
    assert fake_sdk.generate_calls == []
    assert client._call_log[-1]["metadata"]["done_reason"] == "stop"


@pytest.mark.asyncio
async def test_call_log_is_bounded_and_contains_metadata_only():
    client = OllamaClient("http://localhost:11434", "test-model")
    client.client = FakeSdkClient("private response")

    for index in range(105):
        await client.call("private system", f"private user {index}")

    assert len(client._call_log) == 100
    serialized = json.dumps(list(client._call_log))
    assert "private system" not in serialized
    assert "private user" not in serialized
    assert "private response" not in serialized
    assert client._call_log[-1]["response_chars"] == len("private response")


@pytest.mark.asyncio
async def test_info_logs_do_not_include_llm_payloads(caplog):
    client = OllamaClient("http://localhost:11434", "test-model")
    client.client = FakeSdkClient("private response")

    with caplog.at_level("INFO", logger="mycelium.ollama"):
        await client.call("private system", "private user")

    output = caplog.text
    assert "private system" not in output
    assert "private user" not in output
    assert "private response" not in output
    assert "request_chars" in output
    assert "response_chars" in output


class AnswerOutput(BaseModel):
    answer: str


class AnswerListOutput(RootModel[list[AnswerOutput]]):
    pass


@pytest.mark.asyncio
async def test_call_structured_accepts_pydantic_model():
    client = OllamaClient("http://localhost:11434", "test-model")
    fake_sdk = FakeSdkClient('{"answer": "yes"}')
    client.client = fake_sdk

    response = await client.call_structured("system prompt", "user prompt", AnswerOutput)

    assert response == {"answer": "yes"}
    assert fake_sdk.chat_calls[0]["format"] == AnswerOutput.model_json_schema()
    assert fake_sdk.chat_calls[0]["think"] is False


@pytest.mark.asyncio
async def test_call_structured_accepts_pydantic_root_model():
    client = OllamaClient("http://localhost:11434", "test-model")
    fake_sdk = FakeSdkClient('[{"answer": "yes"}]')
    client.client = fake_sdk

    response = await client.call_structured("system prompt", "user prompt", AnswerListOutput)

    assert response == [{"answer": "yes"}]
    assert fake_sdk.chat_calls[0]["format"] == AnswerListOutput.model_json_schema()


@pytest.mark.asyncio
async def test_call_structured_accepts_custom_num_predict():
    client = OllamaClient("http://localhost:11434", "test-model")
    fake_sdk = FakeSdkClient('{"answer": "yes"}')
    client.client = fake_sdk

    response = await client.call_structured("system prompt", "user prompt", AnswerOutput, num_predict=8192)

    assert response == {"answer": "yes"}
    assert fake_sdk.chat_calls[0]["options"]["num_predict"] == 8192


@pytest.mark.asyncio
async def test_call_structured_uses_configured_context_window():
    client = OllamaClient(
        "http://localhost:11434",
        "test-model",
        context_window_tokens=65536,
    )
    fake_sdk = FakeSdkClient('{"answer": "yes"}')
    client.client = fake_sdk

    await client.call_structured("system prompt", "user prompt", AnswerOutput)

    assert fake_sdk.chat_calls[0]["options"]["num_ctx"] == 65536


@pytest.mark.asyncio
async def test_call_structured_debug_dumps_successful_response(tmp_path, monkeypatch):
    client = OllamaClient("http://localhost:11434", "test-model")
    fake_sdk = FakeSdkClient('{"answer": "yes"}', done_reason="length", eval_count=8192)
    client.client = fake_sdk
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path))

    response = await client.call_structured(
        "system prompt",
        "user prompt",
        AnswerOutput,
        num_predict=8192,
        dump_success=True,
        debug_label="wiki-rewrite-person-jon",
    )

    assert response == {"answer": "yes"}
    dump_path = next(tmp_path.glob("structured-success-wiki-rewrite-person-jon-*-attempt-1.json"))
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    assert dump["metadata"]["done_reason"] == "length"
    assert dump["metadata"]["eval_count"] == 8192
    assert dump["options"]["num_predict"] == 8192
    assert dump["response"] == '{"answer": "yes"}'
    assert dump["parsed"] == {"answer": "yes"}


@pytest.mark.asyncio
async def test_call_structured_debug_dumps_failed_partial_response(tmp_path, monkeypatch):
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }
    client = OllamaClient("http://localhost:11434", "test-model")
    partial_json = '{"answer": "unfinished'
    fake_sdk = FakeSdkClient(partial_json, done_reason="length", eval_count=4096)
    client.client = fake_sdk
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="debug_dump=.*structured-failure-"):
        await client.call_structured("system prompt", "user prompt", schema, max_retries=1)

    dump_paths = list(tmp_path.glob("structured-failure-*-attempt-1.json"))
    assert len(dump_paths) == 1
    dump = json.loads(dump_paths[0].read_text(encoding="utf-8"))
    assert dump["response"] == partial_json
    assert dump["metadata"]["done_reason"] == "length"
    assert dump["metadata"]["eval_count"] == 4096
    assert dump["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert dump["format"] == schema


@pytest.mark.asyncio
async def test_call_structured_debug_dump_includes_assistant_message(tmp_path, monkeypatch):
    client = OllamaClient("http://localhost:11434", "test-model")
    fake_sdk = FakeSdkClient("", done_reason="length", eval_count=4096, thinking="hidden chain")
    client.client = fake_sdk
    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path))

    with pytest.raises(ValueError):
        await client.call_structured("system prompt", "user prompt", AnswerOutput, max_retries=1)

    dump_path = next(tmp_path.glob("structured-failure-*-attempt-1.json"))
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    assert dump["response"] == ""
    assert dump["assistant_message"]["thinking"] == "hidden chain"


@pytest.mark.asyncio
async def test_call_structured_mentions_debug_env_when_dump_disabled(monkeypatch):
    client = OllamaClient("http://localhost:11434", "test-model")
    client.client = FakeSdkClient('{"answer": "unfinished', done_reason="length", eval_count=4096)
    monkeypatch.delenv("MYCELIUM_LLM_DEBUG_DIR", raising=False)

    with pytest.raises(ValueError, match="set MYCELIUM_LLM_DEBUG_DIR=.llm-debug"):
        await client.call_structured("system prompt", "user prompt", AnswerOutput, max_retries=1)
