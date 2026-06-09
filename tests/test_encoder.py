import pytest
from unittest.mock import AsyncMock, MagicMock
from mycelium.encoder import Encoder
from mycelium.models import LogEntry
from mycelium.config import Config

@pytest.fixture
def mock_llm():
    return AsyncMock()

@pytest.fixture
def mock_wiki_store():
    store = MagicMock()
    store.get_index.return_value = "# Index"
    return store

@pytest.fixture
def mock_log_store():
    return MagicMock()

@pytest.fixture
def encoder(mock_llm, mock_wiki_store, mock_log_store):
    config = Config.defaults()
    return Encoder(mock_llm, mock_wiki_store, mock_log_store, config)

@pytest.mark.asyncio
async def test_encode_session(encoder, mock_llm, mock_log_store):
    entries = await encoder.encode_session("USER: some transcript", "ses-123")

    assert len(entries) == 1
    assert "Raw conversation transcript" in entries[0].content
    assert "USER: some transcript" in entries[0].content
    assert entries[0].importance == 0.8
    assert entries[0].durability == "durable"
    assert entries[0].session_id == "ses-123"

    mock_llm.call_structured.assert_not_called()
    assert mock_log_store.append.call_count == 1
    args, _ = mock_log_store.append.call_args_list[0]
    assert isinstance(args[0], LogEntry)
    assert args[0].session_id == "ses-123"


@pytest.mark.asyncio
async def test_encode_session_skips_empty_transcript(encoder, mock_llm, mock_log_store):
    entries = await encoder.encode_session("   ", "ses-123")

    assert entries == []
    mock_llm.call_structured.assert_not_called()
    mock_log_store.append.assert_not_called()

@pytest.mark.asyncio
async def test_encode_direct_with_importance(encoder, mock_llm, mock_log_store):
    entry = await encoder.encode(
        content="Direct entry",
        session_id="ses-123",
        importance=0.9
    )
    
    assert entry.content == "Direct entry"
    assert entry.importance == 0.9
    
    mock_llm.call_structured.assert_not_called()
    mock_log_store.append.assert_called_once_with(entry)

@pytest.mark.asyncio
async def test_encode_direct_without_importance(encoder, mock_llm, mock_log_store):
    mock_llm.call_structured.return_value = {"importance": 0.75}
    
    entry = await encoder.encode(
        content="Direct entry no importance",
        session_id="ses-123"
    )
    
    assert entry.content == "Direct entry no importance"
    assert entry.importance == 0.75
    
    mock_llm.call_structured.assert_called_once()
    mock_log_store.append.assert_called_once_with(entry)
