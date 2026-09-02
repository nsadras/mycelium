"""Semantic entity ownership planning for deterministic wiki consolidation."""

from __future__ import annotations

import uuid
import hashlib
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
    IdentityWorkUnit,
    IdentityMaturityAssessment,
)
from mycelium.ollama import OllamaClient
from mycelium.ontology import subject_scope_definition
from mycelium.structured_outputs import (
    claim_routing_output_model,
    entity_plan_output_model,
    identity_node_matching_output_model,
    local_identity_matching_output_model,
    new_identity_verification_output_model,
    identity_maturity_output_model,
    identity_maturity_verification_output_model,
    identity_type_output_model,
    identity_type_verification_output_model,
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
        """Route bounded source cohorts so one malformed identity plan stays local."""
        result = RoutingResult()
        seeds = list(seed_entities)
        for unit_evidence in self._identity_units(evidence):
            unit = self._work_unit(unit_evidence, dream_run_id)
            partial = await self._route_unit(
                unit_evidence,
                dream_run_id=dream_run_id,
                seed_entities=seeds,
                participant_source_ids=participant_source_ids,
                work_unit=unit,
            )
            self._merge_result(result, partial)
            seeds.extend(partial.new_entities)
        return result

    async def _route_unit(
        self,
        evidence: list[ClaimEvidence],
        *,
        dream_run_id: str = "unpersisted",
        seed_entities: Iterable[EntityRecord] = (),
        participant_source_ids: set[str] | None = None,
        work_unit: IdentityWorkUnit,
    ) -> RoutingResult:
        result = RoutingResult()
        planned = {entity.entity_id: entity for entity in self.artifacts.list_entities()}
        planned.update({entity.entity_id: entity for entity in seed_entities})
        initially_materialized = {
            entity.entity_id
            for entity in planned.values()
            if entity.materialization_state == "materialized"
        }
        if not evidence:
            return result
        work_unit.attempt_count += 1
        work_unit.status = "pending"
        work_unit.last_error = None
        work_unit.updated_at = datetime.now().astimezone().isoformat()
        self.artifacts.save_identity_work_unit(work_unit)
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
        try:
            if work_unit.subject_nodes:
                node_plan = {"nodes": work_unit.subject_nodes}
            else:
                node_model = subject_node_output_model(allowed_evidence, participants)
                system, user = prompts.subject_node_prompt(
                    self.formatter.entity_catalog(
                        planned.values(), include_sections=False
                    ),
                    self.formatter.format_subject_candidates(
                        aliases, participants
                    ),
                    self.formatter.format_evidence(aliases, participants),
                )
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
            work_unit.subject_nodes = node_plan["nodes"]
            work_unit.stage = "identity_matching"
            self.artifacts.save_identity_work_unit(work_unit)
        except Exception as exc:
            return self._fail_work_unit(
                work_unit,
                evidence,
                "subject_nodes",
                "Subject node response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        census_nodes = graph_nodes
        reviewed_node_entities: dict[str, str] = {}
        for node_id, node in census_nodes.items():
            reviewed = {
                reference.entity_id
                for alias in node["supporting_evidence"]
                if alias in aliases
                for reference in self.artifacts.list_entity_references(
                    claim_id=aliases[alias].claim.claim_id, status="active"
                )
                if reference.role == "identity_subject"
                and reference.origin == "manual"
                and reference.entity_id
            }
            if len(reviewed) > 1:
                return self._fail_work_unit(
                    work_unit,
                    evidence,
                    "identity_matching",
                    "Reviewed claim identities conflict within one subject node",
                )
            if reviewed:
                reviewed_node_entities[node_id] = next(iter(reviewed))

        match_groups: list[dict] = []
        if census_nodes:
            try:
                node_decisions = dict(work_unit.identity_node_decisions)
                local_decisions = dict(work_unit.local_identity_decisions)
                match_groups = []
                for node_id, node in census_nodes.items():
                    match_model = identity_node_matching_output_model(
                        node_id,
                        [
                            entity_id for entity_id in registry_types
                            if entity_id != "you"
                        ],
                    )
                    supporting = set(node["supporting_evidence"])
                    node_aliases = {
                        alias: item for alias, item in aliases.items()
                        if alias in supporting
                    }
                    node_participants = {
                        alias: item for alias, item in participants.items()
                        if alias in supporting
                    }
                    node_text = self.formatter.format_subject_graph(
                        {node_id: node}, []
                    )
                    evidence_text = self.formatter.format_evidence(
                        node_aliases, node_participants
                    )
                    if node_id in node_decisions:
                        decision = match_model.model_validate({
                            "decision": node_decisions[node_id]
                        }).model_dump()["decision"]
                    else:
                        system, user = prompts.identity_node_matching_prompt(
                            self.formatter.entity_planning_catalog(planned.values()),
                            node_text,
                            evidence_text,
                            self.formatter.identity_review_catalog(node_aliases),
                        )
                        response = await self.llm.call_structured(
                            system,
                            user,
                            match_model,
                            num_predict=2048,
                            debug_label=f"dream-identity-matching-{node_id}",
                        )
                        decision = match_model.model_validate(response).model_dump()[
                            "decision"
                        ]
                        node_decisions[node_id] = decision
                        work_unit.identity_node_decisions = node_decisions
                        work_unit.updated_at = datetime.now().astimezone().isoformat()
                        self.artifacts.save_identity_work_unit(work_unit)
                    local_groups = [
                        group for group in match_groups
                        if group["resolution"] == "new"
                    ]
                    if decision["resolution"] == "new" and local_groups:
                        local_model = local_identity_matching_output_model(
                            node_id,
                            [group["identity_key"] for group in local_groups],
                        )
                        if node_id in local_decisions:
                            local_decision = local_model.model_validate({
                                "decision": local_decisions[node_id]
                            }).model_dump()["decision"]
                        else:
                            system, user = prompts.local_identity_matching_prompt(
                                node_text,
                                evidence_text,
                                self.formatter.format_accumulated_identity_groups(
                                    local_groups
                                ),
                            )
                            response = await self.llm.call_structured(
                                system,
                                user,
                                local_model,
                                num_predict=1024,
                                debug_label=(
                                    f"dream-local-identity-matching-{node_id}"
                                ),
                            )
                            local_decision = local_model.model_validate(
                                response
                            ).model_dump()["decision"]
                            local_decisions[node_id] = local_decision
                            work_unit.local_identity_decisions = local_decisions
                            work_unit.updated_at = (
                                datetime.now().astimezone().isoformat()
                            )
                            self.artifacts.save_identity_work_unit(work_unit)
                        if local_decision["resolution"] == "same_as_local":
                            decision = {
                                **decision,
                                "resolution": "same_as_local",
                                "local_identity_key": local_decision[
                                    "local_identity_key"
                                ],
                            }
                    match_groups = self._accumulate_identity_decision(
                        match_groups, decision
                    )
                    work_unit.identity_groups = match_groups
                    work_unit.updated_at = datetime.now().astimezone().isoformat()
                    self.artifacts.save_identity_work_unit(work_unit)
                for group in match_groups:
                    reviewed = {
                        reviewed_node_entities[node_id]
                        for node_id in group["node_ids"]
                        if node_id in reviewed_node_entities
                    }
                    if len(reviewed) > 1:
                        raise ValueError(
                            "One identity group contains conflicting reviewed identities"
                        )
                    if reviewed and (
                        group["resolution"] != "existing"
                        or group["entity_id"] != next(iter(reviewed))
                    ):
                        raise ValueError(
                            "Identity matching conflicts with a reviewed identity"
                        )
                work_unit.identity_groups = match_groups
                work_unit.stage = "identity_types"
                self.artifacts.save_identity_work_unit(work_unit)
            except Exception as exc:
                return self._fail_work_unit(
                    work_unit,
                    evidence,
                    "identity_matching",
                    "Identity matching response did not satisfy the contract: "
                    f"{type(exc).__name__}: {exc}",
                )

        graph_nodes = {}
        for group in match_groups:
            member_nodes = [census_nodes[node_id] for node_id in group["node_ids"]]
            graph_nodes[group["identity_key"]] = {
                "node_id": group["identity_key"],
                "source_node_ids": list(group["node_ids"]),
                "title": group["preferred_title"],
                "aliases": list(group["aliases"]),
                "identity_resolution": group["resolution"],
                "entity_id": group["entity_id"],
                "identity_reason": group["reason"],
                "candidate_entity_ids": list(group["candidate_entity_ids"]),
                "supporting_evidence": list(dict.fromkeys(
                    alias
                    for node in member_nodes
                    for alias in node["supporting_evidence"]
                )),
                "participant_evidence": list(dict.fromkeys(
                    alias
                    for node in member_nodes
                    for alias in node["participant_evidence"]
                )),
            }

        rejected_existing_ids: dict[str, str] = {}
        try:
            for identity_key, node in graph_nodes.items():
                if node["identity_resolution"] != "existing":
                    continue
                proposed_entity_id = str(node["entity_id"])
                if identity_key in work_unit.existing_identity_verdicts:
                    identity_verdict = work_unit.existing_identity_verdicts[
                        identity_key
                    ]
                else:
                    identity_verdict = await self._verify_identity(
                        node,
                        [planned[proposed_entity_id]],
                        aliases,
                        participants,
                    )
                    work_unit.existing_identity_verdicts[
                        identity_key
                    ] = identity_verdict
                    work_unit.stage = "existing_identity_verification"
                    self.artifacts.save_identity_work_unit(work_unit)
                if (
                    identity_verdict["verdict"] == "existing"
                    and identity_verdict["entity_id"] == proposed_entity_id
                ):
                    node["identity_reason"] = identity_verdict["reason"]
                    continue
                node["entity_id"] = ""
                node["identity_reason"] = identity_verdict["reason"]
                if identity_verdict["verdict"] == "review_required":
                    node["identity_resolution"] = "review_required"
                    node["candidate_entity_ids"] = identity_verdict[
                        "candidate_entity_ids"
                    ]
                else:
                    node["identity_resolution"] = "new"
                    node["candidate_entity_ids"] = []
                    rejected_existing_ids[identity_key] = proposed_entity_id
        except Exception as exc:
            return self._fail_work_unit(
                work_unit,
                evidence,
                "existing_identity_verification",
                "Existing identity verification did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        unresolved_type_evidence = {
            identity_key: node["supporting_evidence"]
            for identity_key, node in graph_nodes.items()
            if node["identity_resolution"] != "existing"
        }
        type_proposals: dict[str, dict] = {}
        type_verdicts: dict[str, dict] = {}
        if unresolved_type_evidence:
            try:
                if work_unit.type_proposals:
                    type_proposals = work_unit.type_proposals
                else:
                    type_model = identity_type_output_model(unresolved_type_evidence)
                    system, user = prompts.identity_types_prompt(
                        self.formatter.format_identity_groups(graph_nodes),
                        self.formatter.format_evidence(aliases, participants),
                    )
                    response = await self.llm.call_structured(
                        system,
                        user,
                        type_model,
                        num_predict=4096,
                        debug_label="dream-identity-types",
                    )
                    type_proposals = type_model.model_validate(response).model_dump()[
                        "decisions"
                    ]
                work_unit.type_proposals = type_proposals
                work_unit.stage = "identity_type_verification"
                self.artifacts.save_identity_work_unit(work_unit)
            except Exception as exc:
                return self._fail_work_unit(
                    work_unit,
                    evidence,
                    "identity_types",
                    "Identity type response did not satisfy the contract: "
                    f"{type(exc).__name__}: {exc}",
                )
            type_verification_model = identity_type_verification_output_model(
                {
                    identity_key: proposal["entity_type"]
                    for identity_key, proposal in type_proposals.items()
                },
                unresolved_type_evidence,
            )
            system, user = prompts.identity_type_verification_prompt(
                self.formatter.format_type_proposals(type_proposals),
                self.formatter.format_identity_groups(graph_nodes),
                self.formatter.format_evidence(aliases, participants),
            )
            try:
                if work_unit.type_verdicts:
                    type_verdicts = work_unit.type_verdicts
                else:
                    response = await self.llm.call_structured(
                        system,
                        user,
                        type_verification_model,
                        num_predict=4096,
                        debug_label="dream-identity-type-verification",
                    )
                    type_verdicts = type_verification_model.model_validate(
                        response
                    ).model_dump()["decisions"]
                work_unit.type_verdicts = type_verdicts
                work_unit.stage = "identity_maturity"
                self.artifacts.save_identity_work_unit(work_unit)
            except Exception as exc:
                return self._fail_work_unit(
                    work_unit,
                    evidence,
                    "identity_type_verification",
                    "Identity type verification did not satisfy the contract: "
                    f"{type(exc).__name__}: {exc}",
                )

        for identity_key, node in graph_nodes.items():
            if node["identity_resolution"] == "existing":
                node["entity_type"] = registry_types[node["entity_id"]]
                node["type_adjudication"] = "accepted"
                node["type_reason"] = "The canonical entity supplies its fixed type."
                continue
            proposal = type_proposals[identity_key]
            verdict = type_verdicts[identity_key]
            node["entity_type"] = proposal["entity_type"]
            node["type_adjudication"] = (
                "accepted"
                if verdict["verdict"] == "supported"
                and node["identity_resolution"] != "review_required"
                else "review_required"
            )
            node["type_reason"] = verdict["reason"]

        try:
            for identity_key, node in graph_nodes.items():
                if (
                    node["identity_resolution"] != "new"
                    or node["type_adjudication"] != "accepted"
                ):
                    continue
                if identity_key in work_unit.new_identity_verdicts:
                    identity_verdict = work_unit.new_identity_verdicts[identity_key]
                else:
                    candidates = [
                        entity for entity in planned.values()
                        if entity.status == "active"
                        and entity.entity_id != "you"
                        and entity.entity_type == node["entity_type"]
                        and entity.entity_id != rejected_existing_ids.get(identity_key)
                    ]
                    identity_verdict = await self._verify_identity(
                        node,
                        candidates,
                        aliases,
                        participants,
                    )
                    work_unit.new_identity_verdicts[identity_key] = identity_verdict
                    work_unit.stage = "new_identity_verification"
                    self.artifacts.save_identity_work_unit(work_unit)
                if identity_verdict["verdict"] == "existing":
                    node["identity_resolution"] = "existing"
                    node["entity_id"] = identity_verdict["entity_id"]
                    node["candidate_entity_ids"] = []
                elif identity_verdict["verdict"] == "review_required":
                    node["identity_resolution"] = "review_required"
                    node["entity_id"] = ""
                    node["candidate_entity_ids"] = identity_verdict[
                        "candidate_entity_ids"
                    ]
                    node["type_adjudication"] = "review_required"
                node["identity_reason"] = identity_verdict["reason"]
        except Exception as exc:
            return self._fail_work_unit(
                work_unit,
                evidence,
                "new_identity_verification",
                "New identity verification did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        node_types = {
            node_id: str(node["entity_type"])
            for node_id, node in graph_nodes.items()
        }
        multi_episode_nodes = {
            node_id
            for node_id, node in graph_nodes.items()
            if len({
                aliases[alias].source.source_id
                for alias in node["supporting_evidence"]
                if alias in aliases
            }) > 1
        }
        direct_encounter_nodes = {
            node_id
            for node_id, node in graph_nodes.items()
            if node["entity_type"] == "person" and node["participant_evidence"]
        }
        allowed_maturity_bases = {
            node_id: (
                ("multiple_episodes",)
                if node_id in multi_episode_nodes
                else (
                    ("direct_encounter",)
                    if node_id in direct_encounter_nodes
                    else ("explicit_prior_history",)
                )
            )
            for node_id in graph_nodes
        }
        maturity_model = identity_maturity_output_model(
            allowed_maturity_bases, aliases
        )
        system, user = prompts.identity_maturity_prompt(
            self.formatter.format_subject_graph(graph_nodes, []),
            self.formatter.format_evidence(aliases, participants),
        )
        try:
            if work_unit.maturity_decisions:
                maturity_decisions = work_unit.maturity_decisions
            else:
                response = await self.llm.call_structured(
                    system,
                    user,
                    maturity_model,
                    num_predict=4096,
                    debug_label="dream-identity-maturity",
                )
                maturity_decisions = maturity_model.model_validate(
                    response
                ).model_dump()["decisions"]
            work_unit.maturity_decisions = maturity_decisions
            work_unit.stage = "identity_maturity_verification"
            self.artifacts.save_identity_work_unit(work_unit)
        except Exception as exc:
            return self._fail_work_unit(
                work_unit,
                evidence,
                "identity_maturity",
                "Identity maturity response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )
        explicit_nodes = {
            node_id
            for node_id, decision in maturity_decisions.items()
            if decision["admission"] == "materialized"
            and decision["basis"]["continuity_basis"]
            == "explicit_prior_history"
        }
        verification_model = identity_maturity_verification_output_model(
            explicit_nodes, graph_nodes
        )
        system, user = prompts.identity_maturity_verification_prompt(
            self.formatter.format_maturity_decisions(maturity_decisions),
            self.formatter.format_evidence(aliases, participants),
        )
        try:
            if work_unit.maturity_verdicts:
                maturity_verdicts = work_unit.maturity_verdicts
            else:
                response = await self.llm.call_structured(
                    system,
                    user,
                    verification_model,
                    num_predict=4096,
                    debug_label="dream-identity-maturity-verification",
                )
                maturity_verdicts = verification_model.model_validate(
                    response
                ).model_dump()["decisions"]
            work_unit.maturity_verdicts = maturity_verdicts
            work_unit.stage = "entity_plan"
            self.artifacts.save_identity_work_unit(work_unit)
        except Exception as exc:
            return self._fail_work_unit(
                work_unit,
                evidence,
                "identity_maturity_verification",
                "Identity maturity verification did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )
        materialization_bases = {
            node_id: (str(decision["basis"]["continuity_basis"]),)
            for node_id, decision in maturity_decisions.items()
            if decision["admission"] == "materialized"
            and (
                node_id not in explicit_nodes
                or maturity_verdicts[node_id]["verdict"] == "supported"
            )
        }
        maturity_review_required_nodes = {
            node_id
            for node_id in explicit_nodes
            if node_types[node_id] in {"project", "series"}
            and maturity_verdicts[node_id]["verdict"] == "supported"
            and not any(
                entity.entity_type == node_types[node_id]
                and entity.materialization_state == "materialized"
                for entity in planned.values()
            )
        }
        try:
            matched_entity_ids = {
                node_id: node["entity_id"]
                for node_id, node in graph_nodes.items()
                if node["identity_resolution"] == "existing"
            }
            entity_model = entity_plan_output_model(
                node_types,
                {alias: role for alias, (_, _, role) in participants.items()},
                registry_types,
                matched_entity_ids,
                materialization_bases,
                {
                    node_id
                    for node_id, node in graph_nodes.items()
                    if node["type_adjudication"] == "review_required"
                } | maturity_review_required_nodes,
            )
            if work_unit.entity_plan:
                entity_plan = entity_model.model_validate(
                    work_unit.entity_plan
                ).model_dump()
            else:
                system, user = prompts.entity_plan_prompt(
                    self.formatter.entity_planning_catalog(planned.values()),
                    self.formatter.format_subject_graph(graph_nodes, []),
                    self.formatter.format_evidence(aliases, participants),
                    self.formatter.identity_review_catalog(aliases),
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
                if parent in graph_nodes:
                    parent_decision = entity_decisions[parent]
                    if (
                        parent_decision["adjudication"] != "accepted"
                        or parent_decision["scope"]
                        not in {"materialized", "provisional"}
                    ):
                        raise ValueError(
                            "A contained entity requires an accepted independent parent"
                        )
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
            work_unit.entity_plan = entity_plan
            work_unit.stage = "claim_routing"
            self.artifacts.save_identity_work_unit(work_unit)
        except Exception as exc:
            return self._fail_work_unit(
                work_unit,
                evidence,
                "entity_plan",
                "Entity plan response did not satisfy the contract: "
                f"{type(exc).__name__}: {exc}",
            )

        graph_edges = [
            {
                "source_node": node_id,
                "target_node": decision["parent_entity"],
                "relation": (
                    "occurrence_of"
                    if decision["scope"] == "occurrence"
                    else "component_of"
                ),
                "supporting_evidence": graph_nodes[node_id]["supporting_evidence"],
            }
            for node_id, decision in entity_decisions.items()
            if decision["scope"] in {"component", "occurrence"}
        ]
        graph_plan = {
            "nodes": node_plan["nodes"],
            "edges": graph_edges,
            "participants": entity_plan["participants"],
        }

        candidate_entities: dict[str, EntityRecord] = {}
        candidate_support: dict[str, tuple[str, ...]] = {}
        identity_blockers_by_alias: dict[str, list[str]] = {}
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
            accepted = decision["adjudication"] == "accepted"
            scope = str(decision["scope"])
            scope_definition = subject_scope_definition(scope)
            page_state = scope_definition.page_state
            entity: EntityRecord | None = None
            if accepted and decision["entity_id"]:
                entity = planned[str(decision["entity_id"])]
                before = (
                    entity.title,
                    tuple(entity.aliases),
                    entity.materialization_state,
                )
                if accepted:
                    previous_title = entity.title
                    entity.title = str(node["title"])
                    entity.aliases = sorted({
                        *entity.aliases,
                        *[str(value) for value in node["aliases"]],
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
            elif accepted and scope_definition.persisted_scope == "independent":
                entity = self._planned_entity(
                    node["entity_type"],
                    node["title"],
                    planned.values(),
                    now,
                    aliases=node["aliases"],
                    materialization_state=page_state,
                )
                planned[entity.entity_id] = entity
                result.new_entities.append(entity)
            if entity is not None:
                candidate_entities[node_id] = entity
                candidate_support[entity.entity_id] = support
            supporting_claim_ids = [item.claim.claim_id for item in supporting]
            parent_ref = str(decision["parent_entity"])
            parent_entity = candidate_entities.get(parent_ref) or planned.get(parent_ref)
            identity_decision = EntityResolutionDecision(
                decision_id=f"identity-{uuid.uuid4().hex[:12]}",
                decision_type="entity_creation",
                entity_id=entity.entity_id if entity else None,
                proposed_entity_type=str(node["entity_type"]),
                proposed_title=str(node["title"]),
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
                review_state=str(decision["adjudication"]),
                dream_run_id=dream_run_id,
                created_at=now,
                proposed_scope=scope_definition.persisted_scope,
                proposed_parent_entity_id=(
                    parent_entity.entity_id if parent_entity else None
                ),
                proposed_page_state=page_state,
                proposed_aliases=[str(value) for value in node["aliases"]],
                proposed_type_reason=str(node["type_reason"]),
            )
            result.entity_decisions.append(identity_decision)
            if (
                identity_decision.review_state == "review_required"
                or identity_decision.proposed_page_state == "provisional"
            ):
                for alias in support:
                    identity_blockers_by_alias.setdefault(alias, []).append(
                        identity_decision.decision_id
                    )
            maturity = maturity_decisions[node_id]
            verdict = maturity_verdicts[node_id]
            result.maturity_assessments.append(IdentityMaturityAssessment(
                assessment_id=f"maturity-{uuid.uuid4().hex[:12]}",
                dream_run_id=dream_run_id,
                identity_key=node_id,
                source_node_ids=list(node["source_node_ids"]),
                proposed_title=str(node["title"]),
                proposed_entity_type=str(node["entity_type"]),
                supporting_source_ids=[
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
                proposal_admission=str(maturity["admission"]),
                proposal_basis=dict(maturity.get("basis") or {}),
                proposal_reason=str(maturity["reason"]),
                proposal_confidence=float(maturity["confidence"]),
                verifier_verdict=str(verdict["verdict"]),
                verifier_reason=str(verdict["reason"]),
                effective_admission=(
                    "review_required"
                    if decision["adjudication"] == "review_required"
                    else page_state
                ),
                created_at=now,
                entity_id=entity.entity_id if entity else None,
            ))

        result.encounters = self.resolution.participant_encounters(
            participants,
            graph_plan["participants"],
            planned,
            candidate_entities,
        )
        for encounter in result.encounters:
            encountered = planned.get(encounter.entity_id)
            if encountered is not None:
                encountered.materialization_state = "materialized"
        result.entity_decisions.extend(self.resolution.participant_decisions(
            participants,
            graph_plan["participants"],
            planned,
            candidate_entities,
            dream_run_id,
            now,
        ))

        routable_entity_types = {
            entity.entity_id: entity.entity_type
            for entity in planned.values()
            if entity.status == "active"
            and entity.materialization_state == "materialized"
        }
        resolved_plan = self.formatter.format_resolved_entity_plan(
            graph_nodes,
            entity_decisions,
            candidate_entities,
            planned,
            entity_plan["participants"],
        )
        review_required_aliases = {
            alias
            for node_id, decision in entity_decisions.items()
            if decision["adjudication"] == "review_required"
            for alias in graph_nodes[node_id]["supporting_evidence"]
            if alias in aliases
        }
        provisional_aliases = {
            alias
            for node_id, decision in entity_decisions.items()
            if decision["adjudication"] == "accepted"
            and decision["scope"] == "provisional"
            for alias in graph_nodes[node_id]["supporting_evidence"]
            if alias in aliases
        }
        deferred_identity_aliases = review_required_aliases | provisional_aliases
        routing_decisions: dict[str, dict] = {
            alias: {
                "route_kind": "deferred",
                "identity_blocker_ids": identity_blockers_by_alias.get(alias, []),
                "confidence": 1.0,
                "reason": (
                    "A supporting identity decision requires user review."
                    if alias in review_required_aliases
                    else "The supporting independent identity is still provisional."
                ),
            }
            for alias in deferred_identity_aliases
        }
        routable_aliases = {
            alias: item for alias, item in aliases.items()
            if alias not in deferred_identity_aliases
        }
        for batch_aliases in self._alias_batches(routable_aliases):
            batch_participants = self.resolution.participants_for_evidence(
                batch_aliases, participants
            )
            routing_model = claim_routing_output_model(
                batch_aliases,
                routable_entity_types,
            )
            system, user = prompts.claim_routing_prompt(
                self.formatter.entity_catalog(
                    (
                        entity for entity in planned.values()
                        if entity.entity_id in routable_entity_types
                    ),
                    include_sections=False,
                ),
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
                routing_decisions.update(batch_decisions)
            except Exception as exc:
                result.failures.extend(
                    self._failure(
                        item,
                        "Claim routing response did not satisfy the contract: "
                        f"{type(exc).__name__}: {exc}",
                    )
                    for item in batch_aliases.values()
                )
                continue

        for alias, item in aliases.items():
            if alias not in routing_decisions:
                continue
            routing = routing_decisions[alias]
            route_kind = str(routing["route_kind"])
            if route_kind == "deferred":
                normalized = {
                    "disposition": "deferred",
                    "owner_entity": "",
                    "linked_entities": [],
                    "subject_entity": "",
                    "object_entities": [],
                    "contextual_entities": [],
                    "relationship_kind": "none",
                    "supporting_claims": [],
                    "identity_blocker_ids": routing.get(
                        "identity_blocker_ids", []
                    ),
                    "confidence": routing["confidence"],
                    "reason": routing["reason"],
                }
            elif route_kind == "project_role":
                normalized = {
                    "disposition": "canonical",
                    "owner_entity": routing["owner_entity"],
                    "linked_entities": [routing["project_entity"]],
                    "subject_entity": routing["owner_entity"],
                    "object_entities": [routing["project_entity"]],
                    "contextual_entities": [],
                    "relationship_kind": "project_role",
                    "supporting_claims": [],
                    "identity_blocker_ids": [],
                    "confidence": routing["confidence"],
                    "reason": routing["reason"],
                }
            else:
                normalized = {
                    "disposition": "canonical",
                    "owner_entity": routing["owner_entity"],
                    "linked_entities": [],
                    "subject_entity": routing["subject_entity"],
                    "object_entities": routing["object_entities"],
                    "contextual_entities": routing["contextual_entities"],
                    "relationship_kind": routing["relationship_kind"],
                    "supporting_claims": [],
                    "identity_blocker_ids": [],
                    "confidence": routing["confidence"],
                    "reason": routing["reason"],
                }
            result.routes.append(self._route_decision(
                alias,
                item,
                normalized,
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
        work_unit.status = "failed" if result.failures else "complete"
        work_unit.stage = "claim_routing" if result.failures else "complete"
        work_unit.last_error = (
            result.failures[0].reason if result.failures else None
        )
        work_unit.updated_at = datetime.now().astimezone().isoformat()
        self.artifacts.save_identity_work_unit(work_unit)
        return result

    @staticmethod
    def _accumulate_identity_decision(
        groups: list[dict], decision: dict
    ) -> list[dict]:
        accumulated = [dict(group) for group in groups]
        resolution = str(decision["resolution"])
        target: dict | None = None
        if resolution == "same_as_local":
            target = next((
                group for group in accumulated
                if group["identity_key"] == decision["local_identity_key"]
            ), None)
            if target is None:
                raise ValueError(
                    "A local identity decision must reference an accumulated group"
                )
        elif resolution == "existing":
            target = next((
                group for group in accumulated
                if group["resolution"] == "existing"
                and group["entity_id"] == decision["entity_id"]
            ), None)
        if target is None:
            if resolution == "same_as_local":
                raise ValueError("Local identity target was not available")
            target = {
                "identity_key": f"I{len(accumulated) + 1:03d}",
                "node_ids": [],
                "preferred_title": decision["preferred_title"],
                "aliases": [],
                "confidence": decision["confidence"],
                "reason": decision["reason"],
                "resolution": resolution,
                "entity_id": decision["entity_id"],
                "candidate_entity_ids": list(
                    decision["candidate_entity_ids"]
                ),
            }
            accumulated.append(target)
        target["node_ids"] = list(dict.fromkeys([
            *target["node_ids"], decision["node_id"]
        ]))
        target["aliases"] = list(dict.fromkeys([
            *target["aliases"], *decision["aliases"]
        ]))
        target["confidence"] = min(
            float(target["confidence"]), float(decision["confidence"])
        )
        if len(target["node_ids"]) > 1:
            target["reason"] = (
                f"{target['reason']} {decision['node_id']}: {decision['reason']}"
            )
        return accumulated

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
        digest = hashlib.sha256("\n".join(claim_ids).encode()).hexdigest()[:16]
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
        unit.dream_run_ids = list(dict.fromkeys(unit.dream_run_ids))
        return unit

    async def _verify_identity(
        self,
        node: dict,
        candidates: list[EntityRecord],
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple],
        chunk_size: int = 12,
    ) -> dict:
        if not candidates:
            return {
                "verdict": "distinct",
                "entity_id": "",
                "candidate_entity_ids": [],
                "confidence": 1.0,
                "reason": (
                    "No active canonical identity has the fixed ontology type, so "
                    "there is no existing identity candidate to duplicate."
                ),
            }
        decisions = []
        proposed = self.formatter.format_identity_groups({
            str(node["node_id"]): node
        })
        for start in range(0, len(candidates), chunk_size):
            chunk = candidates[start:start + chunk_size]
            candidate_ids = [entity.entity_id for entity in chunk]
            output_model = new_identity_verification_output_model(candidate_ids)
            system, user = prompts.new_identity_verification_prompt(
                proposed,
                self.formatter.entity_planning_catalog(chunk),
                self.formatter.format_evidence(aliases, participants),
            )
            response = await self.llm.call_structured(
                system,
                user,
                output_model,
                num_predict=2048,
                debug_label="dream-new-identity-verification",
            )
            decisions.append(
                output_model.model_validate(response).model_dump()["decision"]
            )
        existing_ids = {
            decision["entity_id"] for decision in decisions
            if decision["verdict"] == "existing"
        }
        review_ids = {
            entity_id for decision in decisions
            if decision["verdict"] == "review_required"
            for entity_id in decision["candidate_entity_ids"]
        }
        reasons = " ".join(decision["reason"] for decision in decisions)
        confidence = min(float(decision["confidence"]) for decision in decisions)
        if len(existing_ids) == 1 and not review_ids:
            return {
                "verdict": "existing",
                "entity_id": next(iter(existing_ids)),
                "candidate_entity_ids": [],
                "confidence": confidence,
                "reason": reasons,
            }
        plausible = sorted(existing_ids | review_ids)
        if plausible:
            return {
                "verdict": "review_required",
                "entity_id": "",
                "candidate_entity_ids": plausible,
                "confidence": confidence,
                "reason": reasons,
            }
        return {
            "verdict": "distinct",
            "entity_id": "",
            "candidate_entity_ids": [],
            "confidence": confidence,
            "reason": reasons,
        }

    @staticmethod
    def _merge_result(target: RoutingResult, source: RoutingResult) -> None:
        target.routes.extend(source.routes)
        target.new_entities.extend(source.new_entities)
        target.failures.extend(source.failures)
        target.encounters.extend(source.encounters)
        target.entity_decisions.extend(source.entity_decisions)
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
        if item.claim.evidence_modality == "tool":
            if owner.entity_type == "you":
                return ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    "External evidence cannot automatically establish a personal fact on You.",
                    "deferred", supporting_ids, float(decision["confidence"]),
                )
        return ClaimRoute(
            item.claim.claim_id, owner.entity_id, None, tuple(sorted(linked)),
            item.raw_log_entry_id, str(decision["reason"]), "canonical",
            supporting_ids, float(decision["confidence"]),
            resolved_references.get(subject_ref) if subject_ref else None,
            tuple(sorted({resolved_references[value] for value in object_refs})),
            tuple(sorted({
                resolved_references[value] for value in contextual_refs
            })),
            None if relationship_kind == "none" else relationship_kind,
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
        section_key=(route.section_key or "needs_review") if route.placed else None,
        linked_entity_ids=list(route.linked_entity_ids),
        status="placed" if route.placed else "deferred",
        reason=route.reason,
        created_at=timestamp,
        updated_at=timestamp,
        relationship_kind=route.relationship_kind,
        identity_blocker_ids=list(route.identity_blocker_ids),
    )
