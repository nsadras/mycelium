import pytest
from unittest.mock import AsyncMock, MagicMock
from mycelium.artifacts import ArtifactStore
from mycelium.encoder import Encoder
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
async def test_encode_session_skips_empty_transcript(encoder, mock_llm, mock_log_store):
    entries = await encoder.encode_session("   ", "ses-123")

    assert entries == []
    mock_llm.call_structured.assert_not_called()
    mock_log_store.append.assert_not_called()
