"""Transparent entity curation and review for the generated wiki."""

from __future__ import annotations

from mycelium.database import atomic_curation
import re
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimScopeDecision,
    ConsolidatedFact,
    EntityRecord,
    EntityResolutionDecision,
    OrganizationProposal,
)
from mycelium.materialization import MaterializationResult, PageMaterializer
from mycelium.ontology import (
    ENTITY_TYPES,
    SUBJECT_PAGE_STATES,
    SUBJECT_PERSISTED_SCOPES,
)
from mycelium.store import WikiStore
from mycelium.projection import display_claim_text
from mycelium import identity_context


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _normalized(value: str) -> str:
    return re.sub("[^a-z0-9]+", " ", value.lower()).strip()


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

    @atomic_curation
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
        if entity_type:
            entity.entity_type = entity_type
        entity.updated_at = _now()
        entity.__post_init__()
        self.artifacts.save_entity(entity)
        if old_slug != entity.slug:
            self.wiki.delete(old_slug)
        pages = self.materializer.regenerate({entity_id, "you"})
        return self._result(
            entity, pages, [old_slug] if old_slug != entity.slug else []
        )

    @atomic_curation
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

    @atomic_curation
    def move_claim(
        self,
        claim_id: str,
        owner_entity_id: str | None,
        section_key: str | None,
        *,
        linked_entity_ids: list[str] | None = None,
        page_sections: dict[str, str] | None = None,
        reason: str = "Manual wiki organization",
        origin: str = "manual",
    ) -> CurationResult | None:
        """An explicit claim assignment adds a view; existing items are independent."""
        claim = self.artifacts.get_claim(claim_id)
        if claim.status != "active":
            raise ValueError("Only active evidence can be added to a view")
        if owner_entity_id is None:
            if self.artifacts.facts_for_claim(claim_id):
                raise ValueError("Edit the cited view items to change their destinations")
            claim.dream_disposition = "deferred"
            claim.dream_disposition_reason = reason
            self.artifacts.save_claim(claim)
            return None
        now = _now()
        destinations = page_sections or {owner_entity_id: section_key}
        if not section_key or any(not heading for heading in destinations.values()):
            raise ValueError("Each view item requires a heading")
        for eid, heading in destinations.items():
            self.artifacts.save_consolidated_fact(ConsolidatedFact(
                f"fact-{uuid.uuid4().hex[:12]}", display_claim_text(claim), [claim_id],
                eid, heading, "current", list(linked_entity_ids or []), "manual", 1.0,
                reason, now, now, manual_text=True))
        claim.dream_disposition = "routed"
        claim.dream_disposition_reason, claim.dream_disposition_at = reason, now
        self.artifacts.save_claim(claim)
        pages = self.materializer.regenerate({*destinations, *(linked_entity_ids or [])})
        return self._result(self.artifacts.get_entity(owner_entity_id), pages, [])

    @atomic_curation
    def merge(self, source_entity_id: str, target_entity_id: str) -> CurationResult:
        source = self.artifacts.get_entity(source_entity_id)
        target = self.artifacts.get_entity(target_entity_id)
        if (
            source.entity_id == "you"
            or target.status != "active"
            or source.status != "active"
        ):
            raise ValueError(
                "Merge requires an active non-You source and active target"
            )
        if source.entity_type != target.entity_type and (
            not (source.entity_type == "person" and target.entity_id == "you")
        ):
            raise ValueError("Entities must have the same type to merge")
        for fact in self.artifacts.list_consolidated_facts():
            changed = False
            if fact.owner_entity_id == source_entity_id:
                fact.owner_entity_id = target_entity_id
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
        target.aliases = sorted(
            set([*target.aliases, source.title, source.slug, *source.aliases])
        )
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
            self.artifacts.save_entity_reference(
                ClaimEntityReference(
                    reference_id=successor_id,
                    claim_id=reference.claim_id,
                    role=reference.role,
                    surface=reference.surface,
                    entity_id=target_id,
                    confidence=1.0,
                    reason=f"Manual entity merge redirected {source_id} to {target_id}.",
                    origin="manual",
                    dream_run_id=reference.dream_run_id,
                    status="active",
                    created_at=now,
                    identity_decision_id=reference.identity_decision_id,
                )
            )
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
                    (value for value in [decision.reviewer_note, note] if value)
                )
                self.artifacts.save_entity_resolution_decision(decision)
        for pid in self.artifacts.db.ids("participant-bindings", "entity_id", source_id):
            bound = self.artifacts.db.get("participant-bindings", pid)
            identity_context.save_binding(self.artifacts, bound["source_id"], pid, target_id,
                                          bound["decision_id"], origin="user")
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
                owner_entity_id=target_id
                if decision.owner_entity_id == source_id
                else decision.owner_entity_id,
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
                proposal.reviewer_note = f"Entity merge redirected {source_id} to {target_id}; this proposal no longer has distinct endpoints."
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
                "entity_plan",
                "allocated_entity_ids",
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
                key: EntityCurationService._replace_exact_id(item, source_id, target_id)
                for key, item in value.items()
            }
        return value

    @atomic_curation
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
        owned = {c.claim_id for c in self.artifacts.claims_for_entity(source_entity_id)}
        if not selected or not selected <= owned:
            raise ValueError("Split claims must cite the source identity")
        facts = [f for f in self.artifacts.list_consolidated_facts()
                 if source_entity_id in {f.owner_entity_id, *f.linked_entity_ids}
                 and set(f.member_claim_ids) & selected]
        if any(not set(f.member_claim_ids) <= selected for f in facts):
            raise ValueError("Split mixed view items first, so their destinations can be reviewed explicitly")
        entity = self.artifacts.create_entity(entity_type, title, aliases=aliases)
        now = _now()
        for ref in self.artifacts.list_entity_references(entity_id=source_entity_id, status="active"):
            if ref.claim_id not in selected:
                continue
            successor = replace(ref, reference_id=f"ref-{uuid.uuid4().hex[:12]}", entity_id=entity.entity_id,
                                origin="manual", reason="Manual identity split", created_at=now)
            ref.status, ref.superseded_by_reference_id = "superseded", successor.reference_id
            self.artifacts.save_entity_reference(ref)
            self.artifacts.save_entity_reference(successor)
        for fact in facts:
            if fact.owner_entity_id == source_entity_id:
                fact.owner_entity_id = entity.entity_id
            fact.linked_entity_ids = [entity.entity_id if x == source_entity_id else x for x in fact.linked_entity_ids]
            fact.manual_text, fact.synthesis_origin, fact.updated_at = True, "manual", now
            fact.__post_init__()
            self.artifacts.save_consolidated_fact(fact)
        pages = self.materializer.regenerate(
            {source.entity_id, entity.entity_id, "you"}
        )
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

    @atomic_curation
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
        fact.owner_entity_id = owner_entity_id
        fact.section_key = section_key
        fact.linked_entity_ids = list(linked_entity_ids)
        fact.synthesis_origin = "manual"
        fact.manual_text = True
        fact.reason = reason
        fact.updated_at = now
        fact.__post_init__()
        self.artifacts.save_consolidated_fact(fact)
        pages = self.materializer.regenerate(
            {owner_entity_id, *old_ids, *linked_entity_ids}
        )
        return FactCurationResult([fact], sorted(pages.changed_pages))

    @atomic_curation
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
            member_claim_ids=sorted(
                {claim_id for fact in facts for claim_id in fact.member_claim_ids}
            ),
            owner_entity_id=owner,
            section_key=section,
            state="current"
            if any((fact.state == "current" for fact in facts))
            else "history",
            linked_entity_ids=sorted(
                {entity_id for fact in facts for entity_id in fact.linked_entity_ids}
            ),
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

    @atomic_curation
    def split(
        self, fact_id: str, groups: list[dict[str, object]], *, reason: str
    ) -> FactCurationResult:
        source = self.artifacts.get_consolidated_fact(fact_id)
        parsed_groups: list[tuple[list[str], str]] = []
        for group in groups:
            raw_ids = group.get("claim_ids")
            if not isinstance(raw_ids, list):
                raise ValueError("Each split group requires a claim_ids list")
            parsed_groups.append(
                ([str(claim_id) for claim_id in raw_ids], str(group.get("text") or ""))
            )
        member_ids = [
            claim_id for claim_ids, _ in parsed_groups for claim_id in claim_ids
        ]
        if (
            len(groups) < 2
            or any(not ids for ids, _ in parsed_groups)
            or set(member_ids) != set(source.member_claim_ids)
        ):
            raise ValueError(
                "Split items must cite only the original evidence and together cover it; citations may be shared"
            )
        now = _now()
        created = []
        for claim_ids, text in parsed_groups:
            created.append(
                ConsolidatedFact(
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
                )
            )
        self.artifacts.delete_consolidated_fact(source.fact_id)
        for fact in created:
            self.artifacts.save_consolidated_fact(fact)
        pages = self.materializer.regenerate({source.owner_entity_id})
        return FactCurationResult(created, sorted(pages.changed_pages))


