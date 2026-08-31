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
from mycelium.structured_outputs import fact_resolution_output_model


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
        system, user = prompts.fact_resolution_prompt(
            self._owner_text(owner),
            "\n".join(
                f"{section.key}: {section.description}" for section in definition.sections
            ),
            self._claims_text(aliases, placements, alias_for_entity, entities),
            self._existing_facts_text(existing, alias_for_claim),
            self._relations_text(owner_id, alias_for_claim),
        )
        schema = fact_resolution_output_model(
            aliases, definition.section_keys()
        )
        response = await self.llm.call_structured(
            system,
            user,
            schema,
            num_predict=4096,
            debug_label="dream-fact-resolution",
        )
        plan = schema.model_validate(response).model_dump()
        groups, changes = self._validate_plan(
            plan, aliases, placements, incoming_claim_ids
        )
        now = datetime.now().astimezone().isoformat()
        output = FactResolutionResult()
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
            prior = next((
                fact for fact in existing
                if fact.owner_entity_id == owner_id
                and fact.section_key == section
                and set(fact.member_claim_ids) == member_ids
            ), None)
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
        changed_aliases: set[str] = set()
        for change in plan["truth_changes"]:
            incoming = set(change["incoming_claim_aliases"])
            targets = set(change["target_claim_aliases"])
            if incoming & targets or changed_aliases & (incoming | targets):
                raise ValueError("Truth-change claim sides must be distinct and non-overlapping")
            if any(aliases[alias].claim_id not in incoming_claim_ids for alias in incoming):
                raise ValueError("Truth-change incoming claims must come from this Dream cohort")
            if any(aliases[alias].claim_id in incoming_claim_ids for alias in targets):
                raise ValueError("Truth-change targets must be previously accepted claims")
            incoming_keys = {assignments[alias]["fact_key"] for alias in incoming}
            target_keys = {assignments[alias]["fact_key"] for alias in targets}
            if incoming_keys & target_keys:
                raise ValueError("Truth-change sides cannot share a fact")
            changed_aliases.update(incoming | targets)
        return groups, plan["truth_changes"]
