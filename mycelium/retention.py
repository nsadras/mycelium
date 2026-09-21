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
from mycelium.batching import batch_items, split_text_by_tokens
from mycelium.budget import count_tokens
from mycelium.artifact_integrity import cited_source_segments
from mycelium.database import UnitOfWork
from mycelium import identity_context


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
        return [{"id": s.segment_id, "text": s.content, "speaker": s.speaker, "role": s.role,
                 "participant_id": identity_context.participant_id(source, s),
                 "source_id": source.source_id, "source_time": s.timestamp or source.occurred_at,
                 "metadata": s.metadata} for s in segments if s.role != "system"]

    async def input(self, source, batch, identifier, *, prior_ids=None, recent_claim_ids=()):
        participants = identity_context.participants(self.artifacts, source)
        if prior_ids is None:
            if self.claim_index is None:
                raise ValueError("Retention requires retrieved or explicit prior context")
            text = "\n".join(f"{s.speaker or s.role}: {s.content}" if s.speaker or s.role else s.content
                             for s in batch if s.role != "system")
            prior_ids = await related_claim_ids(self.claim_index, text)
            # Query named participants separately so a new topic does not control
            # every identity candidate. Retrieval supplies choices, never matches.
            for participant in participants:
                if not participant["subject_id"] and participant["name"]:
                    hits = await self.claim_index.search(participant["name"], limit=4)
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
        context = []
        for sid in dict.fromkeys(source.metadata.get("context_source_ids", [])):
            if sid == source.source_id:
                continue
            old = self.artifacts.get_source(sid)
            if old.status == "active":
                context.extend(self.segments(old, old.segments))
        if batch:
            start = next(i for i, segment in enumerate(source.segments) if segment.segment_id == batch[0].segment_id)
            context.extend(self.segments(source, source.segments[:start]))
        selected, used = [], 0
        for row in reversed(context):
            size = count_tokens(json.dumps(row))
            if used + size > min(6000, self.config.llm.context_window_tokens // 8):
                break
            selected.insert(0, row)
            used += size
        return {"source_type": source.source_type, "occurred_at": source.occurred_at,
                "participants": participants, "metadata": source.metadata,
                "segments": self.segments(source, batch), "context_segments": selected,
                "prior_memories": [memory_record(self.artifacts, c) for c in prior],
                "existing_subjects": candidates,
                "new_subject_ids": [stable_id("subject", identifier, i) for i in range(32)]}

    def persist(self, source, identifier, payload, result, *, replacement=None):
        """Persist inside the caller's transaction; user replacement text is exact."""
        contract.retention_model(payload).model_validate(result)
        if self.artifacts.get_source(source.source_id).status != "active":
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
                identity_context.save_binding(self.artifacts, source.source_id, pid, sid, decision_id, origin=origin)
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

    async def extract(self, source, episode, encoder):
        """Resume complete batches without asking the model to repeat extraction."""
        if not episode.extraction_batches:
            # Batch complete canonical segments, including their envelopes. Request
            # validation separately accounts for prior context, schema and output.
            batches = batch_items(source.segments, lambda ss: json.dumps(self.segments(source, ss)),
                                  max(1024, self.config.llm.context_window_tokens // 4))
            episode.extraction_batches = [ExtractionBatchState(stable_id("batch", episode.episode_id, i),
                i, [s.segment_id for s in batch]) for i, batch in enumerate(batches)]
            self.artifacts.save_episode(episode)
        context_ids, errors = set(), []
        for index in range(len(episode.extraction_batches)):
            batch = episode.extraction_batches[index]
            if batch.status == "complete":
                continue
            batch.attempt_count += 1
            unit = UnitOfWork(self.artifacts.db)
            try:
                reader = Retainer(self.llm, ArtifactStore(self.artifacts.root, db=unit), self.config, self.claim_index)
                current = reader.artifacts.get_source(source.source_id)
                reader.artifacts.get_episode(episode.episode_id)
                by_id = {s.segment_id: s for s in current.segments}
                segments = [by_id[sid] for sid in batch.segment_ids]
                payload = await reader.input(current, segments, batch.batch_id,
                                           prior_ids=None if self.segments(source, segments) else [],
                                           recent_claim_ids=episode.claim_ids)
                result = (await contract.retain(self.llm, payload) if payload["segments"]
                          else {"subjects": [], "memories": [], "changes": []})
                trial = deepcopy(episode)
                with self.artifacts.db.transaction():
                    unit.validate_reads()
                    cids = self.persist(source, batch.batch_id, payload, result)
                    trial.claim_ids = list(dict.fromkeys([*episode.claim_ids, *cids]))
                    context_ids.update(m["id"] for m in payload["prior_memories"])
                    saved_batch = trial.extraction_batches[index]
                    saved_batch.status, saved_batch.last_error, saved_batch.response = "complete", None, result
                    self._finish(source, trial, encoder)
                episode.__dict__.update(trial.__dict__)
            except (Exception, asyncio.CancelledError) as exc:
                batch.status, batch.last_error = "failed", f"{type(exc).__name__}: {exc}"
                errors.append({"stage": "retention", "source_id": source.source_id, "reason": batch.last_error})
                self._finish(source, episode, encoder)
                if isinstance(exc, asyncio.CancelledError):
                    raise
            finally:
                unit.close()
        self._finish(source, episode, encoder)
        return context_ids, errors

    def _finish(self, source, episode, encoder):
        complete = all(b.status == "complete" for b in episode.extraction_batches)
        episode.extraction_status = "complete" if complete else "partial" if episode.claim_ids else "failed"
        episode.extraction_error = next((b.last_error for b in episode.extraction_batches if b.last_error), None)
        processed = {sid for b in episode.extraction_batches if b.status == "complete" for sid in b.segment_ids}
        cited = defaultdict(list)
        for cid in episode.claim_ids:
            for p in self.artifacts.get_claim(cid).provenance:
                if p.source_id == source.source_id:
                    for sid in p.segment_ids:
                        cited[sid].append(cid)
        episode.segment_dispositions = [ExtractionSegmentDisposition(s.segment_id,
            "claimed" if cited[s.segment_id] else "source_only", cited[s.segment_id],
            "Cited by retained memory" if cited[s.segment_id] else "Not selected; source retained")
            for s in source.segments if s.segment_id in processed]
        self.artifacts.save_episode(episode)
        encoder._sync_ingestion_operation(episode)
