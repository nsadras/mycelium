"""Authoritative high-level memory lifecycle."""

from __future__ import annotations

import asyncio

from mycelium.dream import ConsolidationProcess
from mycelium.encoder import Encoder
from mycelium.operations import (
    ConsolidationRequest,
    ConsolidationResult,
    IngestionResult,
    RetrievalRequest,
    RetrievalResult,
    SourceInput,
)
from mycelium.retrieval import MemoryRetriever


class MemoryPipeline:
    def __init__(
        self,
        encoder: Encoder,
        retriever: MemoryRetriever,
        consolidator: ConsolidationProcess,
    ) -> None:
        self.encoder = encoder
        self.retriever = retriever
        self.consolidator = consolidator
        self._build_lock = asyncio.Lock()

    async def ingest_source(self, source: SourceInput) -> IngestionResult:
        return await self.encoder.ingest_source(source)

    async def retrieve_context(self, request: RetrievalRequest) -> RetrievalResult:
        return await self.retriever.retrieve(request)

    async def consolidate(
        self, request: ConsolidationRequest = ConsolidationRequest()
    ) -> ConsolidationResult:
        async with self._build_lock:
            source_ids = {
                source.source_id for source in self.encoder.artifacts.list_sources()
            }
            completed = (
                await self.encoder.extract_pending(source_ids)
                if not request.dry_run
                else []
            )
            report = await self.consolidator.run(
                dry_run=request.dry_run,
                include_deferred=request.include_deferred,
                source_ids=source_ids,
            )
            return ConsolidationResult(
                report=report, processed_episode_ids=tuple(completed)
            )
