import pytest
from unittest.mock import AsyncMock, MagicMock
from mycelium.artifacts import ArtifactStore
from mycelium.encoder import Encoder
from mycelium.models import LogEntry
from mycelium.config import Config

@pytest.fixture
def mock_llm():
    return AsyncMock()

@pytest.fixture
def mock_log_store():
    return MagicMock()

@pytest.fixture
def encoder(tmp_path, mock_llm, mock_log_store):
    config = Config.defaults()
    return Encoder(
        mock_llm,
        mock_log_store,
        config,
        ArtifactStore(tmp_path / "artifacts"),
    )

@pytest.mark.asyncio
async def test_encode_session(encoder, mock_llm, mock_log_store):
    async def ignore_transcript(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return {"claims": [], "ignored_segment_ids": [segment_id]}

    mock_llm.call_structured.side_effect = ignore_transcript
    entries = await encoder.encode_session("USER: some transcript", "ses-123")

    assert len(entries) == 1
    assert "Raw conversation transcript" in entries[0].content
    assert "USER: some transcript" in entries[0].content
    assert entries[0].importance == 0.8
    assert entries[0].durability == "durable"
    assert entries[0].session_id == "ses-123"

    mock_llm.call_structured.assert_called_once()
    assert mock_log_store.append.call_count == 1
    args, _ = mock_log_store.append.call_args_list[0]
    assert isinstance(args[0], LogEntry)
    assert args[0].session_id == "ses-123"
    assert len(encoder.artifacts.list_sources()) == 1
    assert encoder.artifacts.list_episodes()[0].extraction_status == "complete"


@pytest.mark.asyncio
async def test_encode_session_skips_empty_transcript(encoder, mock_llm, mock_log_store):
    entries = await encoder.encode_session("   ", "ses-123")

    assert entries == []
    mock_llm.call_structured.assert_not_called()
    mock_log_store.append.assert_not_called()
