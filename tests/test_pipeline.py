from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mycelium.models import DreamReport
from mycelium.operations import (
    ConsolidationRequest,
    IngestionResult,
    MemoryEvidence,
    RetrievalRequest,
    RetrievalResult,
    SourceInput,
)
from mycelium.pipeline import MemoryPipeline


def build_pipeline():
    encoder = SimpleNamespace(
        ingest_source=AsyncMock(return_value=IngestionResult(status="captured")),
        extract_pending=AsyncMock(return_value=["episode-retried"]),
    )
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult((), MemoryEvidence(), "memory context")
        )
    )
    consolidator = SimpleNamespace(run=AsyncMock(return_value=DreamReport(0, 0, 0)))
    encoder.artifacts = SimpleNamespace(list_sources=Mock(return_value=[]))
    return MemoryPipeline(encoder, retriever, consolidator), {
        "encoder": encoder,
        "retriever": retriever,
        "consolidator": consolidator,
    }


@pytest.mark.asyncio
async def test_pipeline_exposes_typed_ingestion_and_retrieval_operations():
    pipeline, services = build_pipeline()
    source = SourceInput("USER: Keep this.", "session-one")
    retrieval_request = RetrievalRequest("What should be kept?")

    ingestion = await pipeline.ingest_source(source)
    retrieval = await pipeline.retrieve_context(retrieval_request)

    assert ingestion.status == "captured"
    assert retrieval.rendered_context == "memory context"
    services["encoder"].ingest_source.assert_awaited_once_with(source)
    services["retriever"].retrieve.assert_awaited_once_with(retrieval_request)


@pytest.mark.asyncio
async def test_pipeline_consolidation_reports_retried_extraction_ids():
    pipeline, services = build_pipeline()
    request = ConsolidationRequest(dry_run=False, include_deferred=True)

    result = await pipeline.consolidate(request)

    assert result.report == DreamReport(0, 0, 0)
    assert result.processed_episode_ids == ("episode-retried",)
    services["encoder"].extract_pending.assert_awaited_once()
    services["consolidator"].run.assert_awaited_once_with(
        dry_run=False, include_deferred=True, source_ids=set()
    )
