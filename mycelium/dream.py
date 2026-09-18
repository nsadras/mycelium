"""Build Memory: durable retention followed by a bounded cited-view refresh."""

import asyncio
import uuid
import json

from mycelium.batching import batch_items

from mycelium.artifacts import DreamRunAudit
from mycelium.materialization import PageMaterializer
from mycelium.models import DreamReport
from mycelium.retention import Retainer, now_iso
from mycelium.short_term import ShortTermMemoryQueue
from mycelium.views import ViewOrganizer


class ConsolidationProcess:
    def __init__(self, llm, wiki, logs, config, artifacts, claim_index):
        self.artifacts, self.logs = artifacts, logs
        self.materializer = PageMaterializer(wiki, artifacts, config)
        self.retainer = Retainer(llm, artifacts, config, claim_index)
        self.views = ViewOrganizer(llm, artifacts, self.materializer, config, claim_index)
        self.short_term = ShortTermMemoryQueue(artifacts)

    async def run(self, *, encoder, dry_run=False, include_deferred=False, source_ids=None):
        report = DreamReport(0, 0, 0)
        processed = []
        if dry_run:
            return report, processed
        run_id, started = "build-" + uuid.uuid4().hex[:16], now_iso()
        sources = {s.source_id: s for s in self.artifacts.list_sources()
                   if s.status == "active" and (source_ids is None or s.source_id in source_ids)}
        episodes = [e for e in self.artifacts.list_episodes() if e.source_id in sources]
        queued = {c.claim_id for c in self.short_term.claims_for_dream(include_deferred=include_deferred)}
        work = [e for e in episodes if e.extraction_status != "complete" or queued.intersection(e.claim_ids)]
        # A captured source without a manifest is a visible failure, never a successful empty Build.
        missing = sources.keys() - {e.source_id for e in episodes}
        for sid in sorted(missing):
            report.failures.append({"stage": "preparation", "source_id": sid, "reason": "Source has no episode manifest"})
        pending = {sources[e.source_id].raw_log_entry_id or e.source_id for e in work}
        pending.update(sources[sid].raw_log_entry_id or sid for sid in missing)
        audit = DreamRunAudit(run_id, started, "", "running", sorted(pending), [], sorted(pending), 0, 0)
        self.artifacts.save_dream_run(audit)
        created, updated = set(), set()
        cancelled = False
        try:
            for episode in work:
                source = sources[episode.source_id]
                report_id = source.raw_log_entry_id or source.source_id
                context_ids = None
                try:
                    if episode.extraction_status != "complete":
                        context_ids, errors = await self.retainer.extract(source, episode, encoder)
                        report.failures.extend(errors)
                        if episode.extraction_status == "complete":
                            processed.append(episode.episode_id)
                    incoming = {cid for cid in episode.claim_ids
                                if (claim := self.artifacts.get_claim(cid)).status == "active"
                                and claim.dream_disposition in ({"pending", "routing_failed", "deferred"}
                                                              if include_deferred else {"pending", "routing_failed"})}
                    batches = batch_items(sorted(incoming),
                        lambda ids: json.dumps([self.artifacts.get_claim(cid).text for cid in ids]),
                        max(1024, self.views.config.llm.context_window_tokens // 4))
                    for batch_index, batch in enumerate(batches):
                        try:
                            pages = await self.views.refresh(batch, context_ids=context_ids,
                                run_id=f"{run_id}-{episode.episode_id}-{batch_index}")
                            created.update(pages.created_slugs)
                            updated.update(pages.updated_slugs)
                        except (Exception, asyncio.CancelledError) as exc:
                            with self.artifacts.db.transaction():
                                for cid in batch:
                                    claim = self.artifacts.get_claim(cid)
                                    claim.dream_disposition = "routing_failed"
                                    claim.dream_disposition_reason = f"{type(exc).__name__}: {exc}"
                                    claim.dream_disposition_at, claim.dream_run_id = now_iso(), run_id
                                    self.artifacts.save_claim(claim)
                            if isinstance(exc, asyncio.CancelledError):
                                raise
                            report.failures.append({"stage": "presentation", "source_id": source.source_id,
                                                    "reason": f"{type(exc).__name__}: {exc}"})
                    unfinished = any(self.artifacts.get_claim(cid).dream_disposition in {"pending", "routing_failed"}
                                     for cid in episode.claim_ids if self.artifacts.get_claim(cid).status == "active")
                    if episode.extraction_status == "complete" and not unfinished:
                        with self.artifacts.db.transaction():
                            if source.raw_log_entry_id:
                                self.logs.mark_consolidated([source.raw_log_entry_id])
                        report.completed_source_ids.append(report_id)
                        pending.discard(report_id)
                except Exception as exc:
                    report.failures.append({"stage": "build", "source_id": source.source_id,
                                            "reason": f"{type(exc).__name__}: {exc}"})
                self.artifacts.db.publish()
        except asyncio.CancelledError:
            cancelled = True
            report.failures.append({"stage": "build", "source_id": "", "reason": "Build cancelled; committed batches will be reused"})
            raise
        finally:
            report.pages_created, report.pages_updated = len(created), len(updated - created)
            report.entries_consolidated = len(report.completed_source_ids)
            report.pending_source_ids = sorted(pending)
            report.reconsolidation_proposal_ids = [p.proposal_id for p in self.artifacts.list_reconsolidation_proposals(status="pending")]
            audit.completed_at = now_iso()
            audit.status = "cancelled" if cancelled else "partial" if pending or report.failures else "complete"
            audit.completed_source_ids, audit.pending_source_ids = report.completed_source_ids, report.pending_source_ids
            audit.pages_created, audit.pages_updated = report.pages_created, report.pages_updated
            audit.failures, audit.reconsolidation_proposal_ids = report.failures, report.reconsolidation_proposal_ids
            self.artifacts.save_dream_run(audit)
            self.artifacts.db.publish()
        return report, processed
