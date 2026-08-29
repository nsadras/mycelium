"""Semantic entity ownership planning for deterministic wiki consolidation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable

from mycelium import prompts
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
)
from mycelium.ontology import (
    section_keys,
)
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import (
    claim_routing_output_model,
    entity_plan_output_model,
    subject_node_output_model,
)


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
        result = RoutingResult()
        planned = {entity.entity_id: entity for entity in self.artifacts.list_entities()}
        planned.update({entity.entity_id: entity for entity in seed_entities})
        initially_materialized = {
            entity.entity_id
            for entity in planned.values()
            if entity.materialization_state == "materialized"
        }
        initially_provisional = {
            entity.entity_id
            for entity in planned.values()
            if entity.materialization_state == "provisional"
        }
        if not evidence:
            return result
        aliases = {f"C{index:03d}": item for index, item in enumerate(evidence, start=1)}
        participants = self.resolution.participant_occurrences(
            evidence, source_ids=participant_source_ids
        )
        allowed_evidence = {*aliases, *participants}
        registry_types = {
            entity.entity_id: entity.entity_type
            for entity in planned.values()
            if entity.status == "active"
        }
        node_model = subject_node_output_model(allowed_evidence)
        system, user = prompts.subject_node_prompt(
            self.formatter.entity_catalog(planned.values(), include_sections=False),
            self.formatter.format_evidence(aliases, participants),
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                node_model,
                num_predict=8192,
                debug_label="dream-subject-nodes",
            )
            node_plan = node_model.model_validate(response).model_dump()
            if any(
                set(node["supporting_evidence"]) - allowed_evidence
                for node in node_plan["nodes"]
            ):
                raise ValueError("Subject node census cited an unknown evidence alias")
            graph_nodes = {
                node["node_id"]: node for node in node_plan["nodes"]
            }
            if len(graph_nodes) != len(node_plan["nodes"]):
                raise ValueError("Subject node census repeated a node ID")
        except Exception as exc:
            return self._fail_batch(
                evidence,
                "Subject node response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        node_types = {
            node_id: str(node["entity_type"])
            for node_id, node in graph_nodes.items()
        }
        try:
            entity_model = entity_plan_output_model(
                node_types,
                {alias: role for alias, (_, _, role) in participants.items()},
                registry_types,
            )
            system, user = prompts.entity_plan_prompt(
                self.formatter.entity_planning_catalog(planned.values()),
                self.formatter.format_subject_graph(graph_nodes, []),
                self.formatter.format_evidence(aliases, participants),
            )
            response = await self.llm.call_structured(
                system,
                user,
                entity_model,
                num_predict=8192,
                debug_label="dream-entity-plan",
            )
            entity_plan = entity_model.model_validate(response).model_dump()
            entity_decisions = entity_plan["decisions"]
            if set(entity_decisions) != set(graph_nodes):
                raise ValueError("Entity plan did not cover exact census nodes")
            if set(entity_plan["participants"]) != set(participants):
                raise ValueError("Entity plan did not resolve exact participants")
            for node_id, decision in entity_decisions.items():
                parent = str(decision["parent_entity"])
                containment = str(decision["containment"])
                if parent:
                    if parent == node_id:
                        raise ValueError("An entity cannot contain itself")
                    expected = (
                        "occurrence_of"
                        if graph_nodes[node_id]["entity_type"] == "event"
                        else "component_of"
                    )
                    if containment != expected or decision["page_state"] != "no_page":
                        raise ValueError("Contained entity plan is internally inconsistent")
                    if parent in graph_nodes:
                        parent_decision = entity_decisions[parent]
                        if (
                            not parent_decision["entity_id"]
                            and parent_decision["page_state"] == "no_page"
                        ):
                            raise ValueError(
                                "Entity plan parent did not resolve to a reusable identity"
                            )
                elif containment != "none":
                    raise ValueError("Containment requires an exact parent entity")
            for resolution in entity_plan["participants"].values():
                entity_ref = str(resolution["entity"])
                if entity_ref == "you":
                    continue
                existing = planned.get(entity_ref)
                if existing is not None and existing.entity_type == "person":
                    continue
                if (
                    entity_ref not in graph_nodes
                    or graph_nodes[entity_ref]["entity_type"] != "person"
                ):
                    raise ValueError("Participant did not resolve to a Person node")
        except Exception as exc:
            return self._fail_batch(
                evidence,
                "Entity plan response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        graph_edges = [
            {
                "source_node": node_id,
                "target_node": decision["parent_entity"],
                "relation": decision["containment"],
                "supporting_evidence": graph_nodes[node_id]["supporting_evidence"],
            }
            for node_id, decision in entity_decisions.items()
            if decision["parent_entity"]
        ]
        graph_plan = {
            "nodes": node_plan["nodes"],
            "edges": graph_edges,
            "participants": entity_plan["participants"],
        }

        candidate_entities: dict[str, EntityRecord] = {}
        candidate_support: dict[str, tuple[str, ...]] = {}
        now = datetime.now().astimezone().isoformat()
        for node_id, node in graph_nodes.items():
            decision = entity_decisions[node_id]
            support = tuple(
                value for value in dict.fromkeys(node["supporting_evidence"])
                if value in aliases
            )
            participant_alias_support = tuple(
                value for value in dict.fromkeys(node["supporting_evidence"])
                if value in participants
            )
            supporting = [aliases[value] for value in support]
            participant_support = [
                participants[value]
                for value in participant_alias_support
            ]
            confidence = float(decision["confidence"])
            accepted = confidence >= 0.7
            page_state = str(decision["page_state"])
            entity: EntityRecord | None = None
            if decision["entity_id"]:
                entity = planned[str(decision["entity_id"])]
                before = (
                    entity.title,
                    tuple(entity.aliases),
                    entity.materialization_state,
                )
                if accepted:
                    previous_title = entity.title
                    entity.title = str(decision["preferred_title"])
                    entity.aliases = sorted({
                        *entity.aliases,
                        *[str(value) for value in decision["aliases"]],
                        *([previous_title] if previous_title != entity.title else []),
                    })
                    if page_state == "materialized":
                        entity.materialization_state = "materialized"
                    entity.updated_at = now
                    entity.__post_init__()
                    after = (
                        entity.title,
                        tuple(entity.aliases),
                        entity.materialization_state,
                    )
                    if after != before:
                        result.new_entities.append(entity)
            elif page_state != "no_page":
                entity = self._planned_entity(
                    node["entity_type"],
                    decision["preferred_title"],
                    planned.values(),
                    now,
                    aliases=decision["aliases"],
                    materialization_state=page_state,
                )
                planned[entity.entity_id] = entity
                result.new_entities.append(entity)
            if entity is not None:
                candidate_entities[node_id] = entity
                candidate_support[entity.entity_id] = support
            supporting_claim_ids = [item.claim.claim_id for item in supporting]
            result.entity_decisions.append(EntityResolutionDecision(
                decision_id=f"identity-{uuid.uuid4().hex[:12]}",
                decision_type="entity_creation",
                entity_id=entity.entity_id if entity else None,
                proposed_entity_type=str(node["entity_type"]),
                proposed_title=str(decision["preferred_title"]),
                source_ids=[
                    *[item.source.source_id for item in supporting],
                    *[source.source_id for source, _, _ in participant_support],
                ],
                supporting_claim_ids=supporting_claim_ids,
                supporting_segment_ids=[
                    *[
                        segment_id
                        for item in supporting
                        for provenance in item.claim.provenance
                        for segment_id in provenance.segment_ids
                    ],
                    *[
                        segment.segment_id
                        for source, surface, _ in participant_support
                        for segment in source.segments
                        if str(segment.speaker or "").strip() == surface
                    ],
                ],
                confidence=confidence,
                reason=str(decision["reason"]),
                review_state="accepted" if accepted else "review_required",
                dream_run_id=dream_run_id,
                created_at=now,
            ))

        entity_sections = {
            entity.entity_id: section_keys(entity.entity_type)
            for entity in planned.values()
            if entity.status == "active"
        }
        resolved_plan = self.formatter.format_resolved_entity_plan(
            graph_nodes,
            entity_decisions,
            candidate_entities,
            planned,
            entity_plan["participants"],
        )
        routing_decisions: dict[str, dict] = {}
        for batch_aliases in self._alias_batches(aliases):
            batch_participants = self.resolution.participants_for_evidence(
                batch_aliases, participants
            )
            routing_model = claim_routing_output_model(
                batch_aliases,
                entity_sections,
            )
            system, user = prompts.claim_routing_prompt(
                self.formatter.entity_catalog(planned.values(), include_sections=True),
                resolved_plan,
                self.formatter.format_evidence(batch_aliases, batch_participants),
            )
            try:
                response = await self.llm.call_structured(
                    system,
                    user,
                    routing_model,
                    num_predict=8192,
                    debug_label="dream-claim-routing",
                )
                batch_decisions = routing_model.model_validate(
                    response
                ).model_dump()["decisions"]
                for alias, decision in batch_decisions.items():
                    owner_id = str(decision["owner_entity"])
                    section = str(decision["section"])
                    if not owner_id:
                        if section:
                            raise ValueError("Deferred claim selected a page section")
                        continue
                    if section and section not in entity_sections[owner_id]:
                        raise ValueError("Claim selected a section invalid for its owner")
                routing_decisions.update(batch_decisions)
            except Exception as exc:
                return self._fail_batch(
                    evidence,
                    "Claim routing response did not satisfy the contract: "
                    f"{type(exc).__name__}: {exc}",
                )

        for alias, decision in routing_decisions.items():
            owner_id = str(decision["owner_entity"] or "")
            if owner_id not in initially_provisional:
                continue
            prior_source_ids = {
                source_id
                for record in self.artifacts.list_entity_resolution_decisions(
                    entity_id=owner_id
                )
                for source_id in record.source_ids
            }
            if aliases[alias].source.source_id in prior_source_ids:
                continue
            entity = planned[owner_id]
            entity.materialization_state = "materialized"
            entity.updated_at = datetime.now().astimezone().isoformat()
            if all(
                changed.entity_id != entity.entity_id
                for changed in result.new_entities
            ):
                result.new_entities.append(entity)

        result.encounters = self.resolution.participant_encounters(
            participants,
            graph_plan["participants"],
            planned,
            candidate_entities,
        )
        result.entity_decisions.extend(self.resolution.participant_decisions(
            participants,
            graph_plan["participants"],
            planned,
            candidate_entities,
            dream_run_id,
            now,
        ))

        for alias, item in aliases.items():
            routing = routing_decisions[alias]
            decision = {
                "disposition": (
                    "canonical" if routing["owner_entity"] else "deferred"
                ),
                "owner_entity": routing["owner_entity"],
                "section": routing["section"],
                "linked_entities": [],
                "subject_entity": routing["subject_entity"],
                "object_entities": routing["object_entities"],
                "contextual_entities": routing["contextual_entities"],
                "relationship_kind": routing["relationship_kind"],
                "supporting_claims": [],
                "confidence": routing["confidence"],
                "reason": routing["reason"],
            }
            result.routes.append(self._route_decision(
                alias,
                item,
                decision,
                aliases,
                planned,
                candidate_entities,
                candidate_support,
            ))
        owned_entity_ids = {
            str(route.owner_entity_id)
            for route in result.routes
            if route.placed and route.owner_entity_id
        }
        encountered_entity_ids = {
            encounter.entity_id for encounter in result.encounters
        }
        for entity in candidate_entities.values():
            if (
                entity.materialization_state == "materialized"
                and entity.entity_id not in initially_materialized
                and entity.entity_id not in owned_entity_ids
                and entity.entity_id not in encountered_entity_ids
            ):
                entity.materialization_state = "provisional"
        result.entity_references = self.resolution.claim_entity_references(
            aliases,
            result.routes,
            planned,
            dream_run_id,
            now,
        )
        return result

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
        if disposition != "canonical":
            return ClaimRoute(
                item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                str(decision["reason"]), disposition, supporting_ids,
                float(decision["confidence"]),
            )
        owner_ref = str(decision["owner_entity"])
        owner = candidates.get(owner_ref) or entities.get(owner_ref)
        if (
            owner is None
            or owner.status != "active"
            or owner.materialization_state != "materialized"
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
        linked = set()
        resolved_references: dict[str, str] = {}
        for value in dict.fromkeys([
            *link_refs,
            *([subject_ref] if subject_ref else []),
            *object_refs,
            *contextual_refs,
        ]):
            linked_entity = candidates.get(value) or entities.get(value)
            if (
                linked_entity is None
                or linked_entity.status != "active"
                or linked_entity.materialization_state != "materialized"
            ):
                return ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    f"Proposed linked entity {value!r} was not admitted or active. "
                    f"{decision['reason']}",
                    "deferred", supporting_ids, float(decision["confidence"]),
                )
            resolved_references[value] = linked_entity.entity_id
        linked.update(resolved_references.values())
        linked.discard(owner.entity_id)
        link_entities = [entities[value] for value in linked if value in entities]
        relationship_kind = str(decision.get("relationship_kind") or "none")
        if relationship_kind == "project_role" and not self._valid_project_role_route(
            owner, link_entities
        ):
            return ClaimRoute(
                item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                "Project-role placement requires a Person or You owner and exactly one linked Project.",
                "deferred", supporting_ids, float(decision["confidence"]),
            )
        section = str(decision["section"])
        if item.claim.evidence_modality == "tool":
            if owner.entity_type == "you":
                return ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    "External evidence cannot automatically establish a personal fact on You.",
                    "deferred", supporting_ids, float(decision["confidence"]),
                )
        return ClaimRoute(
            item.claim.claim_id, owner.entity_id, section, tuple(sorted(linked)),
            item.raw_log_entry_id, str(decision["reason"]), "canonical",
            supporting_ids, float(decision["confidence"]),
            resolved_references.get(subject_ref) if subject_ref else None,
            tuple(sorted({resolved_references[value] for value in object_refs})),
            tuple(sorted({
                resolved_references[value] for value in contextual_refs
            })),
            None if relationship_kind == "none" else relationship_kind,
        )

    @staticmethod
    def _alias_batches(
        aliases: dict[str, ClaimEvidence], size: int = 24
    ) -> Iterable[dict[str, ClaimEvidence]]:
        """Bound unusually large routing responses without splitting ordinary cohorts."""
        items = list(aliases.items())
        for start in range(0, len(items), size):
            yield dict(items[start:start + size])

    @staticmethod
    def _user_evidence(item: ClaimEvidence) -> bool:
        wanted = {
            segment_id
            for provenance in item.claim.provenance
            for segment_id in provenance.segment_ids
        }
        return any(
            segment.segment_id in wanted
            and str(segment.role or segment.speaker or "").strip().lower() == "user"
            for segment in item.source.segments
        )

    @staticmethod
    def _valid_project_role_route(
        owner: EntityRecord, links: Iterable[EntityRecord]
    ) -> bool:
        links = list(links)
        return (
            owner.entity_type in {"you", "person"}
            and sum(entity.entity_type == "project" for entity in links) == 1
        )

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
        section_key=route.section_key,
        linked_entity_ids=list(route.linked_entity_ids),
        status="placed" if route.placed else "deferred",
        reason=route.reason,
        created_at=timestamp,
        updated_at=timestamp,
        relationship_kind=route.relationship_kind,
    )
