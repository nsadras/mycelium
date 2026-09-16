"""Global truth review followed by owner-scoped presentation of canonical claims."""

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
    temporal_records,
)
from mycelium.batching import structured_input_budget
from mycelium.budget import request_tokens
from mycelium.fact_groups import (
    FactText,
    fact_groups_model,
    fact_groups_prompt,
    fact_text_prompt,
)
from mycelium.ollama import OllamaClient
from mycelium.ontology import entity_type_definition
from mycelium.projection import display_claim_text
from mycelium.truth_review import TruthReviewer
from mycelium.structured_outputs import (
    fact_candidate_selection_output_model,
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
    _MAX_ADDITIONS_WITH_HISTORY = 12

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
        excluded_claim_ids: frozenset[str] = frozenset(),
    ) -> FactResolutionResult:
        result = FactResolutionResult()
        placement_by_claim = {
            item.claim_id: item
            for item in [*self.artifacts.list_placements(), *placements]
        }
        existing_facts = self.artifacts.list_consolidated_facts()
        entities = {entity.entity_id: entity for entity in self.artifacts.list_entities()}
        entities.update({entity.entity_id: entity for entity in seed_entities or []})
        truth = await TruthReviewer(self.llm, self.artifacts).review(
            incoming_claim_ids, placement_by_claim, entities, dream_run_id=dream_run_id,
            excluded_claim_ids=excluded_claim_ids,
        )
        if truth.failure_claim_ids:
            # A failed comparison never publishes unchecked additions. Prior
            # facts remain intact and these exact inputs stay retryable.
            result.facts = [f for f in existing_facts if f.owner_entity_id in affected_entity_ids]
            result.failures.append(FactResolutionFailure(
                owner_entity_id="", claim_ids=sorted(truth.failure_claim_ids),
                raw_log_entry_ids=sorted({
                    p.raw_log_entry_id for cid in truth.failure_claim_ids
                    for p in self.artifacts.get_claim(cid).provenance if p.raw_log_entry_id
                }), reason="; ".join(truth.errors), partial=True,
            ))
            return result
        result.proposals.extend(truth.proposals)
        pending = [*self.artifacts.list_reconsolidation_proposals(status="pending"), *truth.proposals]
        affected_entity_ids = affected_entity_ids | {
            eid for proposal in truth.proposals for eid in proposal.affected_entity_ids
        }
        held_claim_ids = {
            cid for proposal in pending for cid in [*proposal.incoming_claim_ids, *proposal.target_claim_ids]
        }
        # Keep whole existing presentations intact while any member is under
        # review; isolate newly arriving sides without inferring a truth change.
        protected_facts = [f for f in existing_facts if set(f.member_claim_ids) & held_claim_ids]
        held_claim_ids.update(cid for f in protected_facts for cid in f.member_claim_ids)
        active_claims = {
            c.claim_id: c for c in self.artifacts.list_claims(status="active")
            if c.claim_id not in held_claim_ids
            and c.claim_id not in excluded_claim_ids
            and c.dream_disposition != "excluded_source_policy"
        }
        for owner_id in sorted(affected_entity_ids):
            retained = [f for f in protected_facts if f.owner_entity_id == owner_id]
            result.facts.extend(retained)
            represented = {cid for f in retained for cid in f.member_claim_ids}
            for claim_id in sorted(held_claim_ids - represented):
                placement = placement_by_claim.get(claim_id)
                if not self._owned_by(placement, owner_id):
                    continue
                claim = self.artifacts.get_claim(claim_id)
                if claim.status == "active":
                    direct, _ = self._direct_projection(entities[owner_id], claim, placement)
                    result.facts.append(direct)
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
                and not set(fact.member_claim_ids) & held_claim_ids
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
        # Routing already chose this exact presentation section. Projecting one
        # statement does not justify replacing that decision with a type default.
        section = placement.section_key
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
                prominence=placement.prominence,
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
        active_owner_ids = {
            claim.claim_id for claim in claims
            if claim.status == "active" and self._owned_by(placements.get(claim.claim_id), owner_id)
        }
        # A manual edit governs its exact evidence membership. Automatic merging
        # must not silently assign new evidence to prose the user never reviewed.
        # Retractions or ownership changes invalidate that protected presentation.
        manual_facts = [
            fact for fact in existing if fact.manual_text
            and set(fact.member_claim_ids) <= active_owner_ids
        ]
        manual_ids = {fact.fact_id for fact in manual_facts}
        manual_members = {cid for fact in manual_facts for cid in fact.member_claim_ids}
        existing = [fact for fact in existing if fact.fact_id not in manual_ids]
        claims = [claim for claim in claims if claim.claim_id not in manual_members]
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
        untouched_existing = [*manual_facts, *[
            fact for fact in existing if fact.fact_id not in selected_fact_ids
        ]]
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
        owner_text = self._owner_text(owner)
        now = datetime.now().astimezone().isoformat()
        output = FactResolutionResult(facts=list(untouched_existing))
        pending_incoming: set[str] = set()
        protected_targets: set[str] = set()
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
            system, user = fact_groups_prompt(
                owner_text, json.dumps(canonical, ensure_ascii=False, indent=2),
                "\n".join(f"{section.key}: {section.description}" for section in definition.sections),
            )
            schema = fact_groups_model(canonical, definition.section_keys())
            response = schema.model_validate(await self.llm.call_structured(
                system, user, schema, num_predict=4096,
                debug_label="dream-fact-grouping",
                cache_store=self.artifacts.db,
            )).model_dump()
            groups = [(group, group["member_claim_aliases"]) for group in response["groups"]]
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
                and not fact.manual_text
                and fact.section_key == section
                and set(fact.member_claim_ids) <= member_ids
            ]
            prior = (
                prior_candidates[0] if len(prior_candidates) == 1 else None
            )
            text = await self._render_group(owner_text, members)
            output.facts.append(ConsolidatedFact(
                fact_id=prior.fact_id if prior else f"fact-{uuid.uuid4().hex[:12]}",
                text=text,
                member_claim_ids=sorted(member_ids),
                owner_entity_id=owner_id,
                section_key=section,
                state=group["state"],
                linked_entity_ids=linked,
                synthesis_origin="claim" if len(members) == 1 else "model",
                confidence=min(member.confidence for member in members),
                reason=group["memory_scope"],
                created_at=prior.created_at if prior else now,
                updated_at=now,
                prominence=group["prominence"],
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
                claim = next((c for c in aliases.values() if c.claim_id == claim_id), None)
                if claim is not None and not any(claim_id in f.member_claim_ids for f in output.facts):
                    fact, _ = self._direct_projection(owner, claim, placement)
                    output.facts.append(fact)
        return output

    async def _render_group(self, owner_text: str, members: list[MemoryClaim]) -> str:
        if len(members) == 1:
            return display_claim_text(members[0])
        # Local, stable aliases keep unrelated groups and changing cohort IDs out
        # of this request's durable cache key. Only the actual evidence matters.
        canonical = {
            f"C{index:03d}": self._canonical_record(claim)
            for index, claim in enumerate(sorted(members, key=lambda c: c.claim_id), 1)
        }
        system, user = fact_text_prompt(
            owner_text, json.dumps(canonical, ensure_ascii=False, indent=2, sort_keys=True),
        )
        return FactText.model_validate(await self.llm.call_structured(
            system, user, FactText, num_predict=1024,
            debug_label="dream-fact-text", cache_store=self.artifacts.db,
        )).text

    async def _select_prior_facts(
        self,
        incoming: list[MemoryClaim],
        placements: dict[str, ClaimPlacement],
        existing: list[ConsolidatedFact],
        entities: dict[str, EntityRecord],
        chunk_size: int = 12,
    ) -> dict[str, set[str]]:
        """Compare complete claim/fact pairs once, sharing history across new claims."""
        selected = {claim.claim_id: set() for claim in incoming}
        if not incoming or not existing:
            return selected
        if chunk_size < 1:
            raise ValueError("Candidate chunk size must be positive")
        input_budget = structured_input_budget(self.llm.context_window_tokens, 2048)
        fact_aliases = {f"X{i:03d}": fact for i, fact in enumerate(existing, 1)}
        prior_blocks = {}
        canonical = {}
        for alias, fact in fact_aliases.items():
            for claim_id in fact.member_claim_ids:
                if claim_id not in canonical:
                    canonical[claim_id] = self._canonical_record(
                        self.artifacts.get_claim(claim_id)
                    )
            members = [canonical[claim_id] for claim_id in fact.member_claim_ids]
            prior_blocks[alias] = (
                f"[{alias}] state={fact.state}; section={fact.section_key}; "
                f"text={fact.text}; members={json.dumps(members, ensure_ascii=False)}"
            )

        async def compare(claims, candidates):
            linked_ids = sorted(
                {
                    eid
                    for claim in claims.values()
                    for eid in placements[claim.claim_id].linked_entity_ids
                }
            )
            incoming_text = self._claims_text(
                claims,
                placements,
                {eid: f"E{i:03d}" for i, eid in enumerate(linked_ids, 1)},
                entities,
            )
            system, user = prompts.fact_candidate_selection_prompt(
                incoming_text,
                "\n".join(prior_blocks[alias] for alias in candidates),
            )
            schema = fact_candidate_selection_output_model(claims, candidates)
            tokens = request_tokens(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                schema=schema.model_json_schema(),
            )
            if tokens > input_budget:
                # Split exact input sets without dropping evidence or deciding relevance.
                if len(candidates) > 1:
                    pairs = list(candidates.items())
                    middle = len(pairs) // 2
                    await compare(claims, dict(pairs[:middle]))
                    await compare(claims, dict(pairs[middle:]))
                elif len(claims) > 1:
                    pairs = list(claims.items())
                    middle = len(pairs) // 2
                    await compare(dict(pairs[:middle]), candidates)
                    await compare(dict(pairs[middle:]), candidates)
                else:
                    raise ValueError(
                        "A complete candidate claim/fact pair exceeds the selection input budget "
                        f"({tokens} > {input_budget}); evidence was not truncated"
                    )
                return
            response = schema.model_validate(
                await self.llm.call_structured(
                    system,
                    user,
                    schema,
                    num_predict=2048,
                    debug_label="dream-fact-candidate-selection",
                    cache_store=self.artifacts.db,
                )
            ).model_dump()["decisions"]
            for alias, claim in claims.items():
                selected[claim.claim_id].update(
                    candidates[fact_alias].fact_id
                    for fact_alias in response[alias]["candidate_fact_ids"]
                )

        prior_pairs = list(fact_aliases.items())
        for begin in range(0, len(incoming), self._MAX_ADDITIONS_WITH_HISTORY):
            aliases = {
                f"C{i:03d}": claim
                for i, claim in enumerate(
                    incoming[begin : begin + self._MAX_ADDITIONS_WITH_HISTORY],
                    begin + 1,
                )
            }
            for start in range(0, len(prior_pairs), chunk_size):
                await compare(aliases, dict(prior_pairs[start : start + chunk_size]))
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
                "temporal": temporal_records(claim.facets), "source_times": self._source_times(claim)}

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
        claims, sources = {}, {}
        for alias, claim in aliases.items():
            citations = []
            for provenance in claim.provenance:
                citations.extend(
                    {
                        "source_id": provenance.source_id,
                        "segment_id": sid,
                        "speaker": provenance.speaker,
                        "evidence_type": provenance.evidence_type,
                    }
                    for sid in provenance.segment_ids
                )
                try:
                    source = self.artifacts.get_source(provenance.source_id)
                except FileNotFoundError:
                    continue
                entry = sources.setdefault(
                    source.source_id,
                    {
                        "source_type": source.source_type,
                        "occurred_at": source.occurred_at,
                        "segments": {},
                    },
                )
                for segment in source.segments:
                    if segment.segment_id in provenance.segment_ids:
                        entry["segments"][segment.segment_id] = {
                            "speaker": segment.speaker,
                            "role": segment.role,
                            "timestamp": segment.timestamp,
                            "text": segment.content,
                        }
            claims[alias] = {
                "claim_id": claim.claim_id,
                "claim_type": claim.claim_type,
                "predicate": claim.predicate,
                "text": claim.text,
                "temporal_status": claim.temporal_status,
                "temporal": temporal_records(claim.facets),
                "citations": citations,
                "linked_entities": [
                    alias_for_entity[e]
                    for e in placements[claim.claim_id].linked_entity_ids
                    if e in alias_for_entity
                ],
            }
        used = {
            e for c in aliases.values() for e in placements[c.claim_id].linked_entity_ids
        }
        registry = {
            alias: {
                "entity_id": eid,
                "entity_type": entities[eid].entity_type,
                "title": entities[eid].title,
            }
            for eid, alias in alias_for_entity.items()
            if eid in used and eid in entities
        }
        return json.dumps(
            {"claims": claims, "linked_entities": registry, "sources": sources},
            ensure_ascii=False,
            indent=2,
        )
