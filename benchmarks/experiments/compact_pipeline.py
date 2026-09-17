"""Opt-in native storage experiment. Not an application mode or alternate backend.

Uses canonical records and transactions on disposable stores. Existing public
retrieval operates on these records unchanged. Adoption still needs lifecycle
validation; free sections are local here until the comparison justifies them.
"""

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, replace
from datetime import datetime, timezone

from benchmarks.experiments import compact_contract as contract
from mycelium.artifacts import (
    ArtifactStore, ClaimEntityReference, ClaimPlacement, ClaimProvenance,
    ConsolidatedFact, EntityRecord, EntityResolutionDecision,
    ExtractionSegmentDisposition, MemoryClaim, ReconsolidationProposal,
)
from mycelium.batching import split_text_by_tokens
from mycelium.budget import count_tokens
from mycelium.consolidation_models import ClaimEvidence
from mycelium.materialization import PageMaterializer
from mycelium.models import DreamReport
from mycelium.operations import ConsolidationResult
from mycelium.page_reviews import reviewed_page_exclusions
from mycelium.pipeline import MemoryPipeline
from mycelium.ontology import section_pairs


def stable_id(kind, *parts):
    return kind + "-" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:20]


class OpenSectionStore(ArtifactStore):
    """Same exact record references; headings are chosen by the model."""

    def save_consolidated_fact(self, fact):
        if not fact.section_key.strip():
            raise ValueError("View items need a heading")
        for eid in {fact.owner_entity_id, *fact.linked_entity_ids}:
            if self.get_entity(eid).status != "active":
                raise ValueError("Fact endpoints must be active identities")
        for cid in fact.member_claim_ids:
            self.get_claim(cid)
        self.db.put("consolidated-facts", fact.fact_id, asdict(fact))


class OpenSectionMaterializer(PageMaterializer):
    """Render each cited item's own destinations, independent of claim placement.

    Temporary placements below adapt the existing renderer's metadata contract;
    they are never persisted as an exclusive ownership decision for evidence.
    """

    def regenerate(self, entity_ids):
        self._identity_reviews = defaultdict(list)
        for decision in self.artifacts.list_entity_resolution_decisions(review_state="review_required"):
            for cid in decision.supporting_claim_ids:
                self._identity_reviews[cid].append(decision.decision_id)
        # A link becoming available/unavailable affects every referencing item.
        by_claim = defaultdict(set)
        for fact in self.artifacts.list_consolidated_facts():
            for cid in fact.member_claim_ids:
                by_claim[cid].update({fact.owner_entity_id, *fact.linked_entity_ids})
        endpoints = list(by_claim.values())
        affected = set(entity_ids)
        while True:
            expanded = affected | {eid for group in endpoints if group & affected for eid in group}
            if expanded == affected:
                return super().regenerate(affected)
            affected = expanded

    @classmethod
    def _page_facts(cls, entity_id, fact, claims, placements, entities):
        endpoints = {fact.owner_entity_id, *fact.linked_entity_ids}
        if entity_id not in endpoints or not all(cid in claims for cid in fact.member_claim_ids):
            return []
        return [replace(fact, owner_entity_id=entity_id,
                        linked_entity_ids=sorted(endpoints - {entity_id}))]

    def _item_placements(self, fact):
        return {cid: ClaimPlacement(cid, fact.owner_entity_id, fact.section_key,
                    fact.linked_entity_ids, "placed", "View item metadata", fact.created_at, fact.updated_at,
                    identity_blocker_ids=self._identity_reviews.get(cid, []))
                for cid in fact.member_claim_ids}

    def _fact_items(self, values, entities, claims_by_id, **kwargs):
        items = []
        for fact in values:
            canonical = self.artifacts.get_consolidated_fact(fact.fact_id)
            items.extend(super()._fact_items([fact], entities, claims_by_id,
                **{**kwargs, "canonical_placements": self._item_placements(canonical)}))
        return items

    def _build_page(self, entity, owned, entities, placements, pending_proposals_by_claim,
                    encounters, facts, claims_by_id, existing, projected_entity_ids):
        owned = [(claims_by_id[cid], placement) for fact in facts
                 for cid, placement in self._item_placements(fact).items()]
        return super()._build_page(entity, owned, entities, placements, pending_proposals_by_claim,
                                  encounters, facts, claims_by_id, existing, projected_entity_ids)

    def _sections(self, entity, owned, entities, placements, pending_proposals_by_claim,
                  encounters, facts, claims_by_id, projected_entity_ids):
        sections = super()._sections(entity, owned, entities, placements, pending_proposals_by_claim,
                                     encounters, facts, claims_by_id, projected_entity_ids)
        declared = {key for key, _ in section_pairs(entity.entity_type)}
        groups = defaultdict(list)
        for fact in facts:
            if fact.section_key not in declared:
                groups[fact.section_key].append(fact)
        for heading, group in groups.items():
            items = self._fact_items(group, entities, claims_by_id, pending=False,
                page_entity_id=entity.entity_id, canonical_placements=placements,
                chronological=False, projected_entity_ids=projected_entity_ids,
                pending_proposals_by_claim=pending_proposals_by_claim)
            if items:
                sections.append({"key": heading, "title": heading, "items": items})
        return sections


