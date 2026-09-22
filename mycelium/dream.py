"""Build Memory: durable retention followed by a bounded cited-view refresh."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from mycelium.artifacts import (
    ArtifactStore,
    DreamRunAudit,
    EpisodeManifest,
    SourceDocument,
)
from mycelium.batching import batch_items
from mycelium.claim_index import LanceClaimIndex
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.materialization import PageMaterializer
from mycelium.memory_budget import OUTPUT_TOKENS, presentation_request
from mycelium.memory_diagnostics import failure
from mycelium.models import DreamReport
from mycelium.ollama import OllamaClient
from mycelium.retention import Retainer, now_iso
from mycelium.short_term import ShortTermMemoryQueue
from mycelium.store import LogStore, WikiStore
from mycelium.views import ViewOrganizer


def _conversation_key(source: SourceDocument) -> tuple[str, str]:
    return (
        source.source_type,
        source.session_id
        if source.source_type == "agent_conversation"
        else source.source_id,
    )


@dataclass
class _BuildProgress:
    """Keep committed progress available even when a later batch fails or is cancelled."""

    report: DreamReport = field(default_factory=lambda: DreamReport(0, 0, 0))
    processed_episode_ids: list[str] = field(default_factory=list)
    pending_source_ids: set[str] = field(default_factory=set)
    created_slugs: set[str] = field(default_factory=set)
    updated_slugs: set[str] = field(default_factory=set)


class ConsolidationProcess:
    def __init__(
        self,
        llm: OllamaClient,
        wiki: WikiStore,
        logs: LogStore,
        config: Config,
        artifacts: ArtifactStore,
        claim_index: LanceClaimIndex,
    ) -> None:
        self.artifacts = artifacts
        self.logs = logs
        self.materializer = PageMaterializer(wiki, artifacts, config)
        self.retainer = Retainer(llm, artifacts, config, claim_index)
        self.views = ViewOrganizer(
            llm, artifacts, self.materializer, config, claim_index
        )
        self.short_term = ShortTermMemoryQueue(artifacts)

    async def run(
        self,
        *,
        encoder: Encoder,
        dry_run: bool = False,
        include_deferred: bool = False,
        source_ids: Sequence[str] | None = None,
    ) -> tuple[DreamReport, list[str]]:
        progress = _BuildProgress()
        if dry_run:
            return progress.report, progress.processed_episode_ids
        run_id, started = "build-" + uuid.uuid4().hex[:16], now_iso()
        captured = [
            source
            for source in self.artifacts.list_sources()
            if source.status == "active"
        ]
        sources = {
            source.source_id: source
            for source in captured
            if source.status == "active"
            and (source_ids is None or source.source_id in source_ids)
        }
        work = self._find_pending_episodes(
            sources, progress, include_deferred=include_deferred
        )
        audit = DreamRunAudit(
            run_id=run_id,
            started_at=started,
            completed_at="",
            status="running",
            source_ids=sorted(progress.pending_source_ids),
            completed_source_ids=[],
            pending_source_ids=sorted(progress.pending_source_ids),
            pages_created=0,
            pages_updated=0,
        )
        self.artifacts.save_dream_run(audit)
        cancelled = False
        groups = self._group_episodes_by_conversation(work, sources)
        try:
            for key, episodes in groups.items():
                await self._build_conversation(
                    episodes,
                    sources,
                    context_sources=[
                        source
                        for source in captured
                        if _conversation_key(source) == key
                    ],
                    encoder=encoder,
                    run_id=run_id,
                    include_deferred=include_deferred,
                    progress=progress,
                )
                self.artifacts.db.publish()
        except asyncio.CancelledError:
            cancelled = True
            progress.report.failures.append(
                {
                    "stage": "build",
                    "source_id": "",
                    "category": "cancelled",
                    "reason": "Build cancelled; committed batches will be reused",
                }
            )
            raise
        finally:
            self._finish_build_audit(audit, progress, cancelled=cancelled)
            self.artifacts.db.publish()
        return progress.report, progress.processed_episode_ids

    def _find_pending_episodes(
        self,
        sources: dict[str, SourceDocument],
        progress: _BuildProgress,
        *,
        include_deferred: bool,
    ) -> list[EpisodeManifest]:
        episodes = [
            episode
            for episode in self.artifacts.list_episodes()
            if episode.source_id in sources
        ]
        queued_claim_ids = {
            claim.claim_id
            for claim in self.short_term.claims_for_dream(
                include_deferred=include_deferred
            )
        }
        work = [
            episode
            for episode in episodes
            if episode.extraction_status != "complete"
            or queued_claim_ids.intersection(episode.claim_ids)
        ]
        # A captured source without a manifest is a visible failure, never a successful empty Build.
        missing_source_ids = sources.keys() - {
            episode.source_id for episode in episodes
        }
        for source_id in sorted(missing_source_ids):
            progress.report.failures.append(
                failure(
                    "preparation",
                    source_id,
                    ValueError("Source has no episode manifest"),
                )
            )
        progress.pending_source_ids = {
            sources[episode.source_id].raw_log_entry_id or episode.source_id
            for episode in work
        }
        progress.pending_source_ids.update(
            sources[source_id].raw_log_entry_id or source_id
            for source_id in missing_source_ids
        )
        return work

    @staticmethod
    def _group_episodes_by_conversation(
        episodes: Sequence[EpisodeManifest],
        sources: dict[str, SourceDocument],
    ) -> dict[tuple[str, str], list[EpisodeManifest]]:
        groups = defaultdict(list)
        for episode in sorted(
            episodes,
            key=lambda episode: (
                sources[episode.source_id].recorded_at,
                episode.source_id,
            ),
        ):
            groups[_conversation_key(sources[episode.source_id])].append(episode)
        return groups

    async def _build_conversation(
        self,
        episodes: Sequence[EpisodeManifest],
        sources: dict[str, SourceDocument],
        *,
        context_sources: Sequence[SourceDocument],
        encoder: Encoder,
        run_id: str,
        include_deferred: bool,
        progress: _BuildProgress,
    ) -> None:
        source = sources[episodes[0].source_id]
        try:
            context_ids: (
                Sequence[str] | set[str] | None
            ) = await self._retain_unfinished_sources(
                episodes,
                sources,
                context_sources=context_sources,
                encoder=encoder,
                progress=progress,
            )
            incoming_ids = self._claims_waiting_for_views(
                episodes, include_deferred=include_deferred
            )
            if context_ids is None:
                context_ids = await self.views.find_related_claim_ids(incoming_ids)
            await self._refresh_pending_views(
                incoming_ids,
                context_ids,
                run_id=run_id,
                first_episode=episodes[0],
                source=source,
                progress=progress,
            )
            self._mark_completed_sources(episodes, sources, progress)
        except Exception as exc:
            progress.report.failures.append(failure("build", source.source_id, exc))

    async def _retain_unfinished_sources(
        self,
        episodes: Sequence[EpisodeManifest],
        sources: dict[str, SourceDocument],
        *,
        context_sources: Sequence[SourceDocument],
        encoder: Encoder,
        progress: _BuildProgress,
    ) -> set[str] | None:
        unfinished = [
            episode for episode in episodes if episode.extraction_status != "complete"
        ]
        if not unfinished:
            return None
        context_ids, errors, warnings = await self.retainer.retain_sources(
            [sources[episode.source_id] for episode in unfinished],
            unfinished,
            encoder,
            context_sources=context_sources,
        )
        progress.report.failures.extend(errors)
        progress.report.warnings.extend(warnings)
        progress.processed_episode_ids.extend(
            episode.episode_id
            for episode in unfinished
            if episode.extraction_status == "complete"
        )
        return context_ids

    def _claims_waiting_for_views(
        self,
        episodes: Sequence[EpisodeManifest],
        *,
        include_deferred: bool,
    ) -> set[str]:
        dispositions = (
            {"pending", "routing_failed", "deferred"}
            if include_deferred
            else {"pending", "routing_failed"}
        )
        return {
            claim_id
            for episode in episodes
            for claim_id in episode.claim_ids
            if (claim := self.artifacts.get_claim(claim_id)).status == "active"
            and claim.dream_disposition in dispositions
        }

    async def _refresh_pending_views(
        self,
        incoming_ids: set[str],
        context_ids: Sequence[str] | set[str],
        *,
        run_id: str,
        first_episode: EpisodeManifest,
        source: SourceDocument,
        progress: _BuildProgress,
    ) -> None:
        batches = batch_items(
            sorted(incoming_ids),
            lambda ids: presentation_request(
                self.views.prepare_presentation_input(ids, context_ids, ())
            ),
            self.views.config.llm.context_window_tokens - OUTPUT_TOKENS - 2048,
        )
        for batch_index, claim_ids in enumerate(batches):
            try:
                pages = await self.views.refresh_views(
                    claim_ids,
                    context_ids=context_ids,
                    run_id=f"{run_id}-{first_episode.episode_id}-{batch_index}",
                )
                progress.created_slugs.update(pages.created_slugs)
                progress.updated_slugs.update(pages.updated_slugs)
            except (Exception, asyncio.CancelledError) as exc:
                self._mark_view_refresh_failed(claim_ids, run_id, exc)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                progress.report.failures.append(
                    failure("presentation", source.source_id, exc)
                )

    def _mark_view_refresh_failed(
        self,
        claim_ids: Sequence[str],
        run_id: str,
        error: Exception | asyncio.CancelledError,
    ) -> None:
        with self.artifacts.db.transaction():
            for claim_id in claim_ids:
                claim = self.artifacts.get_claim(claim_id)
                claim.dream_disposition = "routing_failed"
                claim.dream_disposition_reason = f"{type(error).__name__}: {error}"
                claim.dream_disposition_at, claim.dream_run_id = now_iso(), run_id
                self.artifacts.save_claim(claim)

    def _mark_completed_sources(
        self,
        episodes: Sequence[EpisodeManifest],
        sources: dict[str, SourceDocument],
        progress: _BuildProgress,
    ) -> None:
        for episode in episodes:
            source = sources[episode.source_id]
            report_id = source.raw_log_entry_id or source.source_id
            unfinished = any(
                self.artifacts.get_claim(claim_id).dream_disposition
                in {"pending", "routing_failed"}
                for claim_id in episode.claim_ids
                if self.artifacts.get_claim(claim_id).status == "active"
            )
            if episode.extraction_status == "complete" and not unfinished:
                with self.artifacts.db.transaction():
                    if source.raw_log_entry_id:
                        self.logs.mark_consolidated([source.raw_log_entry_id])
                progress.report.completed_source_ids.append(report_id)
                progress.pending_source_ids.discard(report_id)

    def _finish_build_audit(
        self,
        audit: DreamRunAudit,
        progress: _BuildProgress,
        *,
        cancelled: bool,
    ) -> None:
        report = progress.report
        report.pages_created = len(progress.created_slugs)
        report.pages_updated = len(progress.updated_slugs - progress.created_slugs)
        report.entries_consolidated = len(report.completed_source_ids)
        report.pending_source_ids = sorted(progress.pending_source_ids)
        report.reconsolidation_proposal_ids = [
            proposal.proposal_id
            for proposal in self.artifacts.list_reconsolidation_proposals(
                status="pending"
            )
        ]
        audit.completed_at = now_iso()
        audit.status = (
            "cancelled"
            if cancelled
            else "partial"
            if progress.pending_source_ids or report.failures
            else "complete"
        )
        audit.completed_source_ids = report.completed_source_ids
        audit.pending_source_ids = report.pending_source_ids
        audit.pages_created = report.pages_created
        audit.pages_updated = report.pages_updated
        audit.failures = report.failures
        audit.reconsolidation_proposal_ids = report.reconsolidation_proposal_ids
        audit.warnings = report.warnings
        self.artifacts.save_dream_run(audit)
