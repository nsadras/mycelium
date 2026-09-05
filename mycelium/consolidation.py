"""Semantic entity ownership planning for deterministic wiki consolidation."""

from __future__ import annotations

import uuid
import hashlib
import json
from dataclasses import replace
from datetime import datetime
from typing import Iterable

from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.consolidation_models import (
    ClaimEvidence, ClaimRoute, RoutingFailure, RoutingResult, slugify,
)
from mycelium.consolidation_resolution import ResolutionArtifacts
from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    EntityRecord,
    EntityResolutionDecision,
    IdentityWorkUnit,
)
from mycelium.ollama import OllamaClient
from mycelium.identity_plan import identity_plan_model, identity_plan_prompt, planned_subjects, declared_user_bindings
from mycelium.page_plan import page_plan_model, page_plan_prompt


class ClaimRouter:
    """Plan one validated entity owner for every admitted claim."""

    def __init__(self, llm: OllamaClient, artifacts: ArtifactStore):
        self.llm = llm
        self.artifacts = artifacts
        self.formatter = RoutingFormatter(artifacts)
        self.resolution = ResolutionArtifacts()

    async def route(
        self,
        evidence: list[ClaimEvidence],
        *,
        dream_run_id: str = "unpersisted",
        seed_entities: Iterable[EntityRecord] = (),
        participant_source_ids: set[str] | None = None,
    ) -> RoutingResult:
        """Route bounded source cohorts so one malformed identity plan stays local."""
        result = RoutingResult()
        seeds = list(seed_entities)
        pending_decisions: dict[str, EntityResolutionDecision] = {}
        for unit_evidence in self._identity_units(evidence):
            unit = self._work_unit(unit_evidence, dream_run_id)
            partial = await self._route_unit(
                unit_evidence,
                dream_run_id=dream_run_id,
                seed_entities=seeds,
                participant_source_ids=participant_source_ids,
                work_unit=unit,
                seed_identity_decisions=pending_decisions.values(),
            )
            self._merge_result(result, partial)
            seeds.extend(partial.new_entities)
            pending_decisions.update({
                decision.decision_id: decision
                for decision in partial.entity_decisions
                if decision.decision_type == "entity_creation"
                and decision.review_state == "review_required"
            })
        return result

    async def _route_unit(
        self, evidence: list[ClaimEvidence], *, dream_run_id: str = "unpersisted",
        seed_entities: Iterable[EntityRecord] = (), participant_source_ids=None,
        work_unit: IdentityWorkUnit, seed_identity_decisions=(),
    ) -> RoutingResult:
        if not evidence:
            return RoutingResult()
        result = RoutingResult()
        planned = {e.entity_id: e for e in self.artifacts.list_entities()}
        planned.update({e.entity_id: e for e in seed_entities})
        aliases = {f"C{index:03d}": item for index, item in enumerate(evidence, 1)}
        participants = self.resolution.participant_occurrences(
            evidence, source_ids=participant_source_ids,
        )
        schema = identity_plan_model(
            aliases, {p: role for p, (_, _, role) in participants.items()},
            {e.entity_id: e.entity_type for e in planned.values() if e.status == "active"},
        )
        work_unit.attempt_count += 1
        work_unit.status = "pending"
        now = datetime.now().astimezone().isoformat()
        pending = [
            *self.artifacts.list_entity_resolution_decisions(review_state="review_required"),
            *seed_identity_decisions,
        ]
        try:
            if work_unit.entity_plan:
                plan = schema.model_validate(work_unit.entity_plan).model_dump()
            else:
                system, user = identity_plan_prompt(
                    self.formatter.entity_planning_catalog(planned.values()),
                    self.formatter.format_evidence(aliases, participants),
                    self.formatter.identity_review_catalog(aliases),
                    self.formatter.format_pending_identity_proposals(pending),
                    declared_user_bindings(participants),
                )
                plan = schema.model_validate(await self.llm.call_structured(
                    system, user, schema, num_predict=8192, debug_label="dream-identity-plan",
                )).model_dump()
            # Explicit human identity references are authoritative exact-ID constraints.
            for node in planned_subjects(plan):
                reviewed = {
                    ref.entity_id for alias in node["supporting_evidence"] if alias in aliases
                    for ref in self.artifacts.list_entity_references(
                        claim_id=aliases[alias].claim.claim_id, status="active",
                    ) if ref.role == "identity_subject" and ref.origin == "manual" and ref.entity_id
                }
                if reviewed and (node["resolution"] != "existing" or reviewed != {node["entity_id"]}):
                    raise ValueError("Identity plan conflicts with an explicit human identity decision")
            work_unit.entity_plan = plan
            work_unit.stage = "claim_routing"
            self.artifacts.save_identity_work_unit(work_unit)
        except Exception as exc:
            return self._fail_work_unit(work_unit, evidence, "identity_plan",
                                        f"Identity plan failed: {type(exc).__name__}: {exc}")

        resolved = []
        blockers: dict[str, list[str]] = {}
        for node in planned_subjects(plan):
            support = [aliases[a] for a in node["supporting_evidence"] if a in aliases]
            participant_support = [participants[p] for p in node["participant_evidence"]]
            entity = None
            if node["resolution"] == "existing":
                # Never mutate registry objects in place before the build commit.
                entity = replace(planned[node["entity_id"]])
                entity.aliases = sorted(set(entity.aliases + node["aliases"]))
                if entity.entity_id != "you":
                    entity.aliases = sorted(set(entity.aliases + node["aliases"] +
                                                ([entity.title] if entity.title != node["title"] else [])))
                    entity.title = node["title"]
                entity.updated_at = now
                entity.__post_init__()
            elif node["resolution"] == "new":
                allocated_id = work_unit.allocated_entity_ids.get(node["node_id"])
                if allocated_id in planned:
                    entity = replace(planned[allocated_id])
                else:
                    entity = self._planned_entity(
                        node["entity_type"], node["title"], planned.values(), now,
                        aliases=node["aliases"],
                        materialization_state="provisional",
                    )
                    work_unit.allocated_entity_ids[node["node_id"]] = entity.entity_id
            if entity:
                planned[entity.entity_id] = entity
                result.new_entities.append(entity)
            decision = EntityResolutionDecision(
                decision_id=f"identity-{uuid.uuid4().hex[:12]}", decision_type="entity_creation",
                entity_id=entity.entity_id if entity else None,
                proposed_entity_type=node["entity_type"], proposed_title=node["title"],
                proposed_aliases=node["aliases"], proposed_scope="independent",
                proposed_page_state=entity.materialization_state if entity else "provisional",
                source_ids=sorted({*[s.source.source_id for s in support],
                                   *[s.source_id for s, _, _ in participant_support]}),
                supporting_claim_ids=[s.claim.claim_id for s in support],
                identity_evidence_claim_ids=[s.claim.claim_id for s in support],
                supporting_segment_ids=sorted({
                    *[seg for s in support for p in s.claim.provenance for seg in p.segment_ids],
                    *[seg.segment_id for s, name, role in participant_support for seg in s.segments
                      if seg.speaker == name and seg.role == role],
                }),
                confidence=node["confidence"], reason=node["reason"],
                review_state="accepted" if entity else "review_required",
                dream_run_id=dream_run_id, created_at=now,
            )
            result.entity_decisions.append(decision)
            if entity is None:
                for alias in node["supporting_evidence"]:
                    if alias in aliases:
                        blockers.setdefault(alias, []).append(decision.decision_id)
                # A participant binding covers that speaker's exact cited segments.
                participant_segments = set(decision.supporting_segment_ids)
                for alias, item in aliases.items():
                    if any(participant_segments.intersection(p.segment_ids) for p in item.claim.provenance):
                        blockers.setdefault(alias, []).append(decision.decision_id)
            resolved.append({
                **node, "entity_id": entity.entity_id if entity else None,
                "participant_bindings": node["participant_evidence"],
            })

        routable = {e.entity_id: e.entity_type for e in planned.values() if e.status == "active"}
        routings = {a: {"route_kind": "deferred", "confidence": 1.0,
                       "reason": "A supporting identity requires review."} for a in blockers}
        for batch in self._alias_batches({a: item for a, item in aliases.items() if a not in blockers}):
            routing_model = page_plan_model(batch, routable)
            system, user = page_plan_prompt(
                self.formatter.entity_catalog(planned.values(), include_sections=True),
                json.dumps(resolved, ensure_ascii=False),
                self.formatter.format_evidence(batch, self.resolution.participants_for_evidence(batch, participants)),
            )
            try:
                routings.update(routing_model.model_validate(await self.llm.call_structured(
                    system, user, routing_model, num_predict=8192, debug_label="dream-claim-routing",
                )).model_dump()["decisions"])
            except Exception as exc:
                result.failures.extend(self._failure(item, f"Claim routing failed: {exc}") for item in batch.values())
        for alias, routing in routings.items():
            kind = routing["route_kind"]
            destinations = {p["entity_id"]: p["section_key"] for p in routing.get("pages", [])}
            normalized = {
                "disposition": "deferred" if kind == "deferred" else "canonical",
                "owner_entity": routing.get("owner_entity", ""),
                "linked_entities": list(destinations),
                "subject_entity": "",
                "object_entities": [], "contextual_entities": [], "relationship_kind": "none",
                "page_sections": destinations,
                "supporting_claims": [], "identity_blocker_ids": blockers.get(alias, []),
                "confidence": routing["confidence"],
                "reason": routing["reason"] + "\n" + "\n".join(
                    f"Page {p['entity_id']}: {p['reason']}" for p in routing.get("pages", [])
                ),
            }
            route = self._route_decision(alias, aliases[alias], normalized, aliases, planned, {}, {})
            result.routes.append(route)
            if route.placed:
                for entity_id in route.page_sections:
                    entity = planned[entity_id]
                    if entity.materialization_state != "materialized":
                        entity.materialization_state = "materialized"
                        if not any(e.entity_id == entity_id for e in result.new_entities):
                            result.new_entities.append(entity)
        result.entity_references = self.resolution.claim_entity_references(
            aliases, result.routes, planned, dream_run_id, now,
        )
        work_unit.status = "failed" if result.failures else "complete"
        work_unit.stage = "claim_routing" if result.failures else "complete"
        work_unit.last_error = result.failures[0].reason if result.failures else None
        work_unit.updated_at = now
        self.artifacts.save_identity_work_unit(work_unit)
        return result

    @staticmethod
    def _identity_units(
        evidence: list[ClaimEvidence], size: int = 16
    ) -> list[list[ClaimEvidence]]:
        """Bound identity contracts while preserving the cohort's stable order."""
        return [
            evidence[start:start + size]
            for start in range(0, len(evidence), size)
        ]

    def _work_unit(
        self, evidence: list[ClaimEvidence], dream_run_id: str
    ) -> IdentityWorkUnit:
        claim_ids = sorted(item.claim.claim_id for item in evidence)
        # Cached plans belong to this decision contract, not the retired cascade.
        digest = hashlib.sha256(("identity-page-placement-v1\n" + "\n".join(claim_ids)).encode()).hexdigest()[:16]
        unit_id = f"identity-work-{digest}"
        try:
            unit = self.artifacts.get_identity_work_unit(unit_id)
        except FileNotFoundError:
            unit = IdentityWorkUnit(
                unit_id=unit_id,
                claim_ids=claim_ids,
                source_ids=sorted({item.source.source_id for item in evidence}),
            )
        unit.dream_run_ids.append(dream_run_id)
        if unit.status == "complete":
            unit.entity_plan = {}
            unit.allocated_entity_ids = {}
        unit.dream_run_ids = list(dict.fromkeys(unit.dream_run_ids))
        return unit

    @staticmethod
    def _merge_result(target: RoutingResult, source: RoutingResult) -> None:
        target.routes.extend(source.routes)
        target.new_entities.extend(source.new_entities)
        target.failures.extend(source.failures)
        target.encounters.extend(source.encounters)
        decisions = {
            decision.decision_id: decision for decision in target.entity_decisions
        }
        decisions.update({
            decision.decision_id: decision for decision in source.entity_decisions
        })
        target.entity_decisions = list(decisions.values())
        target.maturity_assessments.extend(source.maturity_assessments)
        target.entity_references.extend(source.entity_references)

    def _fail_work_unit(
        self,
        work_unit: IdentityWorkUnit,
        evidence: Iterable[ClaimEvidence],
        stage: str,
        reason: str,
    ) -> RoutingResult:
        work_unit.status = "failed"
        work_unit.stage = stage
        work_unit.last_error = reason
        work_unit.updated_at = datetime.now().astimezone().isoformat()
        self.artifacts.save_identity_work_unit(work_unit)
        return self._fail_batch(evidence, reason)

    def _route_decision(
        self,
        alias: str,
        item: ClaimEvidence,
        decision: dict,
        aliases: dict[str, ClaimEvidence],
        entities: dict[str, EntityRecord],
        candidates: dict[str, EntityRecord],
        candidate_support: dict[str, tuple[str, ...]],
    ) -> ClaimRoute:
        disposition = str(decision["disposition"])
        support_aliases = tuple(dict.fromkeys([
            alias,
            *decision["supporting_claims"],
            *candidate_support.get(str(decision.get("owner_entity") or ""), ()),
        ]))
        supporting_ids = tuple(
            aliases[value].claim.claim_id
            for value in support_aliases
            if value in aliases
        )
        identity_blockers = tuple(sorted({
            *self._unresolved_identity_blockers(item.claim.claim_id, entities),
            *decision.get("identity_blocker_ids", []),
        }))
        if disposition != "canonical":
            return ClaimRoute(
                item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                str(decision["reason"]), disposition, supporting_ids,
                float(decision["confidence"]),
                identity_blocker_ids=identity_blockers,
            )
        if identity_blockers:
            return ClaimRoute(
                item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                "An attached identity decision is still unresolved.",
                "deferred", supporting_ids, float(decision["confidence"]),
                identity_blocker_ids=identity_blockers,
            )
        owner_ref = str(decision["owner_entity"])
        owner = candidates.get(owner_ref) or entities.get(owner_ref)
        if (
            owner is None
            or owner.status != "active"
        ):
            return ClaimRoute(
                item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                f"Proposed owner {owner_ref!r} is not yet materialized. {decision['reason']}",
                "deferred", supporting_ids, float(decision["confidence"]),
            )
        link_refs = [str(value) for value in decision["linked_entities"]]
        subject_ref = str(decision.get("subject_entity") or "")
        object_refs = [str(value) for value in decision.get("object_entities", [])]
        contextual_refs = [
            str(value) for value in decision.get("contextual_entities", [])
        ]
        endpoint_refs = [
            *link_refs,
            *([subject_ref] if subject_ref else []),
            *object_refs,
        ]
        linked = set()
        resolved_references: dict[str, str] = {}
        for value in dict.fromkeys([
            *endpoint_refs,
            *contextual_refs,
        ]):
            linked_entity = candidates.get(value) or entities.get(value)
            if (
                linked_entity is None
                or linked_entity.status != "active"
            ):
                return ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    f"Proposed linked entity {value!r} was not admitted or active. "
                    f"{decision['reason']}",
                    "deferred", supporting_ids, float(decision["confidence"]),
                )
            resolved_references[value] = linked_entity.entity_id
        linked.update(resolved_references[value] for value in endpoint_refs)
        linked.discard(owner.entity_id)
        relationship_kind = str(decision.get("relationship_kind") or "none")
        if item.claim.evidence_modality == "tool":
            if "you" in decision.get("page_sections", {}):
                return ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    "External evidence cannot automatically establish a personal fact on You.",
                    "deferred", supporting_ids, float(decision["confidence"]),
                )
        return ClaimRoute(
            item.claim.claim_id, owner.entity_id, decision["page_sections"][owner.entity_id], tuple(sorted(linked)),
            item.raw_log_entry_id, str(decision["reason"]), "canonical",
            supporting_ids, float(decision["confidence"]),
            resolved_references.get(subject_ref) if subject_ref else None,
            tuple(sorted({resolved_references[value] for value in object_refs})),
            tuple(sorted({
                resolved_references[value] for value in contextual_refs
            })),
            None if relationship_kind == "none" else relationship_kind,
            page_sections=dict(decision["page_sections"]),
        )

    def _unresolved_identity_blockers(
        self,
        claim_id: str,
        entities: dict[str, EntityRecord],
    ) -> tuple[str, ...]:
        placement = self.artifacts.placement_for_claim(claim_id)
        if placement is None:
            return ()
        unresolved = []
        for decision_id in placement.identity_blocker_ids:
            try:
                decision = self.artifacts.get_entity_resolution_decision(
                    decision_id
                )
            except FileNotFoundError:
                unresolved.append(decision_id)
                continue
            if decision.review_state == "rejected":
                continue
            if decision.review_state == "review_required":
                unresolved.append(decision_id)
                continue
            entity = entities.get(str(decision.entity_id or ""))
            if (
                decision.proposed_page_state == "provisional"
                and (
                    entity is None
                    or entity.materialization_state != "materialized"
                )
            ):
                unresolved.append(decision_id)
        return tuple(sorted(set(unresolved)))

    @staticmethod
    def _alias_batches(
        aliases: dict[str, ClaimEvidence], size: int = 24
    ) -> Iterable[dict[str, ClaimEvidence]]:
        """Bound unusually large routing responses without splitting ordinary cohorts."""
        items = list(aliases.items())
        for start in range(0, len(items), size):
            yield dict(items[start:start + size])

    @staticmethod
    def _planned_entity(
        entity_type: str,
        title: str,
        existing: Iterable[EntityRecord],
        now: str,
        *,
        aliases: Iterable[str] = (),
        materialization_state: str = "materialized",
    ) -> EntityRecord:
        existing = list(existing)
        slug = slugify(title)
        used_slugs = {entity.slug for entity in existing}
        base_slug = slug
        suffix = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        base_id = f"{entity_type}-{base_slug}"
        entity_id = base_id
        used_ids = {entity.entity_id for entity in existing}
        suffix = 2
        while entity_id in used_ids:
            entity_id = f"{base_id}-{suffix}"
            suffix += 1
        return EntityRecord(
            entity_id=entity_id,
            entity_type=entity_type,
            title=title,
            slug=slug,
            aliases=sorted({
                " ".join(alias.split()).strip()
                for alias in aliases
                if alias.strip() and slugify(alias) != slugify(title)
            }),
            status="active",
            created_at=now,
            updated_at=now,
            materialization_state=materialization_state,
        )

    @staticmethod
    def _failure(item: ClaimEvidence, reason: str) -> RoutingFailure:
        return RoutingFailure(item.claim.claim_id, item.raw_log_entry_id, reason)

    def _fail_batch(
        self,
        evidence: Iterable[ClaimEvidence],
        reason: str,
    ) -> RoutingResult:
        return RoutingResult(
            failures=[self._failure(item, reason) for item in evidence],
        )


def placement_from_route(route: ClaimRoute, *, now: str | None = None) -> ClaimPlacement:
    timestamp = now or datetime.now().astimezone().isoformat()
    return ClaimPlacement(
        claim_id=route.claim_id,
        owner_entity_id=route.owner_entity_id,
        section_key=(route.section_key or "needs_review") if route.placed else None,
        linked_entity_ids=list(route.linked_entity_ids),
        status="placed" if route.placed else "deferred",
        reason=route.reason,
        created_at=timestamp,
        updated_at=timestamp,
        relationship_kind=route.relationship_kind,
        identity_blocker_ids=list(route.identity_blocker_ids),
        page_sections=dict(route.page_sections),
    )