class CompactPipeline(MemoryPipeline):
    def __init__(self, memory):
        super().__init__(memory.encoder, memory.retriever, memory.consolidator)
        self.memory = memory
        self.artifacts = OpenSectionStore(memory.artifacts.root)
        self.materializer = OpenSectionMaterializer(memory.wiki, self.artifacts, memory.config)

    def _memory_record(self, claim):
        refs = self.artifacts.list_entity_references(claim_id=claim.claim_id, status="active")
        return {"id": claim.claim_id, "text": claim.text,
                "subject_ids": sorted({r.entity_id for r in refs if r.entity_id}),
                "source_time": [self.artifacts.get_source(p.source_id).occurred_at for p in claim.provenance],
                "segment_ids": [sid for p in claim.provenance for sid in p.segment_ids]}

    async def _retention_input(self, source, batch, identifier):
        query = "\n".join(s.content for s in batch)
        prior_ids = []
        # EmbeddingGemma has its own input limit. Combine learned rankings;
        # this is candidate retrieval, never a semantic identity decision.
        for chunk in split_text_by_tokens(query, 1200):
            hits = await self.retriever.claim_index.search(chunk, limit=24)
            prior_ids.extend(h.claim_id for h in hits)
        prior_ids = list(dict.fromkeys(prior_ids))[:48]
        prior = [self.artifacts.get_claim(cid) for cid in prior_ids]
        entity_ids = {r.entity_id for c in prior for r in self.artifacts.list_entity_references(
            claim_id=c.claim_id, status="active") if r.entity_id}
        entity_ids.update(p.owner_entity_id for cid in prior_ids
                          for p in [self.artifacts.placement_for_claim(cid)] if p and p.owner_entity_id)
        if any(e.entity_id == "you" for e in self.artifacts.list_entities()):
            entity_ids.add("you")
        subjects = [self.artifacts.get_entity(eid) for eid in sorted(entity_ids)]
        context = []
        for sid in source.metadata.get("context_source_ids", []):
            old = self.artifacts.get_source(sid)
            if old.status == "active":
                context.extend(self._segments(old, old.segments))
        # Context is bounded without dropping portions of a cited segment.
        selected, used = [], 0
        for row in reversed(context):
            size = count_tokens(json.dumps(row))
            if used + size > 6000:
                break
            selected.insert(0, row)
            used += size
        return {"source_type": source.source_type, "occurred_at": source.occurred_at,
                "participants": source.participants, "segments": self._segments(source, batch),
                "context_segments": selected, "prior_memories": [self._memory_record(c) for c in prior],
                "existing_subjects": [{"id": e.entity_id, "title": e.title, "entity_type": e.entity_type} for e in subjects],
                "new_subject_ids": [stable_id("subject", identifier, i) for i in range(32)]}

    @staticmethod
    def _segments(source, segments):
        return [{"id": s.segment_id, "text": s.content, "speaker": s.speaker, "role": s.role,
                 "source_id": source.source_id, "source_time": s.timestamp or source.occurred_at,
                 "metadata": s.metadata} for s in segments]

    def _save_retention(self, source, episode, identifier, payload, result):
        now = datetime.now(timezone.utc).isoformat()
        subjects = {s["id"]: s for s in result["subjects"]}
        claims = []
        evidence = {s["id"]: s for s in [*payload["segments"], *payload["context_segments"]]}
        for row in result["memories"]:
            by_source = defaultdict(list)
            for sid in row["segment_ids"]:
                by_source[evidence[sid]["source_id"]].append(sid)
            claims.append(MemoryClaim(stable_id("claim", identifier, row["id"]), row["text"], [],
                [ClaimProvenance(sid, sorted(set(ids))) for sid, ids in by_source.items()], now))
        mapped = {row["id"]: c.claim_id for row, c in zip(result["memories"], claims)}
        decisions = {}
        with self.artifacts.db.transaction():
            for s in result["subjects"]:
                try:
                    entity = self.artifacts.get_entity(s["id"])
                except FileNotFoundError:
                    # Exact allocated IDs define identity; names are display text only.
                    entity = EntityRecord(s["id"], s["entity_type"], s["title"], s["id"], [], "active", now, now,
                                          materialization_state="provisional")
                self.artifacts.save_entity(entity)
            for row, claim in zip(result["memories"], claims):
                self.artifacts.save_claim(claim)
                for sid in row["subject_ids"]:
                    ref = ClaimEntityReference(stable_id("ref", claim.claim_id, sid), claim.claim_id, "subject",
                        subjects[sid]["title"], sid, .8, "Retained with cited source", "extraction", identifier, "active", now)
                    self.artifacts.save_entity_reference(ref)
            for sid, subject in subjects.items():
                cids = [mapped[m["id"]] for m in result["memories"] if sid in m["subject_ids"]]
                cited = sorted({p.segment_ids[i] for c in claims if c.claim_id in cids for p in c.provenance for i in range(len(p.segment_ids))})
                decision = EntityResolutionDecision(stable_id("identity", identifier, sid), "entity_creation", sid,
                    subject["entity_type"], subject["title"], [source.source_id], cids, cited, .8,
                    "Subject selected from source and prior memory", "review_required" if subject["review_required"] else "accepted",
                    identifier, now)
                self.artifacts.save_entity_resolution_decision(decision)
                if subject["review_required"]:
                    decisions[sid] = decision.decision_id
            for change in result["changes"]:
                later, earlier = mapped[change["later_id"]], change["earlier_id"]
                self.artifacts.save_reconsolidation_proposal(ReconsolidationProposal(
                    stable_id("proposal", later, earlier), [later], [earlier], change["relation"], change["reason"],
                    .8, identifier, now, affected_entity_ids=sorted(subjects)))
            state = {"status": "retained", "claim_ids": [c.claim_id for c in claims],
                     "subject_ids": sorted(subjects), "identity_reviews": decisions, "episode_id": episode.episode_id}
            self.artifacts.db.put("compact-builds", identifier, state)
            episode.claim_ids = list(dict.fromkeys([*episode.claim_ids, *state["claim_ids"]]))
            self.artifacts.save_episode(episode)
        return state

    def _view_input(self, state):
        affected = set(state["subject_ids"])
        claims = {c.claim_id: c for c in self.artifacts.list_claims() if c.status == "active"}
        facts = [f for f in self.artifacts.list_consolidated_facts() if f.owner_entity_id in affected]
        mids = set(state["claim_ids"]) | {cid for f in facts for cid in f.member_claim_ids}
        mids &= claims.keys()
        # A failed oversized request is visible; no silent truncation or semantic fallback.
        entities = {e.entity_id: e for e in self.artifacts.list_entities(status="active")}
        related = affected | {eid for f in facts for eid in f.linked_entity_ids}
        proposals = self.artifacts.list_reconsolidation_proposals(status="pending")
        pending = {cid for p in proposals for cid in [*p.incoming_claim_ids, *p.target_claim_ids]}
        # Already published pending/manual facts are immutable; new pending claims
        # can be presented with the existing materializer's review qualification.
        protected = {cid for f in facts if f.manual_text or set(f.member_claim_ids) & pending for cid in f.member_claim_ids}
        exclusions, _ = reviewed_page_exclusions(self.artifacts, {
            cid: ClaimEvidence(claims[cid], self.artifacts.get_source(claims[cid].provenance[0].source_id)) for cid in mids})
        return {"subjects": [{"id": eid, "title": entities[eid].title} for eid in sorted(related)],
                "affected_subject_ids": sorted(affected), "memories": [self._memory_record(claims[cid]) for cid in sorted(mids)],
                "existing_items": [{"id": f.fact_id, "text": f.text, "owner_id": f.owner_entity_id,
                                    "heading": f.section_key, "memory_ids": f.member_claim_ids} for f in facts],
                "pending_changes": [asdict(p) for p in proposals if set(p.incoming_claim_ids + p.target_claim_ids) & mids],
                "protected_memory_ids": sorted(protected),
                "page_exclusions": [{"memory_id": cid, "subject_id": eid} for cid, eids in exclusions.items() for eid in eids]}

    def _save_view(self, identifier, state, view, source, episode):
        now = datetime.now(timezone.utc).isoformat()
        used = {cid for item in view["items"] for cid in item["memory_ids"]}
        prior = self.artifacts.list_consolidated_facts()
        pending = {cid for p in self.artifacts.list_reconsolidation_proposals(status="pending")
                   for cid in [*p.incoming_claim_ids, *p.target_claim_ids]}
        # The refresh owns only these generated items. Shared evidence neither
        # transfers ownership nor authorizes editing another subject's items.
        replaced = [f for f in prior if f.owner_entity_id in state["subject_ids"]
                    and not f.manual_text and not set(f.member_claim_ids) & pending]
        affected = set(state["subject_ids"]) | {eid for f in replaced
                                               for eid in [f.owner_entity_id, *f.linked_entity_ids]}
        with self.artifacts.db.transaction():
            for f in replaced:
                self.artifacts.delete_consolidated_fact(f.fact_id)
            for index, item in enumerate(view["items"]):
                endpoints = {item["owner_id"], *item["linked_subject_ids"]}
                affected.update(endpoints)
                self.artifacts.save_consolidated_fact(ConsolidatedFact(
                    stable_id("fact", identifier, index), item["text"], item["memory_ids"], item["owner_id"],
                    item["heading"], item["state"], item["linked_subject_ids"], "model", .8,
                    "Source-led view refresh", now, now))
                for cid in item["memory_ids"]:
                    claim = self.artifacts.get_claim(cid)
                    claim.dream_disposition = "routed"
                    self.artifacts.save_claim(claim)
            for cid in set(state["claim_ids"]) - used:
                claim = self.artifacts.get_claim(cid)
                claim.dream_disposition = "deferred"
                claim.dream_disposition_reason = "Retained without a new view item"
                self.artifacts.save_claim(claim)
            pages = self.materializer.regenerate(affected)
            state["status"] = "complete"
            self.artifacts.db.put("compact-builds", identifier, state)
            episode.extraction_status = "complete"
            episode.extraction_error = None
            cited = defaultdict(list)
            for cid in episode.claim_ids:
                for provenance in self.artifacts.get_claim(cid).provenance:
                    if provenance.source_id == source.source_id:
                        for sid in provenance.segment_ids:
                            cited[sid].append(cid)
            episode.segment_dispositions = [ExtractionSegmentDisposition(s.segment_id,
                "claimed" if cited[s.segment_id] else "source_only", cited[s.segment_id],
                "Cited by retained memory" if cited[s.segment_id] else "Not selected in this build; source retained")
                for s in source.segments]
            self.artifacts.save_episode(episode)
            self.encoder._sync_ingestion_operation(episode)
            if source.raw_log_entry_id:
                self.memory.log_store.mark_consolidated([source.raw_log_entry_id])
        self.artifacts.db.publish()
        return pages

    async def consolidate(self, request=None):
        failures, completed, created, updated = [], [], 0, 0
        if request and request.dry_run:
            return ConsolidationResult(DreamReport(0, 0, 0))
        async with self._build_lock:
            self.artifacts.db.publish()
            for episode in self.artifacts.list_episodes():
                source = self.artifacts.get_source(episode.source_id)
                if source.status != "active":
                    continue
                identifier = stable_id("build", episode.episode_id)
                try:
                    state = self.artifacts.db.get("compact-builds", identifier)
                except FileNotFoundError:
                    if episode.extraction_status == "complete":
                        continue
                    state = None
                if state and state["status"] == "complete":
                    continue
                try:
                    if state is None:
                        payload = await self._retention_input(source, source.segments, identifier)
                        result = await contract.retain(self.memory.llm, payload)
                        state = self._save_retention(source, episode, identifier, payload, result)
                    view_input = self._view_input(state)
                    view = await contract.present(self.memory.llm, view_input)
                    pages = self._save_view(identifier, state, view, source, episode)
                    created += len(pages.created_slugs)
                    updated += len(pages.updated_slugs)
                    completed.append(source.source_id)
                except Exception as exc:
                    failures.append({"stage": "compact_build", "source_id": source.source_id,
                                     "reason": f"{type(exc).__name__}: {exc}"})
                    episode.extraction_status = "partial" if state else "failed"
                    episode.extraction_error = str(exc)
                    self.artifacts.save_episode(episode)
            return ConsolidationResult(DreamReport(updated, created, len(completed), completed,
                [f["source_id"] for f in failures], failures))
