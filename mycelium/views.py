"""Refresh a bounded set of cited view items without assigning ownership to claims."""

from dataclasses import asdict

from mycelium import memory_contract as contract
from mycelium.artifacts import ArtifactStore, ConsolidatedFact
from mycelium.database import UnitOfWork
from mycelium.page_reviews import reviewed_page_exclusions
from mycelium.retention import memory_record, now_iso, related_claim_ids, stable_id


class ViewOrganizer:
    def __init__(self, llm, artifacts, materializer, config, claim_index=None):
        self.llm, self.artifacts, self.materializer = llm, artifacts, materializer
        self.config, self.claim_index = config, claim_index

    def input(self, incoming_ids, context_ids, entity_ids):
        candidates = set(incoming_ids) | set(sorted(context_ids)[:48])
        # A replacement must refresh items citing its predecessor, including a
        # resumed Build after the first presentation failed. These are exact links.
        candidates.update(link["target"] for cid in incoming_ids
                          for link in self.artifacts.get_claim(cid).links
                          if link["relation"] == "supersedes")
        facts = {f.fact_id: f for cid in candidates for f in self.artifacts.facts_for_claim(cid)}
        facts = {fid: f for fid, f in facts.items() if self.artifacts.get_entity(f.owner_entity_id).status == "active"}
        mids = candidates | {cid for f in facts.values() for cid in f.member_claim_ids}
        claims = {cid: self.artifacts.get_claim(cid) for cid in mids}
        claims = {cid: c for cid, c in claims.items()
                  if c.status == "active" and c.dream_disposition != "excluded_source_policy"}
        affected = set(entity_ids) | self.artifacts.entities_for_claims(set(incoming_ids))
        affected.update(eid for f in facts.values() for eid in [f.owner_entity_id, *f.linked_entity_ids])
        entities = {e.entity_id: e for e in self.artifacts.list_entities(status="active")}
        affected &= entities.keys()
        proposals = self.artifacts.list_reconsolidation_proposals(status="pending")
        pending = {cid for p in proposals for cid in [*p.incoming_claim_ids, *p.target_claim_ids]}
        exclusions, _ = reviewed_page_exclusions(self.artifacts, claims)
        return {"subjects": [{"id": eid, "title": entities[eid].title,
                              "entity_type": entities[eid].entity_type, "aliases": entities[eid].aliases}
                             for eid in sorted(affected)],
                "affected_subject_ids": sorted(affected),
                "memories": [memory_record(self.artifacts, claims[cid]) for cid in sorted(claims)],
                "existing_items": [{"id": f.fact_id, "text": f.text, "owner_id": f.owner_entity_id,
                    "heading": f.section_key, "memory_ids": f.member_claim_ids,
                    "linked_subject_ids": f.linked_entity_ids,
                    "protected": f.manual_text or bool(set(f.member_claim_ids) & pending)} for f in facts.values()],
                "pending_changes": [asdict(p) for p in proposals if set(p.incoming_claim_ids + p.target_claim_ids) & claims.keys()],
                "page_exclusions": [{"memory_id": cid, "subject_id": eid} for cid, eids in exclusions.items() for eid in eids]}

    async def related(self, incoming_ids):
        if self.claim_index is None or not incoming_ids:
            return []
        text = "\n".join(self.artifacts.get_claim(cid).text for cid in sorted(incoming_ids))
        return await related_claim_ids(self.claim_index, text)

    async def refresh(self, incoming_ids, *, entity_ids=(), context_ids=None, run_id):
        incoming_ids = set(incoming_ids)
        if context_ids is None:
            context_ids = await self.related(incoming_ids)
        # Validate the exact model input again at commit, so an intervening user
        # edit cannot be overwritten. Lifecycle services already own a snapshot.
        unit = None if isinstance(self.artifacts.db, UnitOfWork) else UnitOfWork(self.artifacts.db)
        reader = self if unit is None else ViewOrganizer(self.llm,
            ArtifactStore(self.artifacts.root, db=unit), self.materializer, self.config)
        try:
            payload = reader.input(incoming_ids, context_ids, entity_ids)
            view = (await contract.present(self.llm, payload) if payload["memories"] and payload["affected_subject_ids"]
                    else {"items": []})
            with self.artifacts.db.transaction():
                if unit is not None:
                    unit.validate_reads()
                return self.persist(payload, view, incoming_ids, run_id)
        finally:
            if unit is not None:
                unit.close()

    def persist(self, payload, view, incoming_ids, run_id):
        # Revalidate at the mutation boundary, including responses used by tests/tools.
        contract.presentation_model(payload).model_validate(view)
        now = now_iso()
        affected = set(payload["affected_subject_ids"])
        with self.artifacts.db.transaction():
            for item in payload["existing_items"]:
                if not item["protected"]:
                    fact = self.artifacts.get_consolidated_fact(item["id"])
                    affected.update([fact.owner_entity_id, *fact.linked_entity_ids])
                    self.artifacts.delete_consolidated_fact(item["id"])
            for index, item in enumerate(view["items"]):
                self.artifacts.save_consolidated_fact(ConsolidatedFact(
                    f"{stable_id('view', run_id)}-{index:04d}", item["text"], item["memory_ids"], item["owner_id"],
                    item["heading"], item["state"], item["linked_subject_ids"], "model", .8,
                    "Source-backed view refresh", now, now))
                affected.update([item["owner_id"], *item["linked_subject_ids"]])
            for cid in {m["id"] for m in payload["memories"]} | set(incoming_ids):
                claim = self.artifacts.get_claim(cid)
                if claim.status != "active" or claim.dream_disposition == "excluded_source_policy":
                    continue
                claim.dream_disposition = "routed" if self.artifacts.facts_for_claim(cid) else "deferred"
                claim.dream_disposition_reason = "View refreshed" if claim.dream_disposition == "routed" else "Retained without a view item"
                claim.dream_disposition_at, claim.dream_run_id = now, run_id
                self.artifacts.save_claim(claim)
            return self.materializer.regenerate(affected)
