"""Transparent entity curation and review for the generated wiki."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimPlacement,
    ClaimScopeDecision,
    ConsolidatedFact,
    EntityRecord,
    EntityResolutionDecision,
    OrganizationProposal,
)
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.ontology import ENTITY_TYPES, default_section, section_keys
from mycelium.store import WikiStore
from mycelium.projection import display_claim_text


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass
class CurationResult:
    entity: EntityRecord
    pages_updated: list[str]
    pages_deleted: list[str]


@dataclass
class FactCurationResult:
    facts: list[ConsolidatedFact]
    pages_updated: list[str]


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
        if entity_type is not None and entity_type not in ENTITY_TYPES:
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
                placement.section_key = default_section(
                    entity.entity_type, claim.claim_type, claim.predicate
                )
                placement.reason = "Section remapped after a manual entity type correction."
                placement.updated_at = _now()
                self.artifacts.save_placement(placement)
            for fact in self.artifacts.list_consolidated_facts(
                owner_entity_id=entity_id
            ):
                representative = self.artifacts.get_claim(fact.member_claim_ids[0])
                fact.section_key = default_section(
                    entity.entity_type,
                    representative.claim_type,
                    representative.predicate,
                )
                fact.reason = "Section remapped after a manual entity type correction."
                fact.updated_at = _now()
                self.artifacts.save_consolidated_fact(fact)
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
        origin: str = "manual",
    ) -> CurationResult | None:
        old = self.artifacts.placement_for_claim(claim_id)
        affected = (
            {old.owner_entity_id, *old.linked_entity_ids}
            if old and old.owner_entity_id
            else set()
        )
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
                old.relationship_kind if old else None,
            )
            affected.update({owner_entity_id, *placement.linked_entity_ids})
        self.artifacts.save_placement(placement)
        claim = self.artifacts.get_claim(claim_id)
        claim.dream_disposition = "routed" if owner_entity_id else "deferred"
        claim.dream_disposition_reason = reason
        claim.dream_run_id = None
        claim.dream_disposition_at = now
        self.artifacts.save_claim(claim)
        self.artifacts.save_scope_decision(ClaimScopeDecision(
            decision_id=f"scope-{uuid.uuid4().hex[:12]}",
            claim_id=claim_id,
            owner_entity_id=owner_entity_id,
            section_key=section_key,
            linked_entity_ids=list(placement.linked_entity_ids),
            supporting_claim_ids=[claim_id],
            confidence=1.0,
            reason=reason,
            origin=origin,
            dream_run_id=None,
            status="active",
            created_at=now,
        ))
        containing = self.artifacts.facts_for_claim(claim_id)
        if containing:
            for fact in containing:
                self.artifacts.delete_consolidated_fact(fact.fact_id)
                for remaining_id in (
                    value for value in fact.member_claim_ids if value != claim_id
                ):
                    remaining = self.artifacts.get_claim(remaining_id)
                    remaining_placement = self.artifacts.get_placement(remaining_id)
                    self.artifacts.save_consolidated_fact(ConsolidatedFact(
                        fact_id=f"fact-{uuid.uuid4().hex[:12]}",
                        text=display_claim_text(remaining),
                        member_claim_ids=[remaining_id],
                        owner_entity_id=cast(str, remaining_placement.owner_entity_id),
                        section_key=cast(str, remaining_placement.section_key),
                        state="current",
                        linked_entity_ids=list(remaining_placement.linked_entity_ids),
                        synthesis_origin="claim",
                        confidence=remaining.confidence,
                        reason="Separated after manual claim-level curation.",
                        created_at=now,
                        updated_at=now,
                    ))
        if owner_entity_id is not None:
            self.artifacts.save_consolidated_fact(ConsolidatedFact(
                fact_id=(
                    containing[0].fact_id
                    if len(containing) == 1 and len(containing[0].member_claim_ids) == 1
                    else f"fact-{uuid.uuid4().hex[:12]}"
                ),
                text=display_claim_text(claim),
                member_claim_ids=[claim_id],
                owner_entity_id=owner_entity_id,
                section_key=cast(str, section_key),
                state="current",
                linked_entity_ids=list(placement.linked_entity_ids),
                synthesis_origin="claim",
                confidence=claim.confidence,
                reason="Manual claim-level curation.",
                created_at=containing[0].created_at if containing else now,
                updated_at=now,
            ))
        pages = self.materializer.regenerate({value for value in affected if value})
        if owner_entity_id is None:
            return None
        return self._result(self.artifacts.get_entity(owner_entity_id), pages, [])

    def merge(self, source_entity_id: str, target_entity_id: str) -> CurationResult:
        if any(
            commit.status != "complete"
            for commit in self.artifacts.list_dream_commits()
        ):
            raise ValueError("Recover the pending Dream commit before merging entities")
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
                allowed = set(section_keys(target.entity_type))
                if placement.section_key not in allowed:
                    placement.section_key = default_section(
                        target.entity_type, claim.claim_type, claim.predicate
                    )
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
        for fact in self.artifacts.list_consolidated_facts():
            changed = False
            if fact.owner_entity_id == source_entity_id:
                fact.owner_entity_id = target_entity_id
                representative = self.artifacts.get_claim(fact.member_claim_ids[0])
                fact.section_key = default_section(
                    target.entity_type,
                    representative.claim_type,
                    representative.predicate,
                )
                changed = True
            if source_entity_id in fact.linked_entity_ids:
                fact.linked_entity_ids = [
                    target_entity_id if value == source_entity_id else value
                    for value in fact.linked_entity_ids
                ]
                changed = True
            if changed:
                fact.updated_at = _now()
                fact.__post_init__()
                self.artifacts.save_consolidated_fact(fact)
        self._redirect_merge_references(source, target)
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

    def _redirect_merge_references(
        self, source: EntityRecord, target: EntityRecord
    ) -> None:
        source_id = source.entity_id
        target_id = target.entity_id
        now = _now()

        for reference in self.artifacts.list_entity_references(
            entity_id=source_id, status="active"
        ):
            successor_id = f"ref-{uuid.uuid4().hex[:12]}"
            reference.status = "superseded"
            reference.superseded_by_reference_id = successor_id
            self.artifacts.save_entity_reference(reference)
            self.artifacts.save_entity_reference(ClaimEntityReference(
                reference_id=successor_id,
                claim_id=reference.claim_id,
                role=reference.role,
                surface=reference.surface,
                entity_id=target_id,
                confidence=1.0,
                reason=(
                    f"Manual entity merge redirected {source_id} to {target_id}."
                ),
                origin="manual",
                dream_run_id=reference.dream_run_id,
                status="active",
                created_at=now,
            ))

        for decision in self.artifacts.list_entity_resolution_decisions():
            changed = False
            if decision.entity_id == source_id:
                decision.entity_id = target_id
                changed = True
            if decision.proposed_parent_entity_id == source_id:
                decision.proposed_parent_entity_id = target_id
                changed = True
            if changed:
                note = f"Entity merge redirected {source_id} to {target_id}."
                decision.reviewer_note = " ".join(
                    value for value in [decision.reviewer_note, note] if value
                )
                self.artifacts.save_entity_resolution_decision(decision)

        for assessment in self.artifacts.list_identity_maturity_assessments():
            if assessment.entity_id != source_id:
                continue
            assessment.entity_id = target_id
            self.artifacts.save_identity_maturity_assessment(assessment)

        for encounter in self.artifacts.list_encounters(entity_id=source_id):
            encounter.entity_id = target_id
            self.artifacts.save_encounter(encounter)

        for cohort in self.artifacts.list_scope_cohorts():
            if source_id not in cohort.revision_entity_ids:
                continue
            cohort.revision_entity_ids = [
                target_id if value == source_id else value
                for value in cohort.revision_entity_ids
            ]
            cohort.__post_init__()
            self.artifacts.save_scope_cohort(cohort)

        for decision in self.artifacts.list_scope_decisions(status="active"):
            if (
                decision.owner_entity_id != source_id
                and source_id not in decision.linked_entity_ids
            ):
                continue
            successor = ClaimScopeDecision(
                decision_id=f"scope-{uuid.uuid4().hex[:12]}",
                claim_id=decision.claim_id,
                owner_entity_id=(
                    target_id
                    if decision.owner_entity_id == source_id
                    else decision.owner_entity_id
                ),
                section_key=decision.section_key,
                linked_entity_ids=[
                    target_id if value == source_id else value
                    for value in decision.linked_entity_ids
                ],
                supporting_claim_ids=list(decision.supporting_claim_ids),
                confidence=1.0,
                reason=f"Manual entity merge redirected {source_id} to {target_id}.",
                origin="manual",
                dream_run_id=None,
                status="active",
                created_at=now,
                identity_blocker_ids=list(decision.identity_blocker_ids),
            )
            self.artifacts.save_scope_decision(successor)

        for proposal in self.artifacts.list_organization_proposals(status="pending"):
            changed = False
            if proposal.proposed_owner_entity_id == source_id:
                proposal.proposed_owner_entity_id = target_id
                changed = True
            if proposal.source_entity_id == source_id:
                proposal.source_entity_id = target_id
                changed = True
            if proposal.target_entity_id == source_id:
                proposal.target_entity_id = target_id
                changed = True
            if (
                proposal.proposal_type == "merge_entities"
                and proposal.source_entity_id == proposal.target_entity_id
            ):
                proposal.status = "stale"
                proposal.reviewer_note = (
                    f"Entity merge redirected {source_id} to {target_id}; "
                    "this proposal no longer has distinct endpoints."
                )
                changed = True
            if changed:
                self.artifacts.save_organization_proposal(proposal)

        for proposal in self.artifacts.list_reconsolidation_proposals():
            if source_id not in proposal.affected_entity_ids:
                continue
            proposal.affected_entity_ids = [
                target_id if value == source_id else value
                for value in proposal.affected_entity_ids
            ]
            proposal.__post_init__()
            self.artifacts.save_reconsolidation_proposal(proposal)

        for unit in self.artifacts.list_identity_work_units():
            if unit.status == "complete":
                continue
            changed = False
            for field_name in (
                "subject_nodes",
                "identity_groups",
                "existing_identity_verdicts",
                "type_proposals",
                "type_verdicts",
                "new_identity_verdicts",
                "maturity_decisions",
                "maturity_verdicts",
                "entity_plan",
            ):
                current = getattr(unit, field_name)
                revised = self._replace_exact_id(current, source_id, target_id)
                if revised != current:
                    setattr(unit, field_name, revised)
                    changed = True
            if changed:
                unit.updated_at = now
                self.artifacts.save_identity_work_unit(unit)

    @staticmethod
    def _replace_exact_id(value, source_id: str, target_id: str):
        if isinstance(value, str):
            return target_id if value == source_id else value
        if isinstance(value, list):
            return [
                EntityCurationService._replace_exact_id(item, source_id, target_id)
                for item in value
            ]
        if isinstance(value, dict):
            return {
                key: EntityCurationService._replace_exact_id(
                    item, source_id, target_id
                )
                for key, item in value.items()
            }
        return value

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
            claim = self.artifacts.get_claim(claim_id)
            self.move_claim(
                claim_id,
                entity.entity_id,
                default_section(
                    entity.entity_type,
                    claim.claim_type,
                    claim.predicate,
                ),
                linked_entity_ids=list(placement.linked_entity_ids),
                reason="Manual entity split",
            )
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


class FactCurationService:
    """Manual editing and grouping for persisted presentation facts."""

    def __init__(self, artifacts: ArtifactStore, materializer: PageMaterializer):
        self.artifacts = artifacts
        self.materializer = materializer

    def edit(self, fact_id: str, text: str, *, reason: str) -> FactCurationResult:
        fact = self.artifacts.get_consolidated_fact(fact_id)
        fact.text = text
        fact.synthesis_origin = "manual"
        fact.manual_text = True
        fact.confidence = 1.0
        fact.reason = reason
        fact.updated_at = _now()
        fact.__post_init__()
        self.artifacts.save_consolidated_fact(fact)
        pages = self.materializer.regenerate({fact.owner_entity_id})
        return FactCurationResult([fact], sorted(pages.changed_pages))

    def move(
        self,
        fact_id: str,
        owner_entity_id: str,
        section_key: str,
        *,
        linked_entity_ids: list[str],
        reason: str,
    ) -> FactCurationResult:
        fact = self.artifacts.get_consolidated_fact(fact_id)
        old_ids = {fact.owner_entity_id, *fact.linked_entity_ids}
        now = _now()
        for claim_id in fact.member_claim_ids:
            old = self.artifacts.get_placement(claim_id)
            placement = ClaimPlacement(
                claim_id=claim_id,
                owner_entity_id=owner_entity_id,
                section_key=section_key,
                linked_entity_ids=list(linked_entity_ids),
                status="placed",
                reason=reason,
                created_at=old.created_at,
                updated_at=now,
            )
            self.artifacts.save_placement(placement)
            self.artifacts.save_scope_decision(ClaimScopeDecision(
                decision_id=f"scope-{uuid.uuid4().hex[:12]}",
                claim_id=claim_id,
                owner_entity_id=owner_entity_id,
                section_key=section_key,
                linked_entity_ids=list(linked_entity_ids),
                supporting_claim_ids=list(fact.member_claim_ids),
                confidence=1.0,
                reason=reason,
                origin="manual",
                dream_run_id=None,
                status="active",
                created_at=now,
            ))
        fact.owner_entity_id = owner_entity_id
        fact.section_key = section_key
        fact.linked_entity_ids = list(linked_entity_ids)
        fact.synthesis_origin = "manual"
        fact.reason = reason
        fact.updated_at = now
        fact.__post_init__()
        self.artifacts.save_consolidated_fact(fact)
        pages = self.materializer.regenerate(
            {owner_entity_id, *old_ids, *linked_entity_ids}
        )
        return FactCurationResult([fact], sorted(pages.changed_pages))

    def group(
        self, fact_ids: list[str], text: str, *, reason: str
    ) -> FactCurationResult:
        facts = [self.artifacts.get_consolidated_fact(value) for value in fact_ids]
        if len(facts) < 2:
            raise ValueError("Grouping requires at least two consolidated facts")
        scopes = {(fact.owner_entity_id, fact.section_key) for fact in facts}
        if len(scopes) != 1:
            raise ValueError("Facts must share one owner and section before grouping")
        owner, section = next(iter(scopes))
        now = _now()
        grouped = ConsolidatedFact(
            fact_id=f"fact-{uuid.uuid4().hex[:12]}",
            text=text,
            member_claim_ids=sorted({
                claim_id for fact in facts for claim_id in fact.member_claim_ids
            }),
            owner_entity_id=owner,
            section_key=section,
            state=(
                "current" if any(fact.state == "current" for fact in facts)
                else "history"
            ),
            linked_entity_ids=sorted({
                entity_id for fact in facts for entity_id in fact.linked_entity_ids
            }),
            synthesis_origin="manual",
            confidence=1.0,
            reason=reason,
            created_at=now,
            updated_at=now,
            manual_text=True,
        )
        for fact in facts:
            self.artifacts.delete_consolidated_fact(fact.fact_id)
        self.artifacts.save_consolidated_fact(grouped)
        pages = self.materializer.regenerate({owner})
        return FactCurationResult([grouped], sorted(pages.changed_pages))

    def split(
        self,
        fact_id: str,
        groups: list[dict[str, object]],
        *,
        reason: str,
    ) -> FactCurationResult:
        source = self.artifacts.get_consolidated_fact(fact_id)
        parsed_groups: list[tuple[list[str], str]] = []
        for group in groups:
            raw_ids = group.get("claim_ids")
            if not isinstance(raw_ids, list):
                raise ValueError("Each split group requires a claim_ids list")
            parsed_groups.append((
                [str(claim_id) for claim_id in raw_ids],
                str(group.get("text") or ""),
            ))
        member_ids = [
            claim_id for claim_ids, _ in parsed_groups for claim_id in claim_ids
        ]
        if (
            len(groups) < 2
            or len(member_ids) != len(set(member_ids))
            or set(member_ids) != set(source.member_claim_ids)
        ):
            raise ValueError("Split groups must partition the source fact's claims exactly")
        now = _now()
        created = []
        for claim_ids, text in parsed_groups:
            created.append(ConsolidatedFact(
                fact_id=f"fact-{uuid.uuid4().hex[:12]}",
                text=text,
                member_claim_ids=claim_ids,
                owner_entity_id=source.owner_entity_id,
                section_key=source.section_key,
                state=source.state,
                linked_entity_ids=list(source.linked_entity_ids),
                synthesis_origin="manual",
                confidence=1.0,
                reason=reason,
                created_at=now,
                updated_at=now,
                manual_text=True,
            ))
        self.artifacts.delete_consolidated_fact(source.fact_id)
        for fact in created:
            self.artifacts.save_consolidated_fact(fact)
        pages = self.materializer.regenerate({source.owner_entity_id})
        return FactCurationResult(created, sorted(pages.changed_pages))


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
                    origin="review",
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


class IdentityReviewService:
    """Apply an explicit user identity decision and reopen its evidence for routing."""

    def __init__(self, artifacts: ArtifactStore):
        self.artifacts = artifacts

    def review(
        self,
        decision_id: str,
        action: str,
        *,
        reviewer_note: str | None = None,
        entity_id: str | None = None,
        entity_type: str | None = None,
        title: str | None = None,
        scope: str | None = None,
        page_state: str | None = None,
        parent_entity_id: str | None = None,
    ) -> EntityResolutionDecision:
        record = self.artifacts.get_entity_resolution_decision(decision_id)
        if record.review_state != "review_required":
            raise ValueError("Only identity decisions requiring review may be adjudicated")
        now = _now()
        record.reviewer_note = reviewer_note
        record.reviewed_at = now
        if action == "reject":
            record.review_state = "rejected"
        elif action == "approve":
            selected_type = entity_type or record.proposed_entity_type
            selected_title = " ".join((title or record.proposed_title).split()).strip()
            selected_scope = scope or record.proposed_scope
            selected_page_state = page_state or record.proposed_page_state
            selected_parent = parent_entity_id or record.proposed_parent_entity_id
            self._validate_selection(
                selected_type, selected_scope, selected_page_state, selected_parent
            )
            entity = self._resolve_entity(
                entity_id if entity_id is not None else record.entity_id,
                selected_type,
                selected_title,
                record.proposed_aliases,
                selected_scope,
                selected_page_state,
                now,
            )
            record.entity_id = entity.entity_id if entity else None
            record.proposed_entity_type = selected_type
            record.proposed_title = selected_title
            record.proposed_scope = selected_scope
            record.proposed_page_state = selected_page_state
            record.proposed_parent_entity_id = selected_parent
            record.review_state = "accepted"
            if entity is not None:
                self._save_identity_references(record, entity.entity_id, now)
        else:
            raise ValueError("Identity review action must be approve or reject")
        self.artifacts.save_entity_resolution_decision(record)
        self._reopen_claims(record.supporting_claim_ids, decision_id, now)
        return record

    def _resolve_entity(
        self,
        entity_id: str | None,
        entity_type: str,
        title: str,
        aliases: list[str],
        scope: str | None,
        page_state: str | None,
        now: str,
    ) -> EntityRecord | None:
        if entity_id:
            entity = self.artifacts.get_entity(entity_id)
            if entity.status != "active":
                raise ValueError("Reviewed entity ID must be active")
            if entity.entity_type != entity_type:
                raise ValueError("Reviewed entity ID must match the selected entity type")
            entity.title = title
            entity.aliases = sorted({*entity.aliases, *aliases})
            if scope == "independent" and page_state == "materialized":
                entity.materialization_state = "materialized"
            entity.updated_at = now
            entity.__post_init__()
            self.artifacts.save_entity(entity)
            return entity
        if scope != "independent":
            return None
        return self.artifacts.create_entity(
            entity_type,
            title,
            aliases=aliases,
            materialization_state=page_state or "provisional",
        )

    def _validate_selection(
        self,
        entity_type: str,
        scope: str | None,
        page_state: str | None,
        parent_entity_id: str | None,
    ) -> None:
        if entity_type not in set(ENTITY_TYPES) - {"you"}:
            raise ValueError("Identity review requires a discoverable entity type")
        if scope == "independent":
            if page_state not in {"materialized", "provisional"} or parent_entity_id:
                raise ValueError("Independent identities require a page state and no parent")
            return
        if scope == "context":
            if page_state != "no_page" or parent_entity_id:
                raise ValueError("Context identities require no page and no parent")
            return
        if scope == "standalone_event":
            if entity_type != "event" or page_state != "no_page" or parent_entity_id:
                raise ValueError(
                    "Standalone events require Event type, no page, and no parent"
                )
            return
        if scope == "occurrence":
            if entity_type != "event":
                raise ValueError("Only Events may be reviewed as bounded occurrences")
        elif scope == "component":
            if entity_type == "event":
                raise ValueError("Events use occurrence rather than component scope")
        else:
            raise ValueError("Identity review requires an explicit scope")
        if page_state != "no_page" or not parent_entity_id:
            raise ValueError("Contained identities require an exact parent and no page")
        parent = self.artifacts.get_entity(parent_entity_id)
        if parent.status != "active" or parent.entity_type not in {"project", "series"}:
            raise ValueError("Contained identities require an active Project or Series parent")

    def _save_identity_references(
        self, record: EntityResolutionDecision, entity_id: str, now: str
    ) -> None:
        for claim_id in record.supporting_claim_ids:
            reference_id = f"ref-{uuid.uuid4().hex[:12]}"
            for prior in self.artifacts.list_entity_references(
                claim_id=claim_id, status="active"
            ):
                if prior.role != "identity_subject" or prior.origin != "manual":
                    continue
                prior.status = "superseded"
                prior.superseded_by_reference_id = reference_id
                self.artifacts.save_entity_reference(prior)
            self.artifacts.save_entity_reference(ClaimEntityReference(
                reference_id=reference_id,
                claim_id=claim_id,
                role="identity_subject",
                surface=record.proposed_title,
                entity_id=entity_id,
                confidence=1.0,
                reason=f"Approved identity adjudication {record.decision_id}",
                origin="manual",
                dream_run_id=record.dream_run_id,
                status="active",
                created_at=now,
            ))

    def _reopen_claims(
        self, claim_ids: list[str], decision_id: str, now: str
    ) -> None:
        for claim_id in claim_ids:
            claim = self.artifacts.get_claim(claim_id)
            if claim.status != "active":
                continue
            claim.dream_disposition = "pending"
            claim.dream_disposition_reason = (
                f"Identity adjudication {decision_id} requires rerouting."
            )
            claim.dream_run_id = None
            claim.dream_disposition_at = now
            self.artifacts.save_claim(claim)
