"""Semantic entity ownership planning for deterministic wiki consolidation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from mycelium import prompts
from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    EntityEncounter,
    EntityRecord,
    MemoryClaim,
    SourceDocument,
)
from mycelium.models import PAGE_SECTION_KEYS, PAGE_TYPES, PageType
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import cohort_scope_output_model
from mycelium.wiki_schema import default_section, is_project_role


CREATION_BASIS: dict[PageType, set[str]] = {
    "you": set(),
    "person": {"meeting_participant", "durable_person"},
    "project": {"named_project", "project_continuity"},
    "topic": {"intentional_topic", "topic_evidence"},
    "organization": {"lasting_organization"},
    "place": {"lasting_place"},
    "event": {"substantial_event"},
}


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


class ClaimRouter:
    """Plan one validated entity owner for every admitted claim."""

    def __init__(self, llm: OllamaClient, artifacts: ArtifactStore):
        self.llm = llm
        self.artifacts = artifacts

    async def route(self, evidence: list[ClaimEvidence]) -> RoutingResult:
        result = RoutingResult()
        planned = {entity.entity_id: entity for entity in self.artifacts.list_entities()}
        if not evidence:
            return result
        aliases = {f"C{index:03d}": item for index, item in enumerate(evidence, start=1)}
        participants = self._participant_occurrences(evidence)
        output_model = cohort_scope_output_model(aliases, {
            alias: role for alias, (_, _, role) in participants.items()
        })
        system, user = prompts.cohort_scope_prompt(
            self._entity_catalog(planned.values()),
            self._format_evidence(aliases, participants),
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                output_model,
                num_predict=8192,
                debug_label="dream-cohort-scope",
            )
            plan = output_model.model_validate(response).model_dump()
            if set(plan["assignments"]) != set(aliases):
                raise ValueError("Cohort assignments did not cover the exact evidence aliases")
            allowed_aliases = set(aliases)
            if any(
                set(candidate["supporting_claims"]) - allowed_aliases
                for candidate in plan["candidates"]
            ) or any(
                set(decision["supporting_claims"]) - allowed_aliases
                for decision in plan["assignments"].values()
            ):
                raise ValueError("Cohort plan cited an unknown evidence alias")
            allowed_participants = set(participants)
            if set(plan["participants"]) != allowed_participants or any(
                set(candidate["supporting_participants"]) - allowed_participants
                for candidate in plan["candidates"]
            ):
                raise ValueError("Cohort plan did not resolve the exact participant aliases")
            candidate_ids = {
                candidate["candidate_id"] for candidate in plan["candidates"]
            }
            if len(candidate_ids) != len(plan["candidates"]):
                raise ValueError("Cohort plan declared a candidate ID more than once")
            entity_types = {
                **{key: entity.entity_type for key, entity in planned.items()},
                **{
                    candidate["candidate_id"]: candidate["entity_type"]
                    for candidate in plan["candidates"]
                },
            }
            if any(
                (
                    role == "user" and resolution["entity"] != "you"
                ) or (
                    role != "user"
                    and entity_types.get(resolution["entity"]) != "person"
                )
                for alias, resolution in plan["participants"].items()
                for role in [participants[alias][2]]
            ):
                raise ValueError("Source participants must resolve to You or a Person")
        except Exception as exc:
            return self._fail_batch(
                evidence,
                f"Cohort scope response did not satisfy the contract: {type(exc).__name__}",
            )

        candidate_entities: dict[str, EntityRecord] = {}
        candidate_support: dict[str, tuple[str, ...]] = {}
        now = datetime.now().astimezone().isoformat()
        for candidate in plan["candidates"]:
            assigned_support = [
                alias
                for alias, decision in plan["assignments"].items()
                if decision["disposition"] == "canonical"
                and decision["owner_entity"] == candidate["candidate_id"]
            ]
            support = tuple(dict.fromkeys([
                *candidate["supporting_claims"], *assigned_support,
            ]))
            supporting = [aliases[value] for value in support]
            if not self._candidate_is_eligible(candidate, supporting):
                continue
            entity = self._planned_entity(
                candidate["entity_type"],
                candidate["title"],
                planned.values(),
                now,
                aliases=candidate["aliases"],
            )
            planned[entity.entity_id] = entity
            candidate_entities[candidate["candidate_id"]] = entity
            candidate_support[candidate["candidate_id"]] = support
            result.new_entities.append(entity)

        result.encounters = self._participant_encounters(
            participants,
            plan["participants"],
            planned,
            candidate_entities,
        )

        for alias, item in aliases.items():
            decision = plan["assignments"][alias]
            result.routes.append(self._route_decision(
                alias,
                item,
                decision,
                aliases,
                planned,
                candidate_entities,
                candidate_support,
            ))
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
        if owner is None or owner.status != "active":
            return ClaimRoute(
                item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                f"Proposed owner {owner_ref!r} was not admitted or active. {decision['reason']}",
                "deferred", supporting_ids, float(decision["confidence"]),
            )
        link_refs = [str(value) for value in decision["linked_entities"]]
        linked = set()
        for value in link_refs:
            linked_entity = candidates.get(value) or entities.get(value)
            if linked_entity is None or linked_entity.status != "active":
                return ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    f"Proposed linked entity {value!r} was not admitted or active. "
                    f"{decision['reason']}",
                    "deferred", supporting_ids, float(decision["confidence"]),
                )
            linked.add(linked_entity.entity_id)
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
                    "source_only", supporting_ids, float(decision["confidence"]),
                )
            section = "evidence" if owner.entity_type == "event" else "research_references"
        return ClaimRoute(
            item.claim.claim_id, owner.entity_id, section, tuple(sorted(linked)),
            item.raw_log_entry_id, str(decision["reason"]), "canonical",
            supporting_ids, float(decision["confidence"]),
        )

    @staticmethod
    def _participant_occurrences(
        evidence: list[ClaimEvidence],
    ) -> dict[str, tuple[SourceDocument, str, str | None]]:
        """Expose source-declared participant occurrences to the scope contract."""
        sources = {
            item.source.source_id: item.source
            for item in evidence
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

    @classmethod
    def _candidate_is_eligible(
        cls,
        candidate: dict,
        supporting: list[ClaimEvidence],
    ) -> bool:
        entity_type = str(candidate["entity_type"])
        basis = str(candidate["creation_basis"])
        if (
            not str(candidate["title"]).strip()
            or entity_type not in CREATION_BASIS
            or basis not in CREATION_BASIS[entity_type]
            or not (supporting or candidate["supporting_participants"])
        ):
            return False
        if entity_type == "person":
            return bool(candidate["supporting_participants"] or supporting)
        claims = [item.claim for item in supporting]
        source_ids = {item.source.source_id for item in supporting}
        if entity_type == "project":
            if basis == "named_project":
                if not any(claim.claim_type == "identity" for claim in claims):
                    return False
                return len({claim.claim_id for claim in claims}) >= 2
            continuity = any(
                claim.claim_type in {"plan", "commitment", "decision", "state"}
                for claim in claims
            )
            return (
                bool(candidate["independent_scope"])
                and len(source_ids) >= 2
                and len(claims) >= 2
                and continuity
            )
        if not candidate["independent_scope"]:
            return False
        if entity_type == "topic":
            intentional = any(
                item.source.source_type != "tool_observation"
                and item.claim.claim_type in {"plan", "commitment"}
                for item in supporting
            )
            return intentional or len({item.source.source_id for item in supporting if item.source.source_type != "tool_observation"}) >= 2
        if entity_type == "organization":
            return len(source_ids) >= 2 and any(
                item.source.source_type != "tool_observation"
                and item.claim.claim_type in {"relationship", "plan", "commitment"}
                for item in supporting
            )
        if entity_type == "place":
            return len(source_ids) >= 2 and any(
                item.claim.claim_type in {"plan", "relationship", "state"}
                for item in supporting
            )
        if entity_type == "event":
            return len(claims) >= 2 and any(
                claim.claim_type in {"event", "decision", "plan"} for claim in claims
            )
        return False

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
                f"aliases={aliases}"
            )
        if not found:
            lines.append("- none yet")
        return "\n".join(lines)

    @staticmethod
    def _format_evidence(
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple[SourceDocument, str, str | None]],
    ) -> str:
        blocks = []
        for alias, item in aliases.items():
            claim = item.claim
            entities = ", ".join(
                str(value.get("entity")) for value in claim.about if value.get("entity")
            ) or "unknown"
            facets = "; ".join(
                f"{key}={value}" for key, value in sorted(claim.facets.items())
                if value not in (None, "", [], {})
            )
            blocks.append(
                f"[EVIDENCE {alias}]\nclaim_type={claim.claim_type}; entities={entities}; "
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
