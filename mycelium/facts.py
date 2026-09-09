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
    fact_truth_output_model,
    fact_synthesis_output_model,
)


@dataclass(frozen=True)
class FactResolutionFailure:
    owner_entity_id: str
    claim_ids: list[str]
    raw_log_entry_ids: list[str]
    reason: str
    partial: bool = False


@dataclass
class FactResolutionResult:
    facts: list[ConsolidatedFact] = field(default_factory=list)
    placements: list[ClaimPlacement] = field(default_factory=list)
    deleted_fact_ids: set[str] = field(default_factory=set)
    proposals: list[ReconsolidationProposal] = field(default_factory=list)
    failures: list[FactResolutionFailure] = field(default_factory=list)

    @property
    def failed_owner_ids(self) -> set[str]:
        return {failure.owner_entity_id for failure in self.failures if not failure.partial}


class FactResolver:
    """Resolve bounded additions; preserve atomicity when changing existing ownership."""

    _MAX_UNREPRESENTED_PER_GROUPING = 12
    _MAX_ADDITIONS_WITH_HISTORY = 4

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
        held_claim_ids = {
            claim_id for proposal in self.artifacts.list_reconsolidation_proposals(status="pending")
            for claim_id in proposal.incoming_claim_ids
        }
        active_claims = {
            claim.claim_id: claim
            for claim in self.artifacts.list_claims(status="active")
            if claim.claim_id not in held_claim_ids
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
                direct_fact, direct_placement = self._direct_projection(
                    owner, claim, placement
                )
                result.facts.append(direct_fact)
                result.placements.append(direct_placement)
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
            result.failures.extend(resolved.failures)
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
        represented_claim_ids = {
            claim_id for fact in existing for claim_id in fact.member_claim_ids
        }
        unrepresented = [
            claim for claim in claims
            if claim.claim_id not in represented_claim_ids
        ]
        if not unrepresented:
            return await self._resolve_owner_step(
                owner_id,
                claims,
                placements,
                existing,
                incoming_claim_ids,
                dream_run_id,
                entities,
            )

        # Resolve bounded groups of new claims against the facts accumulated so
        # far. Later groups can still join facts created earlier in this run.
        working_facts = list(existing)
        placement_updates: dict[str, ClaimPlacement] = {}
        proposals: list[ReconsolidationProposal] = []
        failures: list[FactResolutionFailure] = []
        claim_by_id = {claim.claim_id: claim for claim in claims}
        # Partial progress is safe only for additions: existing represented claims
        # keep their persisted ownership/views. Existing-view changes remain owner-atomic.
        additions_only = all(
            claim_id in claim_by_id
            and placements.get(claim_id) == self.artifacts.placement_for_claim(claim_id)
            for claim_id in represented_claim_ids
        ) and all(
            (prior := self.artifacts.placement_for_claim(claim.claim_id)) is None
            or prior.owner_entity_id == owner_id
            for claim in unrepresented
        )
        start = 0
        while start < len(unrepresented):
            group_size = (
                self._MAX_ADDITIONS_WITH_HISTORY if working_facts
                else self._MAX_UNREPRESENTED_PER_GROUPING
            )
            incoming_group = unrepresented[
                start:start + group_size
            ]
            start += len(incoming_group)
            represented = {
                claim_id
                for fact in working_facts
                for claim_id in fact.member_claim_ids
            }
            incoming_group_ids = {claim.claim_id for claim in incoming_group}
            step_claims = [
                claim for claim in claims
                if claim.claim_id in represented | incoming_group_ids
            ]
            try:
                step = await self._resolve_owner_step(
                    owner_id, step_claims, placements, working_facts,
                    incoming_group_ids & incoming_claim_ids, dream_run_id, entities,
                    pending_proposals=proposals,
                )
            except Exception as exc:
                if not additions_only:
                    raise
                failures.append(FactResolutionFailure(
                    owner_entity_id=owner_id,
                    claim_ids=sorted(incoming_group_ids),
                    raw_log_entry_ids=sorted({
                        p.raw_log_entry_id for claim in incoming_group for p in claim.provenance
                        if p.raw_log_entry_id
                    }),
                    reason=f"Fact addition batch was rejected: {type(exc).__name__}: {exc}",
                    partial=True,
                ))
                continue
            working_facts = step.facts
            placement_updates.update({
                placement.claim_id: placement for placement in step.placements
            })
            proposals.extend(step.proposals)
        return FactResolutionResult(
            facts=working_facts,
            placements=list(placement_updates.values()),
            proposals=proposals,
            failures=failures,
        )

    @staticmethod
    def _direct_projection(
        owner: EntityRecord,
        claim: MemoryClaim,
        placement: ClaimPlacement,
    ) -> tuple[ConsolidatedFact, ClaimPlacement]:
        section = default_section(
            owner.entity_type, claim.claim_type, claim.predicate
        )
        now = datetime.now().astimezone().isoformat()
        return (
            ConsolidatedFact(
                fact_id=f"fact-{uuid.uuid4().hex[:12]}",
                text=display_claim_text(claim),
                member_claim_ids=[claim.claim_id],
                owner_entity_id=owner.entity_id,
                section_key=section,
                state="history" if claim.temporal_status == "past" else "current",
                linked_entity_ids=list(placement.linked_entity_ids),
                synthesis_origin="claim",
                confidence=claim.confidence,
                reason="Direct projection of one owner-scoped canonical claim.",
                created_at=now,
                updated_at=now,
            ),
            replace(placement, section_key=section, updated_at=now),
        )

    async def _resolve_owner_step(
        self,
        owner_id: str,
        claims: list[MemoryClaim],
        placements: dict[str, ClaimPlacement],
        existing: list[ConsolidatedFact],
        incoming_claim_ids: set[str],
        dream_run_id: str,
        entities: dict[str, EntityRecord],
        *,
        pending_proposals: list[ReconsolidationProposal] | None = None,
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
                num_predict=8192,
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
                "durable_field": decision["durable_field"],
                "prior_state": decision["prior_state"],
                "incoming_state": decision["incoming_state"],
                "transition_evidence": decision["transition_evidence"],
                "explanation": decision["explanation"] + "\nScope comparisons: " + json.dumps(decision["scope"], ensure_ascii=False),
                "confidence": decision["confidence"],
            }
            for alias, decision in adjudications.items()
            if decision["disposition"] == "truth_change"
        ]
        self._validate_truth_changes(changes, aliases, incoming_claim_ids)

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
                    durable_field=change["durable_field"],
                    prior_state=change["prior_state"],
                    incoming_state=change["incoming_state"],
                    transition_evidence=change["transition_evidence"],
                ))
        existing_pending = [
            proposal
            for proposal in [*self.artifacts.list_reconsolidation_proposals(status="pending"),
                             *(pending_proposals or [])]
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
        # Review owns these exact claim IDs. Presentation must neither rewrite
        # protected facts nor hide other claims by grouping them with held ones.
        canonical = {
            alias: self._canonical_record(claim)
            for alias, claim in aliases.items()
            if claim.claim_id not in pending_incoming | preserved_member_ids
        }
        groups = []
        if canonical:
            presentation_existing = [
                fact for fact in existing
                if not set(fact.member_claim_ids) & (pending_incoming | preserved_member_ids)
            ]
            system, user = prompts.fact_synthesis_prompt(
                owner_text, json.dumps(canonical, ensure_ascii=False),
                self._existing_facts_text(presentation_existing, alias_for_claim), "[]",
                "\n".join(f"{section.key}: {section.description}" for section in definition.sections),
            )
            schema = fact_synthesis_output_model(
                {alias: value["text"] for alias, value in canonical.items()},
                definition.section_keys(),
            )
            response = schema.model_validate(await self.llm.call_structured(
                system, user, schema, num_predict=8192,
                debug_label="dream-fact-synthesis",
            )).model_dump()
            groups = [(group, group["member_claim_aliases"]) for group in response["facts"]]
        for group, member_aliases in groups:
            members = [aliases[alias] for alias in member_aliases]
            member_ids = {claim.claim_id for claim in members}
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
                reason=prior.reason if manual else f"Scope: {group['memory_scope']}. {group['reason']}",
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
                prior_blocks = []
                for alias, fact in aliases_for_chunk.items():
                    members = [self._canonical_record(self.artifacts.get_claim(cid))
                               for cid in fact.member_claim_ids]
                    prior_blocks.append(
                        f"[{alias}] state={fact.state}; section={fact.section_key}; "
                        f"text={fact.text}; members={json.dumps(members, ensure_ascii=False)}"
                    )
                prior_text = "\n".join(prior_blocks)
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

    def _canonical_record(self, claim: MemoryClaim) -> dict:
        return {"text": display_claim_text(claim), "temporal_status": claim.temporal_status,
                "temporal": temporal_record(claim.facets), "source_times": self._source_times(claim)}

    def _source_times(self, claim: MemoryClaim) -> list[dict]:
        """Carry cited occurrence anchors, never ingestion wall-clock time."""
        times = []
        for provenance in claim.provenance:
            try:
                source = self.artifacts.get_source(provenance.source_id)
            except FileNotFoundError:
                continue
            times.append({
                "source_id": source.source_id,
                "occurred_at": source.occurred_at,
                "segments": [{"segment_id": segment.segment_id, "timestamp": segment.timestamp}
                             for segment in source.segments if segment.segment_id in provenance.segment_ids],
            })
        return times

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
            block = (
                f"[{alias}] id={claim.claim_id}; type={claim.claim_type}; "
                f"predicate={claim.predicate or 'unknown'}; temporal_status={claim.temporal_status}; "
                f"temporal={json.dumps(temporal_record(claim.facets), sort_keys=True)}; "
                f"source_times={json.dumps(self._source_times(claim), sort_keys=True)}; "
                f"linked_entities={json.dumps(linked)}\nclaim={claim.text}"
            )
            evidence = []
            for provenance in claim.provenance:
                try:
                    source = self.artifacts.get_source(provenance.source_id)
                    segments = {
                        segment.segment_id: segment for segment in source.segments
                    }
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
            block += "\nevidence=" + json.dumps(
                evidence, ensure_ascii=False, sort_keys=True
            )
            blocks.append(block)
        linked_registry = []
        used_entity_ids = {
            entity_id
            for claim in aliases.values()
            for entity_id in placements[claim.claim_id].linked_entity_ids
        }
        for entity_id, alias in alias_for_entity.items():
            if entity_id not in used_entity_ids:
                continue
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
