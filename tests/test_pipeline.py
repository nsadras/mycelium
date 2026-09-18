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


def build_pipeline(tmp_path):
    encoder = SimpleNamespace(
        ingest_source=AsyncMock(return_value=IngestionResult(status="captured")),
    )
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=RetrievalResult((), MemoryEvidence(), "memory context")
        )
    )
    consolidator = SimpleNamespace(run=AsyncMock(return_value=(DreamReport(0, 0, 0), ["episode-retried"])))
    encoder.artifacts = SimpleNamespace(root=tmp_path / "artifacts", list_sources=Mock(return_value=[]))
    consolidator.materializer = SimpleNamespace(wiki=SimpleNamespace(wiki_dir=tmp_path / "wiki"))
    return MemoryPipeline(encoder, retriever, consolidator), {
        "encoder": encoder,
        "retriever": retriever,
        "consolidator": consolidator,
    }


@pytest.mark.asyncio
async def test_pipeline_exposes_typed_ingestion_and_retrieval_operations(tmp_path):
    pipeline, services = build_pipeline(tmp_path)
    source = SourceInput("USER: Keep this.", "session-one")
    retrieval_request = RetrievalRequest("What should be kept?")

    ingestion = await pipeline.ingest_source(source)
    retrieval = await pipeline.retrieve_context(retrieval_request)

    assert ingestion.status == "captured"
    assert retrieval.rendered_context == "memory context"
    services["encoder"].ingest_source.assert_awaited_once_with(source)
    services["retriever"].retrieve.assert_awaited_once_with(retrieval_request)


@pytest.mark.asyncio
async def test_pipeline_consolidation_reports_retried_extraction_ids(tmp_path):
    pipeline, services = build_pipeline(tmp_path)
    request = ConsolidationRequest(dry_run=False, include_deferred=True)

    result = await pipeline.consolidate(request)

    assert result.report == DreamReport(0, 0, 0)
    assert result.processed_episode_ids == ("episode-retried",)
    services["consolidator"].run.assert_awaited_once_with(
        encoder=services["encoder"], dry_run=False, include_deferred=True, source_ids=set()
    )
