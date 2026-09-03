"""Authoritative high-level memory lifecycle."""

from __future__ import annotations

from datetime import datetime

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
from mycelium.short_term import ShortTermMemoryQueue, ShortTermMemoryStatus


class MemoryPipeline:
    def __init__(
        self,
        encoder: Encoder,
        retriever: MemoryRetriever,
        consolidator: ConsolidationProcess,
        short_term: ShortTermMemoryQueue,
    ) -> None:
        self.encoder = encoder
        self.retriever = retriever
        self.consolidator = consolidator
        self.short_term = short_term

    async def ingest_source(self, source: SourceInput) -> IngestionResult:
        return await self.encoder.ingest_source(source)

    async def retrieve_context(self, request: RetrievalRequest) -> RetrievalResult:
        return await self.retriever.retrieve(request)

    async def consolidate(
        self, request: ConsolidationRequest = ConsolidationRequest()
    ) -> ConsolidationResult:
        retried_episode_ids = (
            await self.encoder.retry_incomplete_extractions()
            if not request.dry_run
            else []
        )
        report = await self.consolidator.run(
            dry_run=request.dry_run,
            include_deferred=request.include_deferred,
        )
        return ConsolidationResult(
            report=report,
            retried_episode_ids=tuple(retried_episode_ids),
        )

    def consolidation_status(
        self, *, now: datetime | None = None
    ) -> ShortTermMemoryStatus:
        return self.short_term.status(now=now)

    async def consolidate_if_ready(
        self, *, now: datetime | None = None, dry_run: bool = False
    ) -> ConsolidationResult | None:
        retried_episode_ids = (
            await self.encoder.retry_incomplete_extractions()
            if not dry_run
            else []
        )
        status = self.consolidation_status(now=now)
        if not status.ready:
            return None
        report = await self.consolidator.run(
            dry_run=dry_run,
            include_deferred=status.include_deferred,
        )
        return ConsolidationResult(
            report=report,
            retried_episode_ids=tuple(retried_episode_ids),
        )
