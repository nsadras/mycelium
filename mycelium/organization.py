"""Transparent entity curation and review for the generated wiki."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    EntityRecord,
    OrganizationProposal,
)
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.models import PAGE_SECTION_KEYS, PAGE_TYPES, PageType
from mycelium.store import WikiStore
from mycelium.wiki_schema import default_section


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass
class CurationResult:
    entity: EntityRecord
    pages_updated: list[str]
    pages_deleted: list[str]


class EntityCurationService:
    def __init__(
        self, artifacts: ArtifactStore, wiki: WikiStore, materializer: PageMaterializer
    ) -> None:
        self.artifacts = artifacts
        self.wiki = wiki
        self.materializer = materializer

    def update_entity(
        self,
        entity_id: str,
        *,
        title: str | None = None,
        slug: str | None = None,
        aliases: list[str] | None = None,
        entity_type: str | None = None,
    ) -> CurationResult:
        entity = self.artifacts.get_entity(entity_id)
        if entity.status == "merged":
            raise ValueError("Merged identities cannot be edited")
        if entity.entity_id == "you" and entity_type not in {None, "you"}:
            raise ValueError("The You entity type cannot change")
        if entity_type is not None and entity_type not in PAGE_TYPES:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        old_slug = entity.slug
        old_title = entity.title
        entity.title = " ".join((title or entity.title).split()).strip()
        entity.slug = slug or entity.slug
        entity.aliases = list(aliases if aliases is not None else entity.aliases)
        if title and _normalized(title) != _normalized(old_title):
            entity.aliases.append(old_title)
        type_changed = bool(entity_type and entity_type != entity.entity_type)
        if entity_type:
            entity.entity_type = entity_type
        entity.updated_at = _now()
        entity.__post_init__()
        self.artifacts.save_entity(entity)
        if type_changed:
            for placement in self.artifacts.placements_for_entity(entity_id):
                claim = self.artifacts.get_claim(placement.claim_id)
                placement.section_key = default_section(entity.entity_type, claim)
                placement.reason = "Section remapped after a manual entity type correction."
                placement.updated_at = _now()
                self.artifacts.save_placement(placement)
        if old_slug != entity.slug:
            self.wiki.delete(old_slug)
        pages = self.materializer.regenerate({entity_id, "you"})
        return self._result(entity, pages, [old_slug] if old_slug != entity.slug else [])

    def set_status(self, entity_id: str, status: str) -> CurationResult:
        if status not in {"active", "archived"}:
            raise ValueError("Entity status must be active or archived")
        entity = self.artifacts.get_entity(entity_id)
        if entity.entity_id == "you" and status == "archived":
            raise ValueError("The You entity cannot be archived")
        if entity.status == "merged":
            raise ValueError("Merged identities cannot change lifecycle state")
        entity.status = status
        entity.updated_at = _now()
        self.artifacts.save_entity(entity)
        if status == "archived":
            self.wiki.archive(entity.slug)
            pages = self.materializer.regenerate({"you"})
            self.materializer.rebuild_index(pages.changed_pages, {entity.slug})
            return CurationResult(entity, sorted(pages.changed_pages), [entity.slug])
        pages = self.materializer.regenerate({entity_id, "you"})
        return self._result(entity, pages, [])

    def move_claim(
        self,
        claim_id: str,
        owner_entity_id: str | None,
        section_key: str | None,
        *,
        linked_entity_ids: list[str] | None = None,
        reason: str = "Manual wiki organization",
    ) -> CurationResult | None:
        old = self.artifacts.placement_for_claim(claim_id)
        affected = {old.owner_entity_id} if old and old.owner_entity_id else set()
        now = _now()
        if owner_entity_id is None:
            placement = ClaimPlacement(
                claim_id, None, None, [], "deferred", reason,
                old.created_at if old else now, now,
            )
        else:
            placement = ClaimPlacement(
                claim_id, owner_entity_id, section_key,
                list(linked_entity_ids if linked_entity_ids is not None else (old.linked_entity_ids if old else [])),
                "placed", reason, old.created_at if old else now, now,
            )
            affected.add(owner_entity_id)
        self.artifacts.save_placement(placement)
        claim = self.artifacts.get_claim(claim_id)
        claim.dream_disposition = "routed" if owner_entity_id else "deferred"
        claim.dream_disposition_reason = reason
        claim.dream_run_id = None
        claim.dream_disposition_at = now
        self.artifacts.save_claim(claim)
        pages = self.materializer.regenerate({value for value in affected if value})
        if owner_entity_id is None:
            return None
        return self._result(self.artifacts.get_entity(owner_entity_id), pages, [])

    def merge(self, source_entity_id: str, target_entity_id: str) -> CurationResult:
        source = self.artifacts.get_entity(source_entity_id)
        target = self.artifacts.get_entity(target_entity_id)
        if source.entity_id == "you" or target.status != "active" or source.status != "active":
            raise ValueError("Merge requires an active non-You source and active target")
        if source.entity_type != target.entity_type:
            raise ValueError("Entities must have the same type to merge")
        for placement in self.artifacts.list_placements():
            changed = False
            if placement.owner_entity_id == source_entity_id:
                placement.owner_entity_id = target_entity_id
                claim = self.artifacts.get_claim(placement.claim_id)
                allowed = {
                    key
                    for key, _ in PAGE_SECTION_KEYS[
                        cast(PageType, target.entity_type)
                    ]
                }
                if placement.section_key not in allowed:
                    placement.section_key = default_section(target.entity_type, claim)
                changed = True
            if source_entity_id in placement.linked_entity_ids:
                placement.linked_entity_ids = [
                    target_entity_id if value == source_entity_id else value
                    for value in placement.linked_entity_ids
                ]
                changed = True
            if changed:
                placement.updated_at = _now()
                placement.__post_init__()
                self.artifacts.save_placement(placement)
        target.aliases = sorted(set([
            *target.aliases, source.title, source.slug, *source.aliases
        ]))
        target.updated_at = _now()
        self.artifacts.save_entity(target)
        source.status = "merged"
        source.merged_into_entity_id = target.entity_id
        source.updated_at = _now()
        self.artifacts.save_entity(source)
        self.wiki.archive(source.slug)
        pages = self.materializer.regenerate({target_entity_id, "you"})
        return self._result(target, pages, [source.slug])

    def split(
        self,
        source_entity_id: str,
        claim_ids: list[str],
        *,
        title: str,
        entity_type: str,
        aliases: list[str] | None = None,
    ) -> CurationResult:
        source = self.artifacts.get_entity(source_entity_id)
        selected = set(claim_ids)
        owned = {
            placement.claim_id for placement in self.artifacts.placements_for_entity(source_entity_id)
        }
        if not selected or not selected <= owned:
            raise ValueError("Split claims must be a nonempty subset owned by the source entity")
        entity = self.artifacts.create_entity(entity_type, title, aliases=aliases)
        for claim_id in selected:
            placement = self.artifacts.get_placement(claim_id)
            placement.owner_entity_id = entity.entity_id
            placement.section_key = default_section(entity.entity_type, self.artifacts.get_claim(claim_id))
            placement.updated_at = _now()
            self.artifacts.save_placement(placement)
        pages = self.materializer.regenerate({source.entity_id, entity.entity_id, "you"})
        return self._result(entity, pages, [])

    @staticmethod
    def _result(
        entity: EntityRecord, pages: MaterializationResult, deleted: list[str]
    ) -> CurationResult:
        return CurationResult(
            entity,
            sorted(pages.changed_pages),
            sorted(set([*deleted, *pages.deleted_slugs])),
        )


class OrganizationAuditor:
    """Conservatively surface duplicate identities and clear homes for deferred claims."""

    def __init__(self, artifacts: ArtifactStore):
        self.artifacts = artifacts

    def audit(self) -> list[OrganizationProposal]:
        existing_pending = self.artifacts.list_organization_proposals(status="pending")
        signatures: set[tuple[str, str | None, str | None, str | None]] = {
            (proposal.proposal_type, proposal.claim_id, proposal.source_entity_id, proposal.target_entity_id)
            for proposal in existing_pending
        }
        entities = self.artifacts.list_entities(status="active")
        proposals: list[OrganizationProposal] = []
        for index, left in enumerate(entities):
            left_names = {_normalized(left.title), *(_normalized(value) for value in left.aliases)}
            for right in entities[index + 1:]:
                if left.entity_type != right.entity_type:
                    continue
                right_names = {_normalized(right.title), *(_normalized(value) for value in right.aliases)}
                if not (left_names & right_names):
                    continue
                merge_signature = ("merge_entities", None, right.entity_id, left.entity_id)
                if merge_signature in signatures:
                    continue
                proposals.append(OrganizationProposal(
                    proposal_id=f"org-{uuid.uuid4().hex[:12]}",
                    proposal_type="merge_entities",
                    source_entity_id=right.entity_id,
                    target_entity_id=left.entity_id,
                    explanation="The entities share an exact normalized title or alias.",
                    confidence=0.85,
                    created_at=_now(),
                ))
        names: dict[str, list[EntityRecord]] = {}
        for entity in entities:
            for name in {entity.title, *entity.aliases}:
                names.setdefault(_normalized(name), []).append(entity)
        for placement in self.artifacts.list_placements(status="deferred"):
            claim = self.artifacts.get_claim(placement.claim_id)
            candidates = {
                entity.entity_id: entity
                for subject in claim.about
                for entity in names.get(_normalized(str(subject.get("entity") or "")), [])
            }
            if len(candidates) != 1:
                continue
            entity = next(iter(candidates.values()))
            assign_signature = ("assign_claim", claim.claim_id, None, None)
            if assign_signature in signatures:
                continue
            proposals.append(OrganizationProposal(
                proposal_id=f"org-{uuid.uuid4().hex[:12]}",
                proposal_type="assign_claim",
                claim_id=claim.claim_id,
                proposed_owner_entity_id=entity.entity_id,
                proposed_section_key=default_section(entity.entity_type, claim),
                explanation="The claim names exactly one existing entity by title or alias.",
                confidence=0.8,
                created_at=_now(),
            ))
        for proposal in proposals:
            self.artifacts.save_organization_proposal(proposal)
        return proposals


class OrganizationReviewService:
    def __init__(self, artifacts: ArtifactStore, curation: EntityCurationService):
        self.artifacts = artifacts
        self.curation = curation

    def review(
        self, proposal_id: str, decision: str, *, reviewer_note: str | None = None
    ) -> OrganizationProposal:
        proposal = self.artifacts.get_organization_proposal(proposal_id)
        if proposal.status != "pending":
            raise ValueError("Only pending organization proposals may be reviewed")
        proposal.reviewer_note = reviewer_note
        proposal.reviewed_at = _now()
        if decision == "reject":
            proposal.status = "rejected"
        elif decision == "approve":
            if proposal.proposal_type == "assign_claim":
                if proposal.claim_id is None or proposal.proposed_section_key is None:
                    raise ValueError("Claim assignment proposal is incomplete")
                owner_entity_id = proposal.proposed_owner_entity_id
                if owner_entity_id is None:
                    if (
                        proposal.proposed_new_entity_type is None
                        or proposal.proposed_new_entity_title is None
                    ):
                        raise ValueError("New entity proposal is incomplete")
                    owner_entity_id = self.artifacts.create_entity(
                        proposal.proposed_new_entity_type,
                        proposal.proposed_new_entity_title,
                    ).entity_id
                self.curation.move_claim(
                    proposal.claim_id,
                    owner_entity_id,
                    proposal.proposed_section_key,
                    reason=f"Approved organization proposal {proposal.proposal_id}",
                )
            else:
                if proposal.source_entity_id is None or proposal.target_entity_id is None:
                    raise ValueError("Merge proposal is incomplete")
                self.curation.merge(proposal.source_entity_id, proposal.target_entity_id)
            proposal.status = "applied"
            proposal.applied_at = _now()
        else:
            raise ValueError("Decision must be approve or reject")
        self.artifacts.save_organization_proposal(proposal)
        return proposal