class OrganizationReviewService:
    def __init__(self, artifacts: ArtifactStore, curation: EntityCurationService):
        self.artifacts = artifacts
        self.curation = curation

    @atomic_curation
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
                if (
                    proposal.source_entity_id is None
                    or proposal.target_entity_id is None
                ):
                    raise ValueError("Merge proposal is incomplete")
                self.curation.merge(
                    proposal.source_entity_id, proposal.target_entity_id
                )
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

    @atomic_curation
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
        claim_texts: dict[str, str] | None = None,
    ) -> EntityResolutionDecision:
        record = self.artifacts.get_entity_resolution_decision(decision_id)
        if record.review_state not in {"review_required", "accepted"}:
            raise ValueError(
                "Only current identity decisions may be corrected"
            )
        if action == "reject" and record.review_state != "review_required":
            raise ValueError("Correct an accepted identity by selecting its replacement")
        if claim_texts and action != "approve":
            raise ValueError("Statement wording requires an explicit identity selection")
        if not (claim_texts or {}).keys() <= set(record.supporting_claim_ids):
            raise ValueError("Wording changes must belong to the reviewed identity")
        now = _now()
        history_id = f"identity-review-{uuid.uuid4().hex[:12]}"
        self.artifacts.db.put("identity-review-history", history_id, {
            "decision_id": decision_id, "before": asdict(record), "created_at": now,
            "claim_texts": {cid: self.artifacts.get_claim(cid).text for cid in (claim_texts or {})},
        })
        original_entity_id = record.entity_id
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
            record.proposed_entity_type = entity.entity_type if entity else selected_type
            record.proposed_title = entity.title if entity else selected_title
            record.proposed_scope = selected_scope
            record.proposed_page_state = selected_page_state
            record.proposed_parent_entity_id = selected_parent
            record.review_state = "accepted"
            if entity is not None:
                self._save_identity_references(record, entity.entity_id, now, original_entity_id)
                for pid in record.participant_ids:
                    bound = identity_context.binding(self.artifacts, pid)
                    if bound:
                        identity_context.save_binding(self.artifacts, bound["source_id"], pid,
                            entity.entity_id, record.decision_id, origin="user")
        else:
            raise ValueError("Identity review action must be approve or reject")
        self.artifacts.save_entity_resolution_decision(record)
        if claim_texts:
            from mycelium.claim_lifecycle import correct_identity_wording
            correct_identity_wording(self.artifacts, record, claim_texts, now)
            record = self.artifacts.get_entity_resolution_decision(decision_id)
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
            if entity_id == "you" and entity_type == "person":
                # An explicit review may identify a speaker as the user. The
                # occurrence's tentative name must not rename the canonical You.
                return entity
            if entity.entity_type != entity_type:
                raise ValueError(
                    "Reviewed entity ID must match the selected entity type"
                )
            # Selecting an existing identity is not an entity rename. Its label
            # is edited explicitly through EntityCurationService instead.
            if scope == "independent" and page_state == "materialized":
                entity.materialization_state = "materialized"
            entity.updated_at = now
            entity.__post_init__()
            self.artifacts.save_entity(entity)
            return entity
        # Identity persists independently of page admission. A no-page review
        # restricts only this occurrence and must retain a stable binding.
        return self.artifacts.create_entity(
            entity_type,
            title,
            aliases=aliases,
            materialization_state="provisional" if page_state == "no_page" else page_state or "provisional",
        )

    def _validate_selection(
        self,
        entity_type: str,
        scope: str | None,
        page_state: str | None,
        parent_entity_id: str | None,
    ) -> None:
        if entity_type not in set(ENTITY_TYPES):
            raise ValueError("Identity review requires a discoverable entity type")
        if scope is None and page_state is None and parent_entity_id is None:
            return
        if scope not in SUBJECT_PERSISTED_SCOPES:
            raise ValueError("Identity review requires an explicit scope")
        if page_state not in SUBJECT_PAGE_STATES:
            raise ValueError("Identity review requires an explicit page state")
        if scope == "independent":
            if page_state not in {"materialized", "provisional"} or parent_entity_id:
                raise ValueError(
                    "Independent identities require a page state and no parent"
                )
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
        if page_state != "no_page" or not parent_entity_id:
            raise ValueError("Contained identities require an exact parent and no page")
        parent = self.artifacts.get_entity(parent_entity_id)
        if parent.status != "active" or parent.entity_type not in {"project", "series"}:
            raise ValueError(
                "Contained identities require an active Project or Series parent"
            )

    def _save_identity_references(
        self, record: EntityResolutionDecision, entity_id: str, now: str, original_entity_id: str | None
    ) -> None:
        for claim_id in record.supporting_claim_ids:
            reference_id = f"ref-{uuid.uuid4().hex[:12]}"
            for prior in self.artifacts.list_entity_references(
                claim_id=claim_id, status="active"
            ):
                same_review = prior.role == "identity_subject" and prior.origin == "manual" and prior.identity_decision_id == record.decision_id
                superseded_subject = prior.origin != "manual" and prior.entity_id == original_entity_id
                if not (same_review or superseded_subject):
                    continue
                prior.status = "superseded"
                prior.superseded_by_reference_id = reference_id
                self.artifacts.save_entity_reference(prior)
            self.artifacts.save_entity_reference(
                ClaimEntityReference(
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
                    identity_decision_id=record.decision_id,
                )
            )

    def _reopen_claims(self, claim_ids: list[str], decision_id: str, now: str) -> None:
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
