"""Retain source-backed statements once per bounded, durable source batch."""

import asyncio
from copy import deepcopy
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from mycelium import memory_contract as contract
from mycelium.artifacts import (
    ArtifactStore, ClaimEntityReference, ClaimProvenance, EntityRecord, EntityResolutionDecision,
    ExtractionBatchState, ExtractionSegmentDisposition, MemoryClaim, ReconsolidationProposal,
)
from mycelium.batching import split_text_by_tokens
from mycelium.budget import ContextBudgetError
from mycelium.memory_budget import fit_retention
from mycelium.artifact_integrity import cited_source_segments
from mycelium.database import UnitOfWork
from mycelium import identity_context
from mycelium.memory_diagnostics import failure
from mycelium.telemetry import trace_operation


def stable_id(kind, *parts):
    return kind + "-" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def memory_record(artifacts, claim):
    refs = artifacts.list_entity_references(claim_id=claim.claim_id, status="active")
    provenance = []
    for _, source, segments in cited_source_segments(artifacts, claim):
        for segment in segments:
            row = {"speaker": segment.speaker, "role": segment.role,
                   "source_type": source.source_type,
                   "source_time": segment.timestamp or source.occurred_at}
            bound = identity_context.binding(artifacts, identity_context.participant_id(source, segment))
            if bound:
                row["speaker_subject_id"] = bound["entity_id"]
            if row not in provenance:
                provenance.append(row)
    return {"id": claim.claim_id, "text": claim.text,
            "subject_ids": sorted({r.entity_id for r in refs if r.entity_id}),
            "provenance": provenance,
            "revisions": claim.links, "temporal": claim.facets.get("temporal", [])}


async def related_claim_ids(index, text):
    """Learned candidate retrieval; this does not decide identity or truth."""
    ids = []
    for chunk in split_text_by_tokens(text, 1200):
        ids.extend(hit.claim_id for hit in await index.search(chunk, limit=24))
    return list(dict.fromkeys(ids))[:48]


