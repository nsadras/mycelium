"""Refresh cited view items while preserving user edits and claim ownership."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from mycelium import memory_contract as contract
from mycelium.artifacts import ArtifactStore, ConsolidatedFact
from mycelium.claim_index import LanceClaimIndex
from mycelium.config import Config
from mycelium.database import UnitOfWork
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.memory_inputs import (
    PresentationInput,
    PresentationResult,
    serialize_claim_context,
)
from mycelium.ollama import OllamaClient
from mycelium.page_reviews import reviewed_page_exclusions
from mycelium.retention import now_iso, related_claim_ids, stable_id


def _view_item_key(item: dict[str, Any]) -> tuple[frozenset[str], frozenset[str], str]:
    # Exact support and display location, not textual similarity. Sharing the
    # same evidence on another page or under another heading remains possible.
    return (
        frozenset(item["memory_ids"]),
        frozenset([item["owner_id"], *item["linked_subject_ids"]]),
        item["heading"],
    )


class ViewOrganizer:
    def __init__(
        self,
        llm: OllamaClient,
        artifacts: ArtifactStore,
        materializer: PageMaterializer,
        config: Config,
        claim_index: LanceClaimIndex | None = None,
    ) -> None:
        self.llm = llm
        self.artifacts = artifacts
        self.materializer = materializer
        self.config = config
        self.claim_index = claim_index

    def prepare_presentation_input(
        self,
        incoming_ids: Iterable[str],
        context_ids: Iterable[str],
        entity_ids: Iterable[str],
    ) -> PresentationInput:
        """Separate writable memories from context using exact support and page endpoints."""
        incoming_ids = set(incoming_ids)
        ordered_context = (
            sorted(context_ids) if isinstance(context_ids, set) else context_ids
        )
        context_ids = set(list(dict.fromkeys(ordered_context))[:48])
        touched_claim_ids = set(incoming_ids)
        # A replacement must refresh items citing its predecessor, including a
        # resumed Build after the first presentation failed. These are exact links.
        touched_claim_ids.update(
            link["target"]
            for claim_id in incoming_ids
            for link in self.artifacts.get_claim(claim_id).links
            if link["relation"] == "supersedes"
        )
        affected_subject_ids = set(entity_ids) | self.artifacts.entities_for_claims(
            incoming_ids
        )
        proposals = self.artifacts.list_reconsolidation_proposals(status="pending")
        touched_claim_ids.update(
            claim_id
            for proposal in proposals
            if incoming_ids.intersection(proposal.incoming_claim_ids)
            for claim_id in proposal.target_claim_ids
        )
        # Similarity supplies context, not permission to rewrite another page.
        # Only exact incoming subject/view endpoints or changed support authorize it.
        facts = {
            fact.fact_id: fact
            for claim_id in touched_claim_ids | context_ids
            for fact in self.artifacts.facts_for_claim(claim_id)
            if claim_id in touched_claim_ids
            or affected_subject_ids.intersection(
                [fact.owner_entity_id, *fact.linked_entity_ids]
            )
        }
        facts = {
            fact_id: fact
            for fact_id, fact in facts.items()
            if self.artifacts.get_entity(fact.owner_entity_id).status == "active"
        }
        writable_claim_ids = touched_claim_ids | {
            claim_id for fact in facts.values() for claim_id in fact.member_claim_ids
        }
        writable_claim_ids.update(
            claim_id
            for claim_id in context_ids
            if affected_subject_ids & self.artifacts.entities_for_claims({claim_id})
        )
        claims = {
            claim_id: self.artifacts.get_claim(claim_id)
            for claim_id in writable_claim_ids | context_ids
        }
        claims = {
            claim_id: claim
            for claim_id, claim in claims.items()
            if claim.status == "active"
            and claim.dream_disposition != "excluded_source_policy"
        }
        memories = {
            claim_id: serialize_claim_context(self.artifacts, claim)
            for claim_id, claim in claims.items()
        }
        affected_subject_ids.update(
            entity_id
            for fact in facts.values()
            for entity_id in [fact.owner_entity_id, *fact.linked_entity_ids]
        )
        entities = {
            entity.entity_id: entity
            for entity in self.artifacts.list_entities(status="active")
        }
        # Speaker identity is optional presentation context, never a claim's
        # implicit subject. Declarations without a claim reference remain choices.
        affected_subject_ids.update(
            provenance["speaker_subject_id"]
            for claim_id in incoming_ids
            if claim_id in memories
            for provenance in memories[claim_id]["provenance"]
            if provenance.get("speaker_subject_id")
        )
        source_ids = {
            provenance.source_id
            for claim_id in incoming_ids
            if claim_id in claims
            for provenance in claims[claim_id].provenance
        }
        affected_subject_ids.update(
            decision.entity_id
            for decision in self.artifacts.list_entity_resolution_decisions()
            if decision.entity_id in entities
            and entities[decision.entity_id].entity_type in {"person", "you"}
            and decision.review_state != "rejected"
            and source_ids.intersection(decision.source_ids)
            and (
                not decision.supporting_claim_ids
                or incoming_ids.intersection(decision.supporting_claim_ids)
            )
        )
        affected_subject_ids &= entities.keys()
        subject_ids = affected_subject_ids | {
            subject_id
            for memory in memories.values()
            for subject_id in memory["subject_ids"]
        }
        subject_ids &= entities.keys()
        pending_claim_ids = {
            claim_id
            for proposal in proposals
            for claim_id in [*proposal.incoming_claim_ids, *proposal.target_claim_ids]
        }
        exclusions, _ = reviewed_page_exclusions(self.artifacts, claims)
        return {
            "subjects": [
                {
                    "id": entity_id,
                    "title": entities[entity_id].title,
                    "entity_type": entities[entity_id].entity_type,
                    "aliases": entities[entity_id].aliases,
                }
                for entity_id in sorted(subject_ids)
            ],
            "affected_subject_ids": sorted(affected_subject_ids),
            "memories": [
                memories[claim_id]
                for claim_id in sorted(claims.keys() & writable_claim_ids)
            ],
            "context_memories": [
                memories[claim_id]
                for claim_id in sorted(claims.keys() - writable_claim_ids)
            ],
            "existing_items": [
                {
                    "id": fact.fact_id,
                    "text": fact.text,
                    "owner_id": fact.owner_entity_id,
                    "heading": fact.section_key,
                    "memory_ids": fact.member_claim_ids,
                    "linked_subject_ids": fact.linked_entity_ids,
                    "protected": fact.manual_text
                    or bool(set(fact.member_claim_ids) & pending_claim_ids),
                }
                for fact in facts.values()
            ],
            "pending_changes": [
                asdict(proposal)
                for proposal in proposals
                if set(proposal.incoming_claim_ids + proposal.target_claim_ids)
                & claims.keys()
            ],
            "page_exclusions": [
                {"memory_id": claim_id, "subject_id": entity_id}
                for claim_id, entity_ids in exclusions.items()
                for entity_id in entity_ids
            ],
        }

    async def find_related_claim_ids(self, incoming_ids: Iterable[str]) -> list[str]:
        if self.claim_index is None or not incoming_ids:
            return []
        text = "\n".join(
            self.artifacts.get_claim(claim_id).text for claim_id in sorted(incoming_ids)
        )
        return await related_claim_ids(self.claim_index, text)

    async def refresh_views(
        self,
        incoming_ids: Iterable[str],
        *,
        entity_ids: Iterable[str] = (),
        context_ids: Iterable[str] | None = None,
        run_id: str,
    ) -> MaterializationResult:
        """Prepare a snapshot, request view items, then validate and save atomically."""
        incoming_ids = set(incoming_ids)
        if context_ids is None:
            context_ids = await self.find_related_claim_ids(incoming_ids)
        # Lifecycle services already own a snapshot. Otherwise own it here, and
        # validate again at commit so an intervening user edit cannot be overwritten.
        unit = (
            None
            if isinstance(self.artifacts.db, UnitOfWork)
            else UnitOfWork(self.artifacts.db)
        )
        reader = (
            self
            if unit is None
            else ViewOrganizer(
                self.llm,
                ArtifactStore(self.artifacts.root, db=unit),
                self.materializer,
                self.config,
            )
        )
        try:
            payload = reader.prepare_presentation_input(
                incoming_ids, context_ids, entity_ids
            )
            view: PresentationResult = (
                await contract.present(self.llm, payload)
                if payload["memories"] and payload["affected_subject_ids"]
                else {"items": []}
            )
            with self.artifacts.db.transaction():
                if unit is not None:
                    unit.validate_reads()
                return self.save_view_items(payload, view, incoming_ids, run_id)
        finally:
            if unit is not None:
                unit.close()

    def save_view_items(
        self,
        payload: PresentationInput,
        view: PresentationResult,
        incoming_ids: Iterable[str],
        run_id: str,
    ) -> MaterializationResult:
        """Replace unprotected items, update claim routing, and regenerate affected pages."""
        # Revalidate at the mutation boundary, including responses used by tests/tools.
        contract.presentation_model(payload).model_validate(view)
        now = now_iso()
        affected_subject_ids = set(payload["affected_subject_ids"])
        texts = {memory["id"]: memory["text"] for memory in payload["memories"]}
        with self.artifacts.db.transaction():
            seen = {
                _view_item_key(item)
                for item in payload["existing_items"]
                if item["protected"]
            }
            for item in payload["existing_items"]:
                if not item["protected"]:
                    fact = self.artifacts.get_consolidated_fact(item["id"])
                    affected_subject_ids.update(
                        [fact.owner_entity_id, *fact.linked_entity_ids]
                    )
                    self.artifacts.delete_consolidated_fact(item["id"])
            for index, item in enumerate(view["items"]):
                key = _view_item_key(item)
                if key in seen:
                    continue
                seen.add(key)
                self.artifacts.save_consolidated_fact(
                    ConsolidatedFact(
                        fact_id=f"{stable_id('view', run_id)}-{index:04d}",
                        text=" ".join(
                            texts[memory_id]
                            for memory_id in dict.fromkeys(item["memory_ids"])
                        ),
                        member_claim_ids=item["memory_ids"],
                        owner_entity_id=item["owner_id"],
                        section_key=item["heading"],
                        state=item["state"],
                        linked_entity_ids=item["linked_subject_ids"],
                        synthesis_origin="model",
                        confidence=0.8,
                        reason="Source-backed view refresh",
                        created_at=now,
                        updated_at=now,
                    )
                )
                affected_subject_ids.update(
                    [item["owner_id"], *item["linked_subject_ids"]]
                )
            for claim_id in {memory["id"] for memory in payload["memories"]} | set(
                incoming_ids
            ):
                claim = self.artifacts.get_claim(claim_id)
                if (
                    claim.status != "active"
                    or claim.dream_disposition == "excluded_source_policy"
                ):
                    continue
                claim.dream_disposition = (
                    "routed" if self.artifacts.facts_for_claim(claim_id) else "deferred"
                )
                claim.dream_disposition_reason = (
                    "View refreshed"
                    if claim.dream_disposition == "routed"
                    else "Retained without a view item"
                )
                claim.dream_disposition_at = now
                claim.dream_run_id = run_id
                self.artifacts.save_claim(claim)
            return self.materializer.regenerate(affected_subject_ids)
