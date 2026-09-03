"""Owner-scoped resolution from canonical claims to derived presentation facts."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime

from mycelium import prompts
from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ConsolidatedFact,
    EntityRecord,
    MemoryClaim,
    ReconsolidationProposal,
    temporal_record,
)
from mycelium.ollama import OllamaClient
from mycelium.ontology import default_section, entity_type_definition
from mycelium.projection import display_claim_text
from mycelium.structured_outputs import (
    fact_candidate_selection_output_model,
    fact_grouping_output_model,
    fact_quality_output_model,
    fact_repair_output_model,
    fact_rendering_output_model,
    fact_truth_output_model,
)


@dataclass(frozen=True)
class FactResolutionFailure:
    owner_entity_id: str
    claim_ids: list[str]
    raw_log_entry_ids: list[str]
    reason: str


@dataclass
class FactResolutionResult:
    facts: list[ConsolidatedFact] = field(default_factory=list)
    placements: list[ClaimPlacement] = field(default_factory=list)
    deleted_fact_ids: set[str] = field(default_factory=set)
    proposals: list[ReconsolidationProposal] = field(default_factory=list)
    failures: list[FactResolutionFailure] = field(default_factory=list)

    @property
    def failed_owner_ids(self) -> set[str]:
        return {failure.owner_entity_id for failure in self.failures}


class FactResolver:
    """Make one complete, fail-closed fact decision for each affected owner."""

    def __init__(self, llm: OllamaClient, artifacts: ArtifactStore):
        self.llm = llm
        self.artifacts = artifacts

    async def resolve(
        self,
        placements: list[ClaimPlacement],
        *,
        affected_entity_ids: set[str],
        incoming_claim_ids: set[str],
        dream_run_id: str,
        seed_entities: list[EntityRecord] | None = None,
    ) -> FactResolutionResult:
        result = FactResolutionResult()
        if not affected_entity_ids:
            return result
        placement_by_claim = {
            item.claim_id: item
            for item in [*self.artifacts.list_placements(), *placements]
        }
        active_claims = {
            claim.claim_id: claim
            for claim in self.artifacts.list_claims(status="active")
        }
        existing_facts = self.artifacts.list_consolidated_facts()
        entities = {entity.entity_id: entity for entity in self.artifacts.list_entities()}
        entities.update({entity.entity_id: entity for entity in seed_entities or []})
        for owner_id in sorted(affected_entity_ids):
            owner_claims = sorted(
                (
                    claim
                    for claim_id, claim in active_claims.items()
                    if self._owned_by(placement_by_claim.get(claim_id), owner_id)
                ),
                key=lambda claim: (claim.recorded_at, claim.claim_id),
            )
            owner_existing = [
                fact for fact in existing_facts if fact.owner_entity_id == owner_id
            ]
            if not owner_claims:
                result.deleted_fact_ids.update(fact.fact_id for fact in owner_existing)
                continue
            if len(owner_claims) == 1 and not owner_existing:
                claim = owner_claims[0]
                placement = placement_by_claim[claim.claim_id]
                owner = entities[owner_id]
                section = default_section(
                    owner.entity_type, claim.claim_type, claim.predicate
                )
                now = datetime.now().astimezone().isoformat()
                result.facts.append(ConsolidatedFact(
                    fact_id=f"fact-{uuid.uuid4().hex[:12]}",
                    text=display_claim_text(claim),
                    member_claim_ids=[claim.claim_id],
                    owner_entity_id=owner_id,
                    section_key=section,
                    state="history" if claim.temporal_status == "past" else "current",
                    linked_entity_ids=list(placement.linked_entity_ids),
                    synthesis_origin="claim",
                    confidence=claim.confidence,
                    reason="Direct projection of one owner-scoped canonical claim.",
                    created_at=now,
                    updated_at=now,
                ))
                result.placements.append(replace(
                    placement, section_key=section, updated_at=now
                ))
                continue
            try:
                resolved = await self._resolve_owner(
                    owner_id,
                    owner_claims,
                    placement_by_claim,
                    owner_existing,
                    incoming_claim_ids,
                    dream_run_id,
                    entities,
                )
            except Exception as exc:
                result.facts.extend(owner_existing)
                result.failures.append(FactResolutionFailure(
                    owner_entity_id=owner_id,
                    claim_ids=[claim.claim_id for claim in owner_claims],
                    raw_log_entry_ids=sorted({
                        provenance.raw_log_entry_id
                        for claim in owner_claims
                        for provenance in claim.provenance
                        if provenance.raw_log_entry_id
                    }),
                    reason=f"Fact resolution was rejected: {type(exc).__name__}: {exc}",
                ))
                continue
            result.facts.extend(resolved.facts)
            result.placements.extend(resolved.placements)
            result.proposals.extend(resolved.proposals)
            output_ids = {item.fact_id for item in resolved.facts}
            result.deleted_fact_ids.update(
                fact.fact_id for fact in owner_existing
                if fact.fact_id not in output_ids
            )
        return result

    async def _resolve_owner(
        self,
        owner_id: str,
        claims: list[MemoryClaim],
        placements: dict[str, ClaimPlacement],
        existing: list[ConsolidatedFact],
        incoming_claim_ids: set[str],
        dream_run_id: str,
        entities: dict[str, EntityRecord],
    ) -> FactResolutionResult:
        owner = entities[owner_id]
        definition = entity_type_definition(owner.entity_type)
        owner_claim_ids = {claim.claim_id for claim in claims}
        represented_claim_ids = {
            claim_id for fact in existing for claim_id in fact.member_claim_ids
        }
        unrepresented = [
            claim for claim in claims
            if claim.claim_id not in represented_claim_ids
        ]
        structurally_affected = {
            fact.fact_id for fact in existing
            if not set(fact.member_claim_ids) <= owner_claim_ids
        }
        candidate_fact_ids_by_claim: dict[str, set[str]] = {}
        selected_fact_ids = set(structurally_affected)
        if unrepresented and existing:
            candidate_fact_ids_by_claim = await self._select_prior_facts(
                unrepresented,
                placements,
                existing,
                entities,
            )
            selected_fact_ids.update({
                fact_id
                for fact_ids in candidate_fact_ids_by_claim.values()
                for fact_id in fact_ids
            })
        selected_existing = [
            fact for fact in existing if fact.fact_id in selected_fact_ids
        ]
        untouched_existing = [
            fact for fact in existing if fact.fact_id not in selected_fact_ids
        ]
        selected_claim_ids = {
            claim_id for fact in selected_existing
            for claim_id in fact.member_claim_ids
        }
        claims = [
            claim for claim in claims
            if claim.claim_id not in represented_claim_ids
            or claim.claim_id in selected_claim_ids
        ]
        existing = selected_existing
        if not claims:
            return FactResolutionResult(facts=untouched_existing)
        aliases = {
            f"C{index:03d}": claim for index, claim in enumerate(claims, start=1)
        }
        alias_for_claim = {claim.claim_id: alias for alias, claim in aliases.items()}
        linked_ids = sorted({
            linked_id
            for claim in claims
            for linked_id in placements[claim.claim_id].linked_entity_ids
        })
        linked_aliases = {
            f"E{index:03d}": entity_id
            for index, entity_id in enumerate(linked_ids, start=1)
        }
        alias_for_entity = {
            entity_id: alias for alias, entity_id in linked_aliases.items()
        }
        owner_text = self._owner_text(owner)
        claims_text = self._claims_text(
            aliases, placements, alias_for_entity, entities
        )
        existing_text = self._existing_facts_text(existing, alias_for_claim)
        incoming_aliases = sorted(
            alias for alias, claim in aliases.items()
            if claim.claim_id in incoming_claim_ids
        )
        adjudications: dict[str, dict] = {}
        reserved_target_aliases: set[str] = set()
        prior_decisions: list[dict] = []
        facts_by_id = {fact.fact_id: fact for fact in existing}
        for incoming_alias in incoming_aliases:
            incoming_claim = aliases[incoming_alias]
            candidate_facts = [
                facts_by_id[fact_id]
                for fact_id in sorted(candidate_fact_ids_by_claim.get(
                    incoming_claim.claim_id, set()
                ))
                if fact_id in facts_by_id
            ]
            target_aliases = sorted({
                alias_for_claim[claim_id]
                for fact in candidate_facts
                for claim_id in fact.member_claim_ids
                if claim_id in alias_for_claim
                and alias_for_claim[claim_id] not in reserved_target_aliases
            })
            decision_aliases = {
                alias: aliases[alias]
                for alias in [incoming_alias, *target_aliases]
            }
            incoming_claim_text = self._claims_text(
                {incoming_alias: incoming_claim},
                placements,
                alias_for_entity,
                entities,
            )
            target_claims_text = self._claims_text(
                {alias: aliases[alias] for alias in target_aliases},
                placements,
                alias_for_entity,
                entities,
            ) if target_aliases else "none"
            decision_relations_text = self._relations_text(
                owner_id,
                {claim.claim_id: alias for alias, claim in decision_aliases.items()},
            )
            system, user = prompts.fact_truth_prompt(
                owner_text,
                target_claims_text,
                self._existing_facts_text(candidate_facts, alias_for_claim),
                decision_relations_text,
                incoming_claim_text,
                json.dumps(prior_decisions, ensure_ascii=False, sort_keys=True),
            )
            truth_schema = fact_truth_output_model([incoming_alias], target_aliases)
            response = await self.llm.call_structured(
                system,
                user,
                truth_schema,
                num_predict=2048,
                debug_label="dream-fact-truth",
            )
            decision = truth_schema.model_validate(response).model_dump()[
                "decisions"
            ][incoming_alias]
            adjudications[incoming_alias] = decision
            prior_decision = {
                "incoming_claim_alias": incoming_alias,
                "disposition": decision["disposition"],
            }
            if decision["disposition"] == "truth_change":
                reserved_target_aliases.update(decision["target_claim_aliases"])
                prior_decision.update({
                    "relation": decision["relation"],
                    "target_claim_aliases": decision["target_claim_aliases"],
                })
            prior_decisions.append(prior_decision)
        changes = [
            {
                "relation": decision["relation"],
                "incoming_claim_aliases": [alias],
                "target_claim_aliases": decision["target_claim_aliases"],
                "explanation": decision["explanation"],
                "confidence": decision["confidence"],
            }
            for alias, decision in adjudications.items()
            if decision["disposition"] == "truth_change"
        ]
        self._validate_truth_changes(changes, aliases, incoming_claim_ids)

        system, user = prompts.fact_grouping_prompt(
            owner_text,
            claims_text,
            existing_text,
            json.dumps(changes, ensure_ascii=False, sort_keys=True),
        )
        grouping_schema = fact_grouping_output_model(aliases, changes)
        response = await self.llm.call_structured(
            system,
            user,
            grouping_schema,
            num_predict=4096,
            debug_label="dream-fact-grouping",
        )
        assignments = grouping_schema.model_validate(response).model_dump()[
            "assignments"
        ]
        members_by_key: dict[str, list[str]] = {}
        for alias, assignment in assignments.items():
            members_by_key.setdefault(assignment["fact_key"], []).append(alias)

        rendered_facts: dict[str, dict] = {}
        fact_keys = sorted(members_by_key)
        for batch_index, batch_keys in enumerate(
            self._fact_key_batches(fact_keys), start=1
        ):
            batch_aliases = {
                alias: aliases[alias]
                for key in batch_keys
                for alias in members_by_key[key]
            }
            batch_claim_ids = {
                claim.claim_id for claim in batch_aliases.values()
            }
            batch_existing = [
                fact for fact in existing
                if set(fact.member_claim_ids) & batch_claim_ids
            ]
            groups_text = self._fact_groups_text(
                batch_keys,
                members_by_key,
                batch_aliases,
                placements,
                alias_for_entity,
                entities,
            )
            system, user = prompts.fact_rendering_prompt(
                owner_text,
                "\n".join(
                    f"{section.key}: {section.description}"
                    for section in definition.sections
                ),
                groups_text,
                self._existing_facts_text(batch_existing, alias_for_claim),
            )
            rendering_schema = fact_rendering_output_model(
                batch_keys, definition.section_keys()
            )
            response = await self.llm.call_structured(
                system,
                user,
                rendering_schema,
                num_predict=4096,
                debug_label=f"dream-fact-rendering-{batch_index}",
            )
            batch_rendered = rendering_schema.model_validate(response).model_dump()[
                "facts"
            ]
            batch_rendered = await self._verify_and_repair_facts(
                owner_text,
                groups_text,
                batch_rendered,
            )
            rendered_facts.update(batch_rendered)
        plan = {
            "assignments": assignments,
            "facts": [
                {"fact_key": fact_key, **rendered_facts[fact_key]}
                for fact_key in fact_keys
            ],
            "truth_changes": changes,
        }
        groups, changes = self._validate_plan(
            plan, aliases, placements, incoming_claim_ids
        )
        now = datetime.now().astimezone().isoformat()
        output = FactResolutionResult(facts=list(untouched_existing))
        pending_incoming = {
            aliases[alias].claim_id
            for change in changes
            for alias in change["incoming_claim_aliases"]
        }
        protected_targets = {
            aliases[alias].claim_id
            for change in changes
            for alias in change["target_claim_aliases"]
        }
        for change in changes:
            incoming_ids = [
                aliases[alias].claim_id for alias in change["incoming_claim_aliases"]
            ]
            target_ids = [
                aliases[alias].claim_id for alias in change["target_claim_aliases"]
            ]
            prior = self.artifacts.find_reconsolidation_proposal(
                incoming_ids, target_ids, change["relation"]
            )
            if prior is None:
                output.proposals.append(ReconsolidationProposal(
                    proposal_id=f"recon-{uuid.uuid4().hex[:12]}",
                    incoming_claim_ids=incoming_ids,
                    target_claim_ids=target_ids,
                    proposed_relation=change["relation"],
                    explanation=change["explanation"],
                    confidence=change["confidence"],
                    dream_run_id=dream_run_id,
                    created_at=now,
                    affected_entity_ids=sorted({
                        owner_id,
                        *(
                            linked_id
                            for claim_id in (*incoming_ids, *target_ids)
                            for linked_id in placements[claim_id].linked_entity_ids
                        ),
                    }),
                ))
        existing_pending = [
            proposal
            for proposal in self.artifacts.list_reconsolidation_proposals(status="pending")
            if owner_id in proposal.affected_entity_ids
        ]
        pending_incoming.update(
            claim_id for proposal in existing_pending
            for claim_id in proposal.incoming_claim_ids
        )
        protected_targets.update(
            claim_id for proposal in existing_pending
            for claim_id in proposal.target_claim_ids
        )
        preserved_member_ids: set[str] = set()
        for fact in existing:
            if set(fact.member_claim_ids) & protected_targets:
                output.facts.append(fact)
                preserved_member_ids.update(fact.member_claim_ids)
        for group, member_aliases in groups:
            members = [aliases[alias] for alias in member_aliases]
            member_ids = {claim.claim_id for claim in members}
            if member_ids & pending_incoming:
                continue
            if member_ids & preserved_member_ids:
                continue
            section = group["section_key"]
            linked = sorted({
                linked_id
                for member in members
                for linked_id in placements[member.claim_id].linked_entity_ids
            })
            prior_candidates = [
                fact for fact in existing
                if fact.owner_entity_id == owner_id
                and fact.section_key == section
                and set(fact.member_claim_ids) <= member_ids
            ]
            prior = (
                prior_candidates[0] if len(prior_candidates) == 1 else None
            )
            manual = prior is not None and prior.manual_text
            output.facts.append(ConsolidatedFact(
                fact_id=prior.fact_id if prior else f"fact-{uuid.uuid4().hex[:12]}",
                text=prior.text if manual else group["text"],
                member_claim_ids=sorted(member_ids),
                owner_entity_id=owner_id,
                section_key=section,
                state=group["state"],
                linked_entity_ids=linked,
                synthesis_origin="manual" if manual else "model",
                confidence=prior.confidence if manual else group["confidence"],
                reason=prior.reason if manual else group["reason"],
                created_at=prior.created_at if prior else now,
                updated_at=now,
                manual_text=manual,
            ))
            for member in members:
                placement = placements[member.claim_id]
                output.placements.append(replace(
                    placement,
                    section_key=section,
                    updated_at=now,
                ))
        for claim_id in pending_incoming:
            placement = placements.get(claim_id)
            if placement is not None:
                output.placements.append(replace(
                    placement, section_key="needs_review", updated_at=now
                ))
        return output

    async def _select_prior_facts(
        self,
        incoming: list[MemoryClaim],
        placements: dict[str, ClaimPlacement],
        existing: list[ConsolidatedFact],
        entities: dict[str, EntityRecord],
        chunk_size: int = 12,
    ) -> dict[str, set[str]]:
        fact_aliases = {
            fact.fact_id: f"X{index:03d}"
            for index, fact in enumerate(existing, start=1)
        }
        selected: dict[str, set[str]] = {
            claim.claim_id: set() for claim in incoming
        }
        for claim_index, claim in enumerate(incoming, start=1):
            claim_alias = f"C{claim_index:03d}"
            aliases = {claim_alias: claim}
            linked_ids = sorted(
                placements[claim.claim_id].linked_entity_ids
            )
            alias_for_entity = {
                entity_id: f"E{index:03d}"
                for index, entity_id in enumerate(linked_ids, start=1)
            }
            incoming_text = self._claims_text(
                aliases, placements, alias_for_entity, entities
            )
            for start in range(0, len(existing), chunk_size):
                chunk = existing[start:start + chunk_size]
                aliases_for_chunk = {
                    fact_aliases[fact.fact_id]: fact for fact in chunk
                }
                output_model = fact_candidate_selection_output_model(
                    aliases,
                    aliases_for_chunk,
                )
                prior_text = "\n".join(
                    f"[{alias}] state={fact.state}; section={fact.section_key}; "
                    f"text={fact.text}"
                    for alias, fact in aliases_for_chunk.items()
                )
                system, user = prompts.fact_candidate_selection_prompt(
                    incoming_text,
                    prior_text,
                )
                response = await self.llm.call_structured(
                    system,
                    user,
                    output_model,
                    num_predict=2048,
                    debug_label="dream-fact-candidate-selection",
                )
                decision = output_model.model_validate(response).model_dump()[
                    "decisions"
                ][claim_alias]
                selected[claim.claim_id].update(
                    aliases_for_chunk[alias].fact_id
                    for alias in decision["candidate_fact_ids"]
                )
        return selected

    async def _verify_and_repair_facts(
        self,
        owner_text: str,
        groups_text: str,
        rendered: dict[str, dict],
    ) -> dict[str, dict]:
        verdicts = await self._fact_quality_verdicts(
            owner_text, groups_text, rendered
        )
        rejected = {
            key: rendered[key] for key, verdict in verdicts.items()
            if verdict["verdict"] == "unsupported"
        }
        if not rejected:
            return rendered
        feedback = "\n".join(
            f"[{key}] fixed_state={rendered[key]['state']}; "
            f"fixed_section={rendered[key]['section_key']}; "
            f"rejected_text={rendered[key]['text']}; "
            f"verifier={verdicts[key]['reason']}"
            for key in rejected
        )
        repair_model = fact_repair_output_model(rejected)
        system, user = prompts.fact_repair_prompt(
            owner_text, feedback, groups_text
        )
        response = await self.llm.call_structured(
            system,
            user,
            repair_model,
            num_predict=4096,
            debug_label="dream-fact-repair",
        )
        repairs = repair_model.model_validate(response).model_dump()["facts"]
        repaired_verdicts = await self._fact_quality_verdicts(
            owner_text, groups_text, repairs
        )
        still_rejected = [
            key for key, verdict in repaired_verdicts.items()
            if verdict["verdict"] == "unsupported"
        ]
        if still_rejected:
            raise ValueError(
                "Presentation facts remained unsupported after repair: "
                + ", ".join(still_rejected)
            )
        return {**rendered, **repairs}

    async def _fact_quality_verdicts(
        self,
        owner_text: str,
        groups_text: str,
        rendered: dict[str, dict],
    ) -> dict[str, dict]:
        output_model = fact_quality_output_model(rendered)
        rendered_text = "\n".join(
            f"[{key}] state={fact['state']}; section={fact['section_key']}; "
            f"text={fact['text']}"
            for key, fact in rendered.items()
        )
        system, user = prompts.fact_quality_prompt(
            owner_text, rendered_text, groups_text
        )
        response = await self.llm.call_structured(
            system,
            user,
            output_model,
            num_predict=2048,
            debug_label="dream-fact-quality",
        )
        return output_model.model_validate(response).model_dump()["decisions"]

    @staticmethod
    def _owned_by(placement: ClaimPlacement | None, owner_id: str) -> bool:
        return bool(
            placement
            and placement.status == "placed"
            and placement.owner_entity_id == owner_id
        )

    @staticmethod
    def _owner_text(owner: EntityRecord) -> str:
        return f"id={owner.entity_id}; type={owner.entity_type}; title={owner.title}"

    def _claims_text(
        self,
        aliases: dict[str, MemoryClaim],
        placements: dict[str, ClaimPlacement],
        alias_for_entity: dict[str, str],
        entities: dict[str, EntityRecord],
    ) -> str:
        blocks = []
        for alias, claim in aliases.items():
            placement = placements[claim.claim_id]
            linked = [
                alias_for_entity[entity_id]
                for entity_id in placement.linked_entity_ids
                if entity_id in alias_for_entity
            ]
            evidence = []
            for provenance in claim.provenance:
                try:
                    source = self.artifacts.get_source(provenance.source_id)
                    segments = {segment.segment_id: segment for segment in source.segments}
                except FileNotFoundError:
                    segments = {}
                for segment_id in provenance.segment_ids:
                    segment = segments.get(segment_id)
                    evidence.append({
                        "source_id": provenance.source_id,
                        "segment_id": segment_id,
                        "speaker": provenance.speaker,
                        "evidence_type": provenance.evidence_type,
                        "text": segment.content if segment else None,
                    })
            blocks.append(
                f"[{alias}] id={claim.claim_id}; type={claim.claim_type}; "
                f"predicate={claim.predicate or 'unknown'}; temporal_status={claim.temporal_status}; "
                f"temporal={json.dumps(temporal_record(claim.facets), sort_keys=True)}; "
                f"recorded_at={claim.recorded_at}; "
                f"linked_entities={json.dumps(linked)}\nclaim={claim.text}\n"
                f"evidence={json.dumps(evidence, ensure_ascii=False, sort_keys=True)}"
            )
        linked_registry = []
        for entity_id, alias in alias_for_entity.items():
            entity = entities.get(entity_id)
            if entity is not None:
                linked_registry.append(
                    f"[{alias}] id={entity.entity_id}; type={entity.entity_type}; title={entity.title}"
                )
        registry = "\n".join(linked_registry) or "none"
        return "LINKED ENTITY REGISTRY\n" + registry + "\n\n" + "\n\n".join(blocks)

    @staticmethod
    def _existing_facts_text(
        facts: list[ConsolidatedFact], alias_for_claim: dict[str, str]
    ) -> str:
        if not facts:
            return "none"
        return "\n".join(
            f"[X{index:03d}] id={fact.fact_id}; state={fact.state}; "
            f"section={fact.section_key}; claims={json.dumps([alias_for_claim[c] for c in fact.member_claim_ids if c in alias_for_claim])}; "
            f"manual_text={fact.manual_text}; text={fact.text}"
            for index, fact in enumerate(facts, start=1)
        )

    def _fact_groups_text(
        self,
        fact_keys: list[str],
        members_by_key: dict[str, list[str]],
        aliases: dict[str, MemoryClaim],
        placements: dict[str, ClaimPlacement],
        alias_for_entity: dict[str, str],
        entities: dict[str, EntityRecord],
    ) -> str:
        membership = "\n".join(
            f"[{fact_key}] members={json.dumps(members_by_key[fact_key])}"
            for fact_key in fact_keys
        )
        return membership + "\n\n" + self._claims_text(
            aliases, placements, alias_for_entity, entities
        )

    @staticmethod
    def _fact_key_batches(
        fact_keys: list[str], batch_size: int = 12
    ) -> list[list[str]]:
        return [
            fact_keys[index:index + batch_size]
            for index in range(0, len(fact_keys), batch_size)
        ]

    def _relations_text(
        self, owner_id: str, alias_for_claim: dict[str, str]
    ) -> str:
        values = []
        for proposal in self.artifacts.list_reconsolidation_proposals():
            if owner_id not in proposal.affected_entity_ids:
                continue
            incoming = [
                alias_for_claim[claim_id] for claim_id in proposal.incoming_claim_ids
                if claim_id in alias_for_claim
            ]
            targets = [
                alias_for_claim[claim_id] for claim_id in proposal.target_claim_ids
                if claim_id in alias_for_claim
            ]
            if not incoming or not targets:
                continue
            values.append(
                f"status={proposal.status}; relation={proposal.proposed_relation}; "
                f"incoming={json.dumps(incoming)}; targets={json.dumps(targets)}; "
                f"reviewer_note={proposal.reviewer_note or 'none'}"
            )
        return "\n".join(values) or "none"

    @staticmethod
    def _validate_plan(
        plan: dict,
        aliases: dict[str, MemoryClaim],
        placements: dict[str, ClaimPlacement],
        incoming_claim_ids: set[str],
    ) -> tuple[list[tuple[dict, list[str]]], list[dict]]:
        assignments = plan["assignments"]
        facts = plan["facts"]
        fact_by_key = {fact["fact_key"]: fact for fact in facts}
        if len(fact_by_key) != len(facts):
            raise ValueError("Fact keys must be unique")
        used_keys = {assignment["fact_key"] for assignment in assignments.values()}
        if used_keys != set(fact_by_key):
            raise ValueError("Every assigned fact key must have exactly one used definition")
        members_by_key: dict[str, list[str]] = {key: [] for key in used_keys}
        for alias, assignment in assignments.items():
            members_by_key[assignment["fact_key"]].append(alias)
        groups = []
        for key, members in members_by_key.items():
            fact = fact_by_key[key]
            groups.append((fact, members))
        FactResolver._validate_truth_changes(
            plan["truth_changes"], aliases, incoming_claim_ids
        )
        for change in plan["truth_changes"]:
            incoming = set(change["incoming_claim_aliases"])
            targets = set(change["target_claim_aliases"])
            incoming_keys = {assignments[alias]["fact_key"] for alias in incoming}
            target_keys = {assignments[alias]["fact_key"] for alias in targets}
            if incoming_keys & target_keys:
                raise ValueError("Truth-change sides cannot share a fact")
        return groups, plan["truth_changes"]

    @staticmethod
    def _validate_truth_changes(
        changes: list[dict],
        aliases: dict[str, MemoryClaim],
        incoming_claim_ids: set[str],
    ) -> None:
        changed_aliases: set[str] = set()
        for change in changes:
            incoming = set(change["incoming_claim_aliases"])
            targets = set(change["target_claim_aliases"])
            if incoming & targets or changed_aliases & (incoming | targets):
                raise ValueError(
                    "Truth-change claim sides must be distinct and non-overlapping"
                )
            if any(
                aliases[alias].claim_id not in incoming_claim_ids
                for alias in incoming
            ):
                raise ValueError(
                    "Truth-change incoming claims must come from this Dream cohort"
                )
            if any(
                aliases[alias].claim_id in incoming_claim_ids for alias in targets
            ):
                raise ValueError(
                    "Truth-change targets must be previously accepted claims"
                )
            changed_aliases.update(incoming | targets)