class Retainer:
    def __init__(self, llm, artifacts, config, claim_index=None):
        self.llm, self.artifacts, self.config, self.claim_index = llm, artifacts, config, claim_index

    @staticmethod
    def segments(source, segments):
        return [{"id": s.segment_id, "index": s.index, "text": s.content, "speaker": s.speaker, "role": s.role,
                 "participant_id": identity_context.participant_id(source, s),
                 "source_id": source.source_id, "source_time": s.timestamp or source.occurred_at,
                 "metadata": s.metadata} for s in segments if s.role != "system"]

    async def input(self, source, batch, identifier, *, prior_ids=None, recent_claim_ids=(), sources=None, context_sources=()):
        sources = sources or [source]
        context_sources = {item.source_id: item for item in [*context_sources, *sources] if item.status == "active"}
        for item in sources:
            for sid in item.metadata.get("context_source_ids", []):
                old = self.artifacts.get_source(sid)
                if old.status == "active":
                    context_sources[sid] = old
        participants = [p for item in context_sources.values() for p in identity_context.participants(self.artifacts, item)]
        segment_sources = {s.segment_id: item for item in sources for s in item.segments}
        if prior_ids is None:
            if self.claim_index is None:
                raise ValueError("Retention requires retrieved or explicit prior context")
            text = "\n".join(f"{s.speaker or s.role}: {s.content}" if s.speaker or s.role else s.content
                             for s in batch if s.role != "system")
            prior_ids = await related_claim_ids(self.claim_index, text)
            # Query named participants separately so a new topic does not control
            # every identity candidate. Retrieval supplies choices, never matches.
            names = dict.fromkeys(p["name"] for p in participants if not p["subject_id"] and p["name"])
            for name in names:
                hits = await self.claim_index.search(name, limit=4)
                prior_ids.extend(hit.claim_id for hit in hits)
        # Preserve a bounded amount of the current source's established context
        # even when its new topic retrieves different evidence. IDs only select
        # context; the model still decides whether any identity is the same.
        prior_ids = dict.fromkeys([*reversed(list(recent_claim_ids)[-12:]), *prior_ids])
        prior = [self.artifacts.get_claim(cid) for cid in prior_ids]
        prior = [c for c in prior if c.status == "active" and c.dream_disposition != "excluded_source_policy"][:48]
        entity_ids = self.artifacts.entities_for_claims({c.claim_id for c in prior})
        entity_ids.update(self.artifacts.entities_for_claims(set(recent_claim_ids)))
        entity_ids.update(p["subject_id"] for p in participants if p["subject_id"])
        if any(e.entity_id == "you" for e in self.artifacts.list_entities(status="active")):
            entity_ids.add("you")
        subjects = [self.artifacts.get_entity(eid) for eid in sorted(entity_ids)]
        candidates = []
        for entity in subjects:
            if entity.status != "active":
                continue
            evidence = []
            refs = self.artifacts.list_entity_references(entity_id=entity.entity_id, status="active")
            ids = {r.claim_id for r in refs}
            ordered = dict.fromkeys([*(c.claim_id for c in prior if c.claim_id in ids),
                                     *reversed(sorted(ids))])
            for cid in ordered:
                claim = self.artifacts.get_claim(cid)
                if claim.status == "active" and claim.dream_disposition != "excluded_source_policy":
                    evidence.append({"id": cid, "text": claim.text})
                    if len(evidence) == 2:
                        break
            candidates.append({"id": entity.entity_id, "title": entity.title,
                               "entity_type": entity.entity_type, "aliases": entity.aliases,
                               "evidence": evidence})
        new_ids = {s.segment_id for s in batch}
        # The whole conversation is interpretation context when it fits, including
        # later clarifications. Only the designated new segments may be extracted.
        context = [row for item in sorted(context_sources.values(), key=lambda s: (s.recorded_at, s.source_id))
                   for row in self.segments(item, item.segments) if row["id"] not in new_ids]
        return {"source_type": source.source_type, "occurred_at": source.occurred_at,
                "participants": participants, "metadata": source.metadata,
                "segments": [row for s in batch for row in self.segments(segment_sources[s.segment_id], [s])],
                "context_segments": context,
                "prior_memories": [memory_record(self.artifacts, c) for c in prior],
                "existing_subjects": candidates,
                "new_subject_ids": [stable_id("subject", identifier, i) for i in range(32)]}

    def persist(self, source, identifier, payload, result, *, replacement=None):
        """Persist inside the caller's transaction; user replacement text is exact."""
        contract.retention_model(payload).model_validate({k: v for k, v in result.items() if k != "_rejections"})
        for sid in {s["source_id"] for s in payload["segments"]}:
            if self.artifacts.get_source(sid).status != "active":
                raise ValueError("Source was retracted during retention")
        for change in result["changes"]:
            if self.artifacts.get_claim(change["earlier_id"]).status != "active":
                raise ValueError("Prior evidence changed during retention")
        now = now_iso()
        declarations = {s["id"]: s for s in result["subjects"]}
        subjects = {**declarations, **{s["id"]: s for s in payload["existing_subjects"]}}
        evidence = {s["id"]: s for s in [*payload["segments"], *payload["context_segments"]]}
        claims, mapped = [], {}
        for row in result["memories"]:
            by_source = defaultdict(list)
            for sid in row["segment_ids"]:
                s = evidence[sid]
                by_source[(s["source_id"], s["speaker"])].append(sid)
            roles = {evidence[sid]["role"] for sid in row["segment_ids"]}
            modality = "tool" if roles == {"tool"} else "mixed" if "tool" in roles else "speech"
            claim = replacement or MemoryClaim(stable_id("claim", identifier, row["id"]), row["text"], [],
                [ClaimProvenance(sid, sorted(set(ids)), self.artifacts.get_source(sid).raw_log_entry_id, speaker)
                 for (sid, speaker), ids in by_source.items()], now, evidence_modality=modality)
            mapped[row["id"]] = claim.claim_id
            if claim.claim_id not in {c.claim_id for c in claims}:
                claims.append(claim)
        if replacement is not None and not claims:
            claims.append(replacement)
        for s in result["subjects"]:
            try:
                entity = self.artifacts.get_entity(s["id"])
            except FileNotFoundError:
                entity = EntityRecord(s["id"], s["entity_type"], s["title"], s["id"], [], "active", now, now,
                                      materialization_state="provisional")
            self.artifacts.save_entity(entity)
        for claim in claims:
            self.artifacts.save_claim(claim)
        used = {sid for row in result["memories"] for sid in row["subject_ids"]} | declarations.keys()
        decisions = {}
        for sid in sorted(used):
            subject = subjects[sid]
            # Reusing an exact bound identity also reuses its review record,
            # even when the model omits the optional existing-subject declaration.
            pids = sorted(set(declarations.get(sid, {}).get("participant_ids", [])) |
                          {p["id"] for p in payload["participants"] if p["subject_id"] == sid})
            bound = [identity_context.binding(self.artifacts, pid) for pid in pids]
            decision_id = next((b["decision_id"] for b in bound if b), stable_id("identity", source.source_id, sid))
            cids = {mapped[m["id"]] for m in result["memories"] if sid in m["subject_ids"]}
            cited = {s for c in claims if c.claim_id in cids for p in c.provenance for s in p.segment_ids}
            cited.update(s["id"] for s in payload["segments"] if s.get("participant_id") in pids)
            try:
                decision = self.artifacts.get_entity_resolution_decision(decision_id)
            except FileNotFoundError:
                decision = EntityResolutionDecision(decision_id, "participant_resolution" if pids else "entity_creation",
                    sid, subject["entity_type"], subject["title"], [source.source_id], [], [], .8,
                    "Subject selected from cited source and candidate evidence", "accepted", identifier, now)
            if decision.entity_id != sid:
                raise ValueError("Identity changed during retention")
            decision.supporting_claim_ids = sorted(set(decision.supporting_claim_ids) | cids)
            decision.supporting_segment_ids = sorted(set(decision.supporting_segment_ids) | cited)
            decision.source_ids = sorted(set(decision.source_ids) | {p.source_id for c in claims if c.claim_id in cids for p in c.provenance})
            decision.participant_ids = sorted(set(decision.participant_ids) | set(pids))
            self.artifacts.save_entity_resolution_decision(decision)
            decisions[sid] = decision_id
            for pid in pids:
                previous = identity_context.binding(self.artifacts, pid)
                origin = previous["origin"] if previous else next(p["binding_origin"] for p in payload["participants"] if p["id"] == pid) or "model"
                participant_source = next(p["source_id"] for p in payload["participants"] if p["id"] == pid)
                identity_context.save_binding(self.artifacts, participant_source, pid, sid, decision_id, origin=origin)
        for row in result["memories"]:
            for sid in row["subject_ids"]:
                self.artifacts.save_entity_reference(ClaimEntityReference(
                    stable_id("ref", mapped[row["id"]], sid), mapped[row["id"]], "subject", subjects[sid]["title"],
                    sid, .8, "Retained with cited source", "extraction", identifier, "active", now,
                    identity_decision_id=decisions[sid]))
        if replacement is None:
            for change in result["changes"]:
                later, earlier = mapped[change["later_id"]], change["earlier_id"]
                self.artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
                    stable_id("proposal", later, earlier), [later], [earlier], change["relation"], change["reason"],
                    .8, identifier, now, affected_entity_ids=sorted(used)))
        return [c.claim_id for c in claims]

    async def plan(self, sources, episodes, context_sources):
        """Replan only unprocessed evidence; completed records keep their exact IDs."""
        completed = {sid for e in episodes for b in e.extraction_batches if b.status == "complete" for sid in b.segment_ids}
        remaining = [segment for source in sources for segment in source.segments if segment.segment_id not in completed]
        plans = []

        async def measure(segments):
            identifier = stable_id("batch", [s.segment_id for s in segments])
            payload = await self.input(sources[0], segments, identifier, sources=sources,
                                       context_sources=context_sources, prior_ids=[])
            fit_retention(payload, self.config.llm.context_window_tokens)
            return identifier

        while remaining:
            try:
                identifier = await measure(remaining)
                size = len(remaining)
            except ContextBudgetError:
                low, high, size = 1, len(remaining) - 1, 0
                while low <= high:
                    middle = (low + high) // 2
                    try:
                        identifier = await measure(remaining[:middle])
                        size, low = middle, middle + 1
                    except ContextBudgetError:
                        high = middle - 1
                if not size:
                    await measure(remaining[:1])  # Surface the actual capacity failure.
                identifier = stable_id("batch", [s.segment_id for s in remaining[:size]])
            plans.append((identifier, {s.segment_id for s in remaining[:size]}))
            remaining = remaining[size:]
        with self.artifacts.db.transaction():
            for episode in episodes:
                previous = {b.batch_id: b for b in episode.extraction_batches}
                episode.extraction_batches = [b for b in previous.values() if b.status == "complete"]
                for identifier, ids in plans:
                    own_ids = [sid for sid in episode.segment_ids if sid in ids]
                    if own_ids:
                        prior = previous.get(identifier)
                        episode.extraction_batches.append(ExtractionBatchState(identifier,
                            len(episode.extraction_batches), own_ids,
                            attempt_count=prior.attempt_count if prior else 0))
                self.artifacts.save_episode(episode)
        return plans

    async def extract(self, sources, episodes, encoder, *, context_sources=()):
        """One request can cover several captures; each source keeps its own manifest."""
        plans = await self.plan(sources, episodes, context_sources)
        context_ids, errors, warnings = set(), [], []
        for identifier, segment_ids in plans:
            members = [e for e in episodes if set(e.segment_ids) & segment_ids]
            for episode in members:
                next(b for b in episode.extraction_batches if b.batch_id == identifier).attempt_count += 1
            unit = UnitOfWork(self.artifacts.db)
            try:
                reader = Retainer(self.llm, ArtifactStore(self.artifacts.root, db=unit), self.config, self.claim_index)
                current = [reader.artifacts.get_source(s.source_id) for s in sources]
                earlier = [reader.artifacts.get_source(s.source_id) for s in context_sources]
                for episode in episodes:
                    reader.artifacts.get_episode(episode.episode_id)
                segments = [s for source in current for s in source.segments if s.segment_id in segment_ids]
                payload = await reader.input(current[0], segments, identifier, sources=current, context_sources=earlier,
                    prior_ids=None if any(s.role != "system" for s in segments) else [],
                    recent_claim_ids=[cid for e in episodes for cid in e.claim_ids])
                payload, budget = fit_retention(payload, self.config.llm.context_window_tokens)
                with trace_operation("retention-batch", batch_id=identifier, **budget):
                    result = (await contract.retain(self.llm, payload) if payload["segments"]
                              else {"subjects": [], "memories": [], "changes": []})
                trials = deepcopy(members)
                with self.artifacts.db.transaction():
                    unit.validate_reads()
                    cids = self.persist(current[0], identifier, payload, result)
                    context_ids.update(m["id"] for m in payload["prior_memories"])
                    for trial in trials:
                        batch = next(b for b in trial.extraction_batches if b.batch_id == identifier)
                        own = [cid for cid in cids if any(p.source_id == trial.source_id and set(p.segment_ids) & set(batch.segment_ids)
                               for p in self.artifacts.get_claim(cid).provenance)]
                        trial.claim_ids = list(dict.fromkeys([*trial.claim_ids, *own]))
                        batch.status, batch.last_error, batch.response = "complete", None, result
                        batch.diagnostics = budget
                        self._finish(next(s for s in current if s.source_id == trial.source_id), trial, encoder)
                for episode, trial in zip(members, trials):
                    episode.__dict__.update(trial.__dict__)
                warnings.extend({"stage": "retention", "batch_id": identifier,
                    **{k: v for k, v in rejection.items() if k not in {"record", "request_ids", "request_citations"}}}
                    for rejection in result.get("_rejections", []))
            except (Exception, asyncio.CancelledError) as exc:
                for episode in members:
                    batch = next(b for b in episode.extraction_batches if b.batch_id == identifier)
                    batch.status, batch.last_error = "failed", f"{type(exc).__name__}: {exc}"
                    errors.append({**failure("retention", episode.source_id, exc), "batch_id": identifier})
                    self._finish(next(s for s in sources if s.source_id == episode.source_id), episode, encoder)
                if isinstance(exc, asyncio.CancelledError):
                    raise
            finally:
                unit.close()
        for source, episode in zip(sources, episodes):
            self._finish(source, episode, encoder)
        return context_ids, errors, warnings

    def _finish(self, source, episode, encoder):
        complete = all(b.status == "complete" for b in episode.extraction_batches)
        episode.extraction_status = "complete" if complete else "partial" if episode.claim_ids else "failed"
        episode.extraction_error = next((b.last_error for b in episode.extraction_batches if b.last_error), None)
        processed = {sid for b in episode.extraction_batches if b.status == "complete" for sid in b.segment_ids}
        rejected = {sid for b in episode.extraction_batches if b.response and b.response.get("_rejections") for sid in b.segment_ids}
        cited = defaultdict(list)
        for cid in episode.claim_ids:
            for p in self.artifacts.get_claim(cid).provenance:
                if p.source_id == source.source_id:
                    for sid in p.segment_ids:
                        cited[sid].append(cid)
        episode.segment_dispositions = [ExtractionSegmentDisposition(s.segment_id,
            "claimed" if cited[s.segment_id] else "source_only", cited[s.segment_id],
            "Cited by retained memory" if cited[s.segment_id] else
            "Not retained; inspect rejected records in batch response" if s.segment_id in rejected else "Not selected; source retained")
            for s in source.segments if s.segment_id in processed]
        self.artifacts.save_episode(episode)
        encoder._sync_ingestion_operation(episode)
