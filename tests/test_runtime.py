from types import SimpleNamespace

import pytest

from mycelium.openai_compatible import OpenAICompatibleClient
from mycelium.store import LogStore
from server import runtime
from server.runtime import append_tool_event_logs, ensure_session_record


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    requests = []

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url):
        self.requests.append(url)
        return FakeHttpResponse(
            {
                "models": [
                    {"name": "gemma4:12b"},
                    {"name": "llama3.2:latest"},
                    {"digest": "missing-name"},
                ]
            }
        )


def test_ensure_session_record_initializes_episode():
    record = {"query": "Test", "transcript": []}

    ensure_session_record(record, "ses")

    assert record["encoded_episodes"] == []
    assert record["active_episode"]["id"] == "ses-ep-1"
    assert record["active_episode"]["buffer"] == []


def test_no_entries_flush_should_preserve_buffer_shape():
    record = {
        "query": "Test",
        "transcript": [{"role": "user", "content": "hello"}],
        "episode_seq": 1,
        "encoded_episodes": [],
        "active_episode": {
            "id": "ses-ep-1",
            "started_at": "2026-05-19T00:00:00+00:00",
            "last_activity_at": "2026-05-19T00:00:00+00:00",
            "buffer": [{"role": "user", "content": "hello"}],
            "turn_count": 1,
        },
    }

    ensure_session_record(record, "ses")

    assert record["active_episode"]["turn_count"] == 1
    assert record["encoded_episodes"] == []


def test_append_tool_event_logs_creates_unconsolidated_entries(tmp_path, monkeypatch):
    log_store = LogStore(tmp_path / "logs")
    monkeypatch.setattr(runtime, "get_mem", lambda: SimpleNamespace(log_store=log_store))

    created = append_tool_event_logs(
        "chat-123",
        "chat-123-ep-1",
        [
            {
                "tool_name": "web_search",
                "arguments": {"query": "local llm news"},
                "result": "1. Result\nhttps://example.com\nUseful new information.",
                "failed": False,
                "truncated": True,
            }
        ],
        turn_count=2,
    )

    entries = log_store.get_unconsolidated()
    assert len(created) == 1
    assert len(entries) == 1
    assert entries[0].entry_id.startswith(created[0].entry_id.split("#")[0] + "#tool-")
    assert entries[0].session_id == "chat-123-ep-1"
    assert "Tool observation from chat." in entries[0].content
    assert "- chat_session_id: chat-123" in entries[0].content
    assert "- tool_name: web_search" in entries[0].content
    assert '"query": "local llm news"' in entries[0].content
    assert "Useful new information." in entries[0].content


def test_update_llm_settings_persists_config_and_rebuilds_client(tmp_path, monkeypatch):
    store_path = tmp_path / "store"
    config_path = tmp_path / "mycelium.toml"
    config_path.write_text(
        "\n".join(
            [
                "[store]",
                f'path = "{store_path}"',
                "git_commits = false",
                "",
                "[llm]",
                'provider = "ollama"',
                'model = "gemma4:12b"',
                'url = "http://localhost:11434"',
                "temperature = 0.2",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime, "CONFIG_FILE", config_path)
    monkeypatch.setattr(runtime, "_mem", None)

    settings = runtime.update_llm_settings(
        provider="vllm",
        model="google/diffusiongemma-26B-A4B-it",
        url="http://localhost:8000/v1",
        temperature=0.1,
    )

    assert settings["provider"] == "vllm"
    assert settings["model"] == "google/diffusiongemma-26B-A4B-it"
    assert isinstance(runtime.get_mem().llm, OpenAICompatibleClient)
    saved = config_path.read_text(encoding="utf-8")
    assert 'provider = "vllm"' in saved
    assert 'model = "google/diffusiongemma-26B-A4B-it"' in saved
    assert 'url = "http://localhost:8000/v1"' in saved


@pytest.mark.asyncio
async def test_list_llm_models_reads_installed_ollama_models(monkeypatch):
    FakeAsyncClient.requests = []
    monkeypatch.setattr(runtime.httpx, "AsyncClient", FakeAsyncClient)

    result = await runtime.list_llm_models(provider="ollama", url="http://ollama.test")

    assert FakeAsyncClient.requests == ["http://ollama.test/api/tags"]
    assert result == {
        "provider": "ollama",
        "url": "http://ollama.test",
        "models": [
            {"id": "gemma4:12b", "label": "gemma4:12b"},
            {"id": "llama3.2:latest", "label": "llama3.2:latest"},
        ],
        "error": None,
    }
