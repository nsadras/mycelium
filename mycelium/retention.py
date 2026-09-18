"""Retain source-backed statements once per bounded, durable source batch."""

import asyncio
from copy import deepcopy
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from mycelium import memory_contract as contract
from mycelium.artifacts import (
    ClaimEntityReference, ClaimProvenance, EntityRecord, EntityResolutionDecision,
    ExtractionBatchState, ExtractionSegmentDisposition, MemoryClaim, ReconsolidationProposal,
)
from mycelium.batching import batch_items, split_text_by_tokens
from mycelium.budget import count_tokens
from mycelium.artifact_integrity import cited_source_segments


def stable_id(kind, *parts):
    return kind + "-" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def memory_record(artifacts, claim):
    cited_source_segments(artifacts, claim)
    refs = artifacts.list_entity_references(claim_id=claim.claim_id, status="active")
    return {"id": claim.claim_id, "text": claim.text,
            "subject_ids": sorted({r.entity_id for r in refs if r.entity_id}),
            "source_time": [artifacts.get_source(p.source_id).occurred_at for p in claim.provenance],
            "segment_ids": [sid for p in claim.provenance for sid in p.segment_ids],
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
                 "source_id": source.source_id, "source_time": s.timestamp or source.occurred_at,
                 "metadata": s.metadata} for s in segments if s.role != "system"]

    async def input(self, source, batch, identifier, *, prior_ids=None):
        if prior_ids is None:
            if self.claim_index is None:
                raise ValueError("Retention requires retrieved or explicit prior context")
            prior_ids = await related_claim_ids(self.claim_index, "\n".join(s.content for s in batch))
        prior = [self.artifacts.get_claim(cid) for cid in dict.fromkeys(prior_ids)]
        prior = [c for c in prior if c.status == "active" and c.dream_disposition != "excluded_source_policy"]
        entity_ids = self.artifacts.entities_for_claims({c.claim_id for c in prior})
        if any(e.entity_id == "you" for e in self.artifacts.list_entities(status="active")):
            entity_ids.add("you")
        subjects = [self.artifacts.get_entity(eid) for eid in sorted(entity_ids)]
        context = []
        for sid in source.metadata.get("context_source_ids", []):
            old = self.artifacts.get_source(sid)
            if old.status == "active":
                context.extend(self.segments(old, old.segments))
        selected, used = [], 0
        for row in reversed(context):
            size = count_tokens(json.dumps(row))
            if used + size > min(6000, self.config.llm.context_window_tokens // 8):
                break
            selected.insert(0, row)
            used += size
        return {"source_type": source.source_type, "occurred_at": source.occurred_at,
                "participants": source.participants, "metadata": source.metadata,
                "segments": self.segments(source, batch), "context_segments": selected,
                "prior_memories": [memory_record(self.artifacts, c) for c in prior],
                "existing_subjects": [{"id": e.entity_id, "title": e.title, "entity_type": e.entity_type}
                                      for e in subjects if e.status == "active"],
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
        subjects = {s["id"]: s for s in result["subjects"]}
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
        for row in result["memories"]:
            for sid in row["subject_ids"]:
                self.artifacts.save_entity_reference(ClaimEntityReference(
                    stable_id("ref", mapped[row["id"]], sid), mapped[row["id"]], "subject", subjects[sid]["title"],
                    sid, .8, "Retained with cited source", "extraction", identifier, "active", now))
        for sid, subject in subjects.items():
            cids = sorted({mapped[m["id"]] for m in result["memories"] if sid in m["subject_ids"]})
            cited = sorted({s for c in claims if c.claim_id in cids for p in c.provenance for s in p.segment_ids})
            if not cids:
                continue
            self.artifacts.save_entity_resolution_decision(EntityResolutionDecision(
                stable_id("identity", identifier, sid), "entity_creation", sid, subject["entity_type"],
                subject["title"], sorted({p.source_id for c in claims if c.claim_id in cids for p in c.provenance}),
                cids, cited, .8, "Subject selected from source and prior memory",
                "review_required" if subject["review_required"] else "accepted", identifier, now))
        if replacement is None:
            for change in result["changes"]:
                later, earlier = mapped[change["later_id"]], change["earlier_id"]
                self.artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
                    stable_id("proposal", later, earlier), [later], [earlier], change["relation"], change["reason"],
                    .8, identifier, now, affected_entity_ids=sorted(subjects)))
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
        by_id = {s.segment_id: s for s in source.segments}
        context_ids, errors = set(), []
        for index in range(len(episode.extraction_batches)):
            batch = episode.extraction_batches[index]
            if batch.status == "complete":
                continue
            batch.attempt_count += 1
            try:
                segments = [by_id[sid] for sid in batch.segment_ids]
                payload = await self.input(source, segments, batch.batch_id,
                                           prior_ids=None if self.segments(source, segments) else [])
                result = (await contract.retain(self.llm, payload) if payload["segments"]
                          else {"subjects": [], "memories": [], "changes": []})
                trial = deepcopy(episode)
                with self.artifacts.db.transaction():
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
