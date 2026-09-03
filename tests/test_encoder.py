import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from mycelium.artifacts import ArtifactStore
from mycelium.encoder import Encoder
from mycelium.config import Config
from mycelium.operations import SourceInput

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


@pytest.mark.asyncio
async def test_ingest_source_returns_an_explicit_empty_result(
    encoder, mock_llm, mock_log_store
):
    result = await encoder.ingest_source(SourceInput(
        transcript="   ", session_id="ses-123"
    ))

    assert result.status == "empty"
    assert result.log_entries == ()
    assert result.source_ids == ()
    assert result.episode_ids == ()
    assert result.claim_ids == ()
    assert result.operation_ids == ()
    mock_llm.call_structured.assert_not_called()
    mock_log_store.append.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_source_derives_segments_when_the_caller_omits_them(
    encoder, mock_llm
):
    with patch.object(
        encoder, "_extract_claims", new_callable=AsyncMock
    ) as extract_claims:
        result = await encoder.ingest_source(SourceInput(
            transcript="USER: Keep this memory.",
            session_id="ses-123",
            source_type="multi_party_conversation",
            idempotency_key="derive-default-segments",
        ))

    source = encoder.artifacts.get_source(result.source_ids[0])
    assert [segment.content for segment in source.segments] == ["Keep this memory."]
    extract_claims.assert_awaited_once()
    mock_llm.call_structured.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_source_rejects_explicitly_empty_segments_for_nonempty_input(
    encoder, mock_llm
):
    with pytest.raises(
        ValueError, match="non-empty source transcript must produce at least one segment"
    ):
        await encoder.ingest_source(SourceInput(
            transcript="USER: Keep this memory.",
            session_id="ses-123",
            segments=(),
            idempotency_key="explicit-empty-segments",
        ))

    operation = encoder.artifacts.list_ingestion_operations()[0]
    assert operation.status == "failed"
    assert "must produce at least one segment" in (operation.error or "")
    assert encoder.artifacts.list_sources() == []
    mock_llm.call_structured.assert_not_called()
