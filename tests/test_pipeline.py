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
from mycelium.short_term import ShortTermMemoryStatus


def build_pipeline():
    encoder = SimpleNamespace(
        ingest_source=AsyncMock(return_value=IngestionResult(status="complete")),
        retry_incomplete_extractions=AsyncMock(return_value=["episode-retried"]),
    )
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult((), MemoryEvidence(), "memory context")
        )
    )
    consolidator = SimpleNamespace(run=AsyncMock(return_value=DreamReport(0, 0, 0)))
    short_term = SimpleNamespace(
        status=Mock(
            return_value=ShortTermMemoryStatus(
                pending_claims=1,
                deferred_claims=0,
                retryable_failures=0,
                total_claims=1,
                oldest_pending_at=None,
                oldest_deferred_at=None,
                ready=True,
            )
        )
    )
    return MemoryPipeline(encoder, retriever, consolidator, short_term), {
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

    assert ingestion.status == "complete"
    assert retrieval.rendered_context == "memory context"
    services["encoder"].ingest_source.assert_awaited_once_with(source)
    services["retriever"].retrieve.assert_awaited_once_with(retrieval_request)


@pytest.mark.asyncio
async def test_pipeline_consolidation_reports_retried_extraction_ids():
    pipeline, services = build_pipeline()
    request = ConsolidationRequest(dry_run=False, include_deferred=True)

    result = await pipeline.consolidate(request)

    assert result.report == DreamReport(0, 0, 0)
    assert result.retried_episode_ids == ("episode-retried",)
    services["encoder"].retry_incomplete_extractions.assert_awaited_once()
    services["consolidator"].run.assert_awaited_once_with(
        dry_run=False, include_deferred=True
    )
