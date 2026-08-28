"""Semantic entity ownership planning for deterministic wiki consolidation."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from mycelium import prompts
from mycelium.artifacts import (
    ArtifactStore,
    ClaimEntityReference,
    ClaimPlacement,
    EntityEncounter,
    EntityRecord,
    EntityResolutionDecision,
    MemoryClaim,
    SourceDocument,
)
from mycelium.models import PAGE_SECTION_KEYS, PAGE_TYPES
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import (
    claim_owner_output_model,
    claim_reference_output_model,
    graph_admission_output_model,
    identity_resolution_output_model,
    identity_verification_output_model,
    subject_graph_output_model,
)
from mycelium.wiki_schema import default_section, is_project_role


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


@dataclass(frozen=True)
class ClaimEvidence:
    claim: MemoryClaim
    source: SourceDocument

    @property
    def raw_log_entry_id(self) -> str:
        return self.source.raw_log_entry_id or self.source.source_id


@dataclass(frozen=True)
class ClaimRoute:
    claim_id: str
    owner_entity_id: str | None
    section_key: str | None
    linked_entity_ids: tuple[str, ...]
    raw_log_entry_id: str
    reason: str
    disposition: str = "canonical"
    supporting_claim_ids: tuple[str, ...] = ()
    confidence: float = 0.8
    subject_entity_id: str | None = None
    object_entity_ids: tuple[str, ...] = ()
    contextual_entity_ids: tuple[str, ...] = ()

    @property
    def placed(self) -> bool:
        return self.disposition == "canonical" and bool(
            self.owner_entity_id and self.section_key
        )


@dataclass(frozen=True)
class RoutingFailure:
    claim_id: str
    raw_log_entry_id: str
    reason: str


@dataclass
class RoutingResult:
    routes: list[ClaimRoute] = field(default_factory=list)
    new_entities: list[EntityRecord] = field(default_factory=list)
    failures: list[RoutingFailure] = field(default_factory=list)
    encounters: list[EntityEncounter] = field(default_factory=list)
    entity_decisions: list[EntityResolutionDecision] = field(default_factory=list)
    entity_references: list[ClaimEntityReference] = field(default_factory=list)


class ClaimRouter:
    """Plan one validated entity owner for every admitted claim."""

    def __init__(self, llm: OllamaClient, artifacts: ArtifactStore):
        self.llm = llm
        self.artifacts = artifacts

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
        if not evidence:
            return result
        aliases = {f"C{index:03d}": item for index, item in enumerate(evidence, start=1)}
        participants = self._participant_occurrences(
            evidence, source_ids=participant_source_ids
        )
        graph_model = subject_graph_output_model(
            {alias: role for alias, (_, _, role) in participants.items()},
            evidence_aliases=(*aliases, *participants),
            existing_entity_types={
                entity.entity_id: entity.entity_type
                for entity in planned.values()
                if entity.status == "active"
            },
        )
        system, user = prompts.subject_graph_prompt(
            self._entity_catalog(planned.values()),
            self._format_evidence(aliases, participants),
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                graph_model,
                num_predict=8192,
                debug_label="dream-subject-graph",
            )
            graph_plan = graph_model.model_validate(response).model_dump()
            allowed_aliases = set(aliases)
            allowed_evidence = {*allowed_aliases, *participants}
            if any(
                set(node["supporting_evidence"]) - allowed_evidence
                for node in graph_plan["nodes"]
            ) or any(
                set(edge["supporting_evidence"]) - allowed_evidence
                for edge in graph_plan["edges"]
            ):
                raise ValueError("Subject graph cited an unknown evidence alias")
            graph_nodes = {
                node["node_id"]: node for node in graph_plan["nodes"]
            }
            if len(graph_nodes) != len(graph_plan["nodes"]):
                raise ValueError("Subject graph repeated a node ID")
            if set(graph_plan["participants"]) != set(participants):
                raise ValueError("Subject graph did not resolve exact participants")
            for resolution in graph_plan["participants"].values():
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
            allowed_endpoints = {
                *graph_nodes,
                *(
                    entity.entity_id
                    for entity in planned.values()
                    if entity.status == "active"
                ),
            }
            if any(
                edge["source_node"] not in allowed_endpoints
                or edge["target_node"] not in allowed_endpoints
                for edge in graph_plan["edges"]
            ):
                raise ValueError("Subject graph edge used an undeclared endpoint")
        except Exception as exc:
            return self._fail_batch(
                evidence,
                "Subject graph response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        registry_types = {
            entity.entity_id: entity.entity_type
            for entity in planned.values()
            if entity.status == "active"
        }
        resolution_model = identity_resolution_output_model(
            {
                node_id: str(node["entity_type"])
                for node_id, node in graph_nodes.items()
            },
            registry_types,
        )
        graph_summary = self._format_subject_graph(
            graph_nodes, graph_plan["edges"]
        )
        system, user = prompts.graph_identity_resolution_prompt(
            self._entity_catalog(planned.values()),
            graph_summary,
            self._format_evidence(aliases, participants),
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                resolution_model,
                num_predict=4096,
                debug_label="dream-graph-identity-resolution",
            )
            identity_resolutions = resolution_model.model_validate(
                response
            ).model_dump()["resolutions"]
            if set(identity_resolutions) != set(graph_nodes):
                raise ValueError("Identity resolution did not cover exact graph nodes")
            for node_id, decision in identity_resolutions.items():
                entity_id = str(decision["entity_id"])
                if entity_id:
                    entity = planned.get(entity_id)
                    if (
                        entity is None
                        or entity_id not in registry_types
                        or (
                            entity.entity_type != graph_nodes[node_id]["entity_type"]
                            and not (
                                graph_nodes[node_id]["entity_type"] == "person"
                                and entity.entity_type == "you"
                            )
                        )
                    ):
                        raise ValueError(
                            "Existing identity resolution used an invalid same-type ID"
                        )
        except Exception as exc:
            return self._fail_batch(
                evidence,
                "Identity resolution response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        proposed_matches = {
            node_id: str(decision["entity_id"])
            for node_id, decision in identity_resolutions.items()
            if decision["entity_id"]
        }
        if proposed_matches:
            verification_model = identity_verification_output_model(
                proposed_matches
            )
            match_summary = "\n".join(
                f"- {node_id}: candidate_type="
                f"{graph_nodes[node_id]['entity_type']}; "
                f"candidate_title={graph_nodes[node_id]['title']!r}; "
                f"existing_id={entity_id}; "
                f"existing_title={planned[entity_id].title!r}; "
                f"existing_aliases={','.join(planned[entity_id].aliases) or 'none'}; "
                f"supporting_evidence="
                f"{','.join(graph_nodes[node_id]['supporting_evidence'])}"
                for node_id, entity_id in proposed_matches.items()
            )
            system, user = prompts.identity_verification_prompt(
                match_summary,
                self._format_evidence(aliases, participants),
            )
            try:
                response = await self.llm.call_structured(
                    system,
                    user,
                    verification_model,
                    num_predict=4096,
                    debug_label="dream-identity-verification",
                )
                verifications = verification_model.model_validate(
                    response
                ).model_dump()["verifications"]
            except Exception as exc:
                return self._fail_batch(
                    evidence,
                    "Identity verification response did not satisfy the contract: "
                    f"{type(exc).__name__}: {exc}",
                )
            for node_id, verification in verifications.items():
                decision = identity_resolutions[node_id]
                if not verification["same_identity"]:
                    node = graph_nodes[node_id]
                    decision["entity_id"] = ""
                    decision["preferred_title"] = node["title"]
                    decision["aliases"] = []
                    decision["reason"] = verification["reason"]
                else:
                    decision["reason"] = (
                        f"{decision['reason']} Verified match: "
                        f"{verification['reason']}"
                    )

        contained_nodes = {
            str(edge["source_node"])
            for edge in graph_plan["edges"]
            if edge["relation"] in {"component_of", "occurrence_of"}
            and edge["source_node"] in graph_nodes
        }
        admission_model = graph_admission_output_model(
            tuple(graph_nodes),
            contained_node_ids=contained_nodes,
        )
        resolved_graph = self._format_subject_graph(
            graph_nodes,
            graph_plan["edges"],
            resolutions=identity_resolutions,
        )
        system, user = prompts.graph_admission_prompt(
            self._entity_catalog(planned.values()),
            resolved_graph,
            self._format_evidence(aliases, participants),
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                admission_model,
                num_predict=4096,
                debug_label="dream-graph-admission",
            )
            admissions = admission_model.model_validate(response).model_dump()[
                "admissions"
            ]
            if set(admissions) != set(graph_nodes):
                raise ValueError("Admission did not cover exact graph nodes")
        except Exception as exc:
            return self._fail_batch(
                evidence,
                "Graph admission response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        candidate_entities: dict[str, EntityRecord] = {}
        candidate_support: dict[str, tuple[str, ...]] = {}
        now = datetime.now().astimezone().isoformat()
        for node_id, node in graph_nodes.items():
            decision = identity_resolutions[node_id]
            admission = admissions[node_id]
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
            if admission["scope_role"] == "independent":
                page_state = (
                    "materialized"
                    if (
                        admission["memory_evidence"] == "accumulating"
                        and admission["evidence_maturity"] == "established"
                    )
                    else "provisional"
                )
            else:
                page_state = "no_page"
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
                reason=f"{decision['reason']} Admission: {admission['reason']}",
                review_state="accepted" if accepted else "review_required",
                dream_run_id=dream_run_id,
                created_at=now,
            ))

        registry_ids = tuple(
            entity.entity_id for entity in planned.values()
            if entity.status == "active"
        )
        resolved_graph = self._format_subject_graph(
            graph_nodes,
            graph_plan["edges"],
            resolutions=identity_resolutions,
            admissions=admissions,
            entities=candidate_entities,
        )
        routed_evidence = (
            f"{self._format_evidence(aliases, participants)}\n\n"
            f"[RESOLVED SUBJECT GRAPH]\n{resolved_graph}"
        )
        owner_model = claim_owner_output_model(aliases, registry_ids)
        system, user = prompts.claim_owner_prompt(
            self._entity_catalog(planned.values()),
            routed_evidence,
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                owner_model,
                num_predict=4096,
                debug_label="dream-claim-owner",
            )
            owner_plan = owner_model.model_validate(response).model_dump()
        except Exception as exc:
            return self._fail_batch(
                evidence,
                "Claim owner response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        reference_model = claim_reference_output_model(aliases, registry_ids)
        fixed_owners = "\n".join(
            f"- {alias}: fixed_owner={decision['owner_entity'] or 'deferred'}"
            for alias, decision in owner_plan["assignments"].items()
        )
        system, user = prompts.claim_reference_prompt(
            self._entity_catalog(planned.values()),
            f"{routed_evidence}\n\n"
            f"[FIXED CLAIM OWNERS]\n{fixed_owners}",
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                reference_model,
                num_predict=4096,
                debug_label="dream-claim-references",
            )
            reference_plan = reference_model.model_validate(response).model_dump()
        except Exception as exc:
            return self._fail_batch(
                evidence,
                "Claim reference response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        result.encounters = self._participant_encounters(
            participants,
            graph_plan["participants"],
            planned,
            candidate_entities,
        )
        result.entity_decisions.extend(self._participant_decisions(
            participants,
            graph_plan["participants"],
            planned,
            candidate_entities,
            dream_run_id,
            now,
        ))

        for alias, item in aliases.items():
            owner = owner_plan["assignments"][alias]
            references = reference_plan["references"][alias]
            decision = {
                "disposition": "canonical" if owner["owner_entity"] else "deferred",
                "owner_entity": owner["owner_entity"],
                "linked_entities": [],
                "subject_entity": references["subject_entity"],
                "object_entities": references["object_entities"],
                "contextual_entities": references["contextual_entities"],
                "supporting_claims": [],
                "confidence": owner["confidence"],
                "reason": owner["reason"],
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
        result.entity_references = self._claim_entity_references(
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
        if is_project_role(item.claim) and not self._valid_project_role_route(
            owner, link_entities
        ):
            return ClaimRoute(
                item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                "Project-role placement requires a Person or You owner and exactly one linked Project.",
                "deferred", supporting_ids, float(decision["confidence"]),
            )
        section = default_section(owner.entity_type, item.claim)
        if item.claim.evidence_modality == "tool":
            if owner.entity_type == "you":
                return ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    "External evidence cannot automatically establish a personal fact on You.",
                    "deferred", supporting_ids, float(decision["confidence"]),
                )
            section = "evidence" if owner.entity_type == "event" else "research_references"
        return ClaimRoute(
            item.claim.claim_id, owner.entity_id, section, tuple(sorted(linked)),
            item.raw_log_entry_id, str(decision["reason"]), "canonical",
            supporting_ids, float(decision["confidence"]),
            resolved_references.get(subject_ref) if subject_ref else None,
            tuple(sorted({resolved_references[value] for value in object_refs})),
            tuple(sorted({
                resolved_references[value] for value in contextual_refs
            })),
        )

    @staticmethod
    def _participant_occurrences(
        evidence: list[ClaimEvidence],
        *,
        source_ids: set[str] | None = None,
    ) -> dict[str, tuple[SourceDocument, str, str | None]]:
        """Expose source-declared participant occurrences to the scope contract."""
        sources = {
            item.source.source_id: item.source
            for item in evidence
            if (source_ids is None or item.source.source_id in source_ids)
            if item.source.source_type
            in {"meeting_transcript", "multi_party_conversation"}
        }
        occurrences: list[tuple[SourceDocument, str, str | None]] = []
        for source in sources.values():
            speakers = dict.fromkeys(
                (
                    str(segment.speaker).strip(),
                    str(segment.role).strip().lower() if segment.role else None,
                )
                for segment in source.segments
                if str(segment.speaker or "").strip()
            )
            occurrences.extend(
                (source, name, role) for name, role in speakers
            )
        return {
            f"P{index:03d}": occurrence
            for index, occurrence in enumerate(occurrences, start=1)
        }

    @staticmethod
    def _participant_encounters(
        occurrences: dict[str, tuple[SourceDocument, str, str | None]],
        resolutions: dict[str, dict],
        entities: dict[str, EntityRecord],
        candidates: dict[str, EntityRecord],
    ) -> list[EntityEncounter]:
        created_at = datetime.now().astimezone().isoformat()
        encounters: dict[str, EntityEncounter] = {}
        for alias, (source, _, _) in occurrences.items():
            resolution = resolutions[alias]
            entity = candidates.get(resolution["entity"]) or entities.get(
                resolution["entity"]
            )
            if entity is None or entity.entity_type != "person":
                continue
            title = str(source.metadata.get("title") or "").strip() or None
            encounter_id = f"encounter-{entity.entity_id}-{source.source_id}"
            encounters[encounter_id] = EntityEncounter(
                encounter_id=encounter_id,
                entity_id=entity.entity_id,
                source_id=source.source_id,
                raw_log_entry_id=source.raw_log_entry_id,
                occurred_at=source.occurred_at,
                title=title,
                created_at=created_at,
            )
        return sorted(encounters.values(), key=lambda item: item.encounter_id)

    @staticmethod
    def _participant_decisions(
        occurrences: dict[str, tuple[SourceDocument, str, str | None]],
        resolutions: dict[str, dict],
        entities: dict[str, EntityRecord],
        candidates: dict[str, EntityRecord],
        dream_run_id: str,
        created_at: str,
    ) -> list[EntityResolutionDecision]:
        decisions = []
        for alias, (source, surface, _) in occurrences.items():
            resolution = resolutions[alias]
            entity = candidates.get(resolution["entity"]) or entities.get(
                resolution["entity"]
            )
            confidence = float(resolution["confidence"])
            if entity is None:
                decisions.append(EntityResolutionDecision(
                    decision_id=f"identity-{uuid.uuid4().hex[:12]}",
                    decision_type="participant_resolution",
                    entity_id=None,
                    proposed_entity_type="person",
                    proposed_title=surface,
                    source_ids=[source.source_id],
                    supporting_claim_ids=[],
                    supporting_segment_ids=[
                        segment.segment_id
                        for segment in source.segments
                        if str(segment.speaker or "").strip() == surface
                    ],
                    confidence=confidence,
                    reason=(
                        "Review required because the model referenced an undeclared "
                        f"participant entity {resolution['entity']!r}. "
                        f"{resolution['reason']}"
                    ),
                    review_state="review_required",
                    dream_run_id=dream_run_id,
                    created_at=created_at,
                    participant_surface=surface,
                ))
                continue
            decisions.append(EntityResolutionDecision(
                decision_id=f"identity-{uuid.uuid4().hex[:12]}",
                decision_type="participant_resolution",
                entity_id=entity.entity_id,
                proposed_entity_type=entity.entity_type,
                proposed_title=entity.title,
                source_ids=[source.source_id],
                supporting_claim_ids=[],
                supporting_segment_ids=[
                    segment.segment_id
                    for segment in source.segments
                    if str(segment.speaker or "").strip() == surface
                ],
                confidence=confidence,
                reason=str(resolution["reason"]),
                review_state=("accepted" if confidence >= 0.7 else "review_required"),
                dream_run_id=dream_run_id,
                created_at=created_at,
                participant_surface=surface,
            ))
        return decisions

    @staticmethod
    def _claim_entity_references(
        aliases: dict[str, ClaimEvidence],
        routes: list[ClaimRoute],
        entities: dict[str, EntityRecord],
        dream_run_id: str,
        created_at: str,
    ) -> list[ClaimEntityReference]:
        """Preserve extracted surfaces and add stable scope endpoints without string matching."""
        routes_by_claim = {route.claim_id: route for route in routes}
        references: list[ClaimEntityReference] = []
        for item in aliases.values():
            claim = item.claim
            for mention in claim.about:
                surface = " ".join(str(mention.get("entity") or "").split()).strip()
                if not surface:
                    continue
                extracted_role = str(mention.get("role") or "").strip().lower()
                if extracted_role in {"subject", "speaker", "owner", "actor"}:
                    role = "subject"
                elif extracted_role in {"object", "value", "target", "recipient"}:
                    role = "object"
                else:
                    role = "context"
                references.append(ClaimEntityReference(
                    reference_id=f"ref-{uuid.uuid4().hex[:12]}",
                    claim_id=claim.claim_id,
                    role=role,
                    surface=surface,
                    entity_id=None,
                    confidence=claim.confidence,
                    reason="Surface mention preserved from structured claim extraction.",
                    origin="extraction",
                    dream_run_id=dream_run_id,
                    status="active",
                    created_at=created_at,
                ))
            route = routes_by_claim[claim.claim_id]
            if route.owner_entity_id:
                references.append(ClaimEntityReference(
                    reference_id=f"ref-{uuid.uuid4().hex[:12]}",
                    claim_id=claim.claim_id,
                    role="canonical_owner",
                    surface=None,
                    entity_id=route.owner_entity_id,
                    confidence=route.confidence,
                    reason=route.reason,
                    origin="scope",
                    dream_run_id=dream_run_id,
                    status="active",
                    created_at=created_at,
                ))
            stable_roles = [
                *([("subject", route.subject_entity_id)] if route.subject_entity_id else []),
                *(("object", entity_id) for entity_id in route.object_entity_ids),
                *(("context", entity_id) for entity_id in route.contextual_entity_ids),
            ]
            explicitly_typed_ids = {entity_id for _, entity_id in stable_roles}
            stable_roles.extend(
                ("context", entity_id)
                for entity_id in route.linked_entity_ids
                if entity_id not in explicitly_typed_ids
            )
            for role, entity_id in stable_roles:
                entity = entities.get(entity_id)
                references.append(ClaimEntityReference(
                    reference_id=f"ref-{uuid.uuid4().hex[:12]}",
                    claim_id=claim.claim_id,
                    role=role,
                    surface=entity.title if entity else None,
                    entity_id=entity_id,
                    confidence=route.confidence,
                    reason="Stable semantic endpoint from the scope decision.",
                    origin="scope",
                    dream_run_id=dream_run_id,
                    status="active",
                    created_at=created_at,
                ))
        return references

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
    def _entity_catalog(entities: Iterable[EntityRecord]) -> str:
        lines = ["Typed section contract:"]
        for entity_type in PAGE_TYPES:
            sections = ", ".join(key for key, _ in PAGE_SECTION_KEYS[entity_type])
            lines.append(f"- type={entity_type}; allowed_sections={sections}")
        lines.extend(["", "Existing canonical entities:"])
        found = False
        for entity in sorted(entities, key=lambda item: item.entity_id):
            if entity.status != "active":
                continue
            found = True
            aliases = ", ".join(entity.aliases) or "none"
            lines.append(
                f"- id={entity.entity_id}; type={entity.entity_type}; title={entity.title!r}; "
                f"aliases={aliases}; page_state={entity.materialization_state}"
            )
        if not found:
            lines.append("- none yet")
        return "\n".join(lines)

    @staticmethod
    def _format_subject_graph(
        nodes: dict[str, dict],
        edges: list[dict],
        *,
        resolutions: dict[str, dict] | None = None,
        admissions: dict[str, dict] | None = None,
        entities: dict[str, EntityRecord] | None = None,
    ) -> str:
        """Render validated graph facts without adding semantic decisions."""
        lines = ["Nodes:"]
        for node_id, node in nodes.items():
            details = [
                f"type={node['entity_type']}",
                f"title={node['title']!r}",
                f"evidence={','.join(node['supporting_evidence'])}",
            ]
            if resolutions is not None:
                resolution = resolutions[node_id]
                details.extend([
                    f"resolved_id={resolution['entity_id'] or 'new'}",
                    f"preferred_title={resolution['preferred_title']!r}",
                ])
            if admissions is not None:
                admission = admissions[node_id]
                details.extend([
                    f"scope_role={admission['scope_role']}",
                    f"memory_evidence={admission['memory_evidence']}",
                    f"evidence_maturity={admission['evidence_maturity']}",
                ])
            if entities is not None:
                entity = entities.get(node_id)
                details.append(
                    f"stable_id={entity.entity_id if entity else 'no_page'}"
                )
            lines.append(f"- {node_id}: {'; '.join(details)}")
        lines.append("Edges:")
        lines.extend(
            f"- {edge['source_node']} -[{edge['relation']}]-> "
            f"{edge['target_node']}; evidence="
            f"{','.join(edge['supporting_evidence'])}"
            for edge in edges
        )
        if not edges:
            lines.append("- none")
        return "\n".join(lines)

    def _format_evidence(
        self,
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple[SourceDocument, str, str | None]],
    ) -> str:
        blocks = []
        for alias, item in aliases.items():
            claim = item.claim
            entities = ", ".join(
                f"{str(value.get('entity'))!r}[role={str(value.get('role') or 'unspecified')}]"
                for value in claim.about if value.get("entity")
            ) or "unknown"
            stable_references = ", ".join(
                f"{reference.role}:{reference.entity_id or 'unresolved'}"
                for reference in self.artifacts.list_entity_references(
                    claim_id=claim.claim_id, status="active"
                )
            ) or "none"
            facets = "; ".join(
                f"{key}={value}" for key, value in sorted(claim.facets.items())
                if value not in (None, "", [], {})
            )
            blocks.append(
                f"[EVIDENCE {alias}]\nclaim_type={claim.claim_type}; "
                f"extracted_entity_mentions={entities}; stable_entity_references={stable_references}; "
                f"temporal_status={claim.temporal_status}; source_id={item.source.source_id}; "
                f"source_type={item.source.source_type}; occurred_at={item.source.occurred_at or 'unknown'}; "
                f"participants={','.join(item.source.participants) or 'none'}; "
                f"evidence_modality={claim.evidence_modality}\nclaim={claim.text}\n"
                f"qualifiers={facets or 'none'}"
            )
        if participants:
            blocks.append("[SOURCE-DECLARED PARTICIPANTS]")
            blocks.extend(
                f"[{alias}] name={name!r}; source_id={source.source_id}; "
                f"speaker_role={role or 'participant'}; "
                f"occurred_at={source.occurred_at or 'unknown'}"
                for alias, (source, name, role) in participants.items()
            )
        return "\n\n".join(blocks)

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
    )
