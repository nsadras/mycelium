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
    EntityRecord,
    MemoryClaim,
    SourceDocument,
)
from mycelium.models import PAGE_SECTION_KEYS, PAGE_TYPES, PageType
from mycelium.ollama import OllamaClient
from mycelium.structured_outputs import entity_discovery_output_model, placement_output_model
from mycelium.wiki_schema import default_section


CREATION_BASIS: dict[PageType, set[str]] = {
    "you": set(),
    "person": {"durable_person"},
    "project": {"project_continuity"},
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

    @property
    def placed(self) -> bool:
        return bool(self.owner_entity_id and self.section_key)


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


class ClaimRouter:
    """Plan one validated entity owner for every admitted claim."""

    def __init__(self, llm: OllamaClient, artifacts: ArtifactStore):
        self.llm = llm
        self.artifacts = artifacts

    async def route(self, evidence: list[ClaimEvidence]) -> RoutingResult:
        result = RoutingResult()
        evidence_by_source: dict[str, list[ClaimEvidence]] = {}
        for item in evidence:
            evidence_by_source.setdefault(item.raw_log_entry_id, []).append(item)
        planned = {entity.entity_id: entity for entity in self.artifacts.list_entities()}
        seeded = self._participant_entities(evidence, planned.values())
        for entity in seeded:
            planned[entity.entity_id] = entity
            result.new_entities.append(entity)

        # Discovery is deliberately cohort-level: claims accumulated across
        # episodes must be visible together before any one source is routed.
        # Placement remains source-scoped so a malformed response cannot poison
        # unrelated episodes.
        for offset in range(0, len(evidence), 48):
            discovered = await self._discover_entities(
                evidence[offset:offset + 48], planned
            )
            for entity in discovered:
                planned[entity.entity_id] = entity
                result.new_entities.append(entity)
        for source_evidence in evidence_by_source.values():
            for offset in range(0, len(source_evidence), 32):
                batch = source_evidence[offset:offset + 32]
                batch_result = await self._route_batch(batch, planned)
                result.routes.extend(batch_result.routes)
                result.failures.extend(batch_result.failures)
        return result

    async def _discover_entities(
        self, evidence: list[ClaimEvidence], entities: dict[str, EntityRecord]
    ) -> list[EntityRecord]:
        """Discover durable page subjects before deciding where claims belong."""
        aliases = {f"C{index:03d}": item for index, item in enumerate(evidence, start=1)}
        output_model = entity_discovery_output_model(aliases)
        system, user = prompts.entity_discovery_prompt(
            self._entity_registry(entities.values()), self._format_evidence(aliases)
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                output_model,
                num_predict=2048,
                debug_label="dream-entity-discovery",
            )
            decisions = output_model.model_validate(response).model_dump()
        except Exception:
            # Entity discovery is advisory. Placement still records a durable,
            # reviewable deferral when no established owner fits.
            return []

        known = dict(entities)
        created: list[EntityRecord] = []
        now = datetime.now().astimezone().isoformat()
        grouped: dict[tuple[str, str], list[tuple[str, dict]]] = {}
        for alias, decision in decisions.items():
            candidate = decision["candidate"]
            if candidate is None:
                continue
            entity_type = candidate["entity_type"]
            title = " ".join(str(candidate["title"]).split()).strip()
            basis = str(candidate["creation_basis"])
            if not title or entity_type not in CREATION_BASIS or basis not in CREATION_BASIS[entity_type]:
                continue
            grouped.setdefault((entity_type, slugify(title)), []).append((alias, candidate))

        for (entity_type, _), proposals in grouped.items():
            cited = [aliases[alias].claim for alias, _ in proposals]
            basis = str(proposals[0][1]["creation_basis"])
            if any(str(decision["creation_basis"]) != basis for _, decision in proposals):
                continue
            if basis == "topic_evidence" and len(cited) < 2:
                continue
            if basis == "project_continuity" and not (
                len(cited) >= 2
                or any(claim.claim_type in {"state", "plan", "commitment", "decision"} for claim in cited)
            ):
                continue
            candidate = proposals[0][1]
            title = " ".join(str(candidate["title"]).split()).strip()
            all_aliases = [
                *[alias for _, decision in proposals for alias in decision["aliases"]],
                *self._surface_aliases(title, evidence),
            ]
            names = {
                slugify(title),
                *(slugify(alias) for alias in all_aliases),
            } - {""}
            duplicate = next((
                entity for entity in known.values()
                if entity.status == "active"
                and entity.entity_type == entity_type
                and names & {
                    slugify(entity.title),
                    *(slugify(alias) for alias in entity.aliases),
                }
            ), None)
            if duplicate is not None:
                continue
            entity = self._planned_entity(
                entity_type, title, known.values(), now, aliases=all_aliases,
            )
            known[entity.entity_id] = entity
            created.append(entity)
        return created

    @staticmethod
    def _surface_aliases(title: str, evidence: Iterable[ClaimEvidence]) -> list[str]:
        """Preserve explicit possessive/qualified forms of a discovered title."""
        title_key = slugify(title)
        if not title_key:
            return []
        aliases = set()
        for item in evidence:
            for mention in item.claim.about:
                surface = " ".join(str(mention.get("entity") or "").split()).strip()
                key = slugify(surface)
                if key != title_key and key.endswith(f"-{title_key}"):
                    aliases.add(surface)
        return sorted(aliases)

    @classmethod
    def _participant_entities(
        cls,
        evidence: list[ClaimEvidence],
        existing: Iterable[EntityRecord],
    ) -> list[EntityRecord]:
        """Create Persons for direct named participants before semantic placement."""
        existing = list(existing)
        known_names = {
            slugify(name)
            for entity in existing
            if entity.entity_type == "person" and entity.status == "active"
            for name in [entity.title, *entity.aliases]
        }
        ignored = {"user", "assistant", "system", "tool", "unknown", "speaker"}
        names = sorted({
            " ".join(str(name).split()).strip()
            for item in evidence
            if item.source.source_type in {"meeting_transcript", "multi_party_conversation"}
            for name in [
                *item.source.participants,
                *(segment.speaker for segment in item.source.segments),
            ]
            if name
            and slugify(str(name)) not in ignored
            and slugify(str(name)) not in known_names
        })
        now = datetime.now().astimezone().isoformat()
        created: list[EntityRecord] = []
        for name in names:
            entity = cls._planned_entity("person", name, [*existing, *created], now)
            created.append(entity)
            known_names.add(slugify(name))
        return created

    async def _route_batch(
        self, evidence: list[ClaimEvidence], entities: dict[str, EntityRecord]
    ) -> RoutingResult:
        result = RoutingResult()
        unresolved: list[ClaimEvidence] = []
        for item in evidence:
            exact = self._exact_owner(item.claim, entities.values())
            if exact is None:
                unresolved.append(item)
                continue
            exact_owner, exact_links = exact
            if item.claim.evidence_modality == "tool" and exact_owner.entity_type == "you":
                unresolved.append(item)
                continue
            result.routes.append(ClaimRoute(
                item.claim.claim_id,
                exact_owner.entity_id,
                default_section(exact_owner.entity_type, item.claim),
                tuple(entity.entity_id for entity in exact_links),
                item.raw_log_entry_id,
                "Exact subject identity matched the canonical entity registry.",
            ))
        if not unresolved:
            return result
        evidence = unresolved
        aliases = {f"C{index:03d}": item for index, item in enumerate(evidence, start=1)}
        output_model = placement_output_model(aliases)
        system, user = prompts.consolidation_identify_prompt(
            self._entity_catalog(entities.values()), self._format_evidence(aliases)
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                output_model,
                num_predict=4096,
                debug_label="dream-claim-ownership",
            )
            if not isinstance(response, dict):
                raise ValueError("Placement response was not an object")
            decisions = output_model.model_validate(response).model_dump()
        except Exception as exc:
            result.failures.extend(self._fail_batch(
                evidence,
                f"Placement response did not satisfy the source contract: {type(exc).__name__}",
            ).failures)
            return result

        known = dict(entities)
        for alias, item in aliases.items():
            decision = decisions[alias]
            reason = str(decision["reason"]).strip()
            owner_value = str(decision["owner_entity"]).strip()
            if not owner_value:
                result.routes.append(ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id, reason
                ))
                continue

            routed_owner = known.get(owner_value)
            if routed_owner is None or routed_owner.status != "active":
                result.routes.append(ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    f"Proposed owner {owner_value!r} was not an active canonical entity. {reason}",
                ))
                continue
            if routed_owner.entity_type == "you" and self._has_named_participant_scope(item.source):
                result.failures.append(self._failure(
                    item, "Named-participant evidence cannot be owned by You"
                ))
                continue
            if not self._owner_is_grounded(routed_owner, item.claim, item.source):
                result.routes.append(ClaimRoute(
                    item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                    f"Proposed owner {routed_owner.entity_id!r} was not grounded in the standalone claim. {reason}",
                ))
                continue

            section_key = default_section(routed_owner.entity_type, item.claim)
            if item.claim.evidence_modality == "tool":
                section_key = "evidence" if routed_owner.entity_type == "event" else "research_references"
                if routed_owner.entity_type == "you":
                    result.routes.append(ClaimRoute(
                        item.claim.claim_id, None, None, (), item.raw_log_entry_id,
                        "External evidence cannot automatically establish a fact on You.",
                    ))
                    continue
            routed_links = tuple(sorted({
                value for value in decision["linked_entities"]
                if value in known and value != routed_owner.entity_id and known[value].status == "active"
            }))
            result.routes.append(ClaimRoute(
                item.claim.claim_id,
                routed_owner.entity_id,
                section_key,
                routed_links,
                item.raw_log_entry_id,
                reason,
            ))
        return result

    @staticmethod
    def _owner_is_grounded(
        owner: EntityRecord, claim: MemoryClaim, source: SourceDocument
    ) -> bool:
        if owner.entity_id == "you":
            return source.source_type == "agent_conversation"
        content = slugify(" ".join([
            claim.text,
            *(str(item.get("entity") or "") for item in claim.about),
        ]))
        words = set(content.split("-"))
        for name in [owner.title, *owner.aliases]:
            name_words = {word for word in slugify(name).split("-") if len(word) >= 3}
            if name_words & words:
                return True
        return False

    @staticmethod
    def _exact_owner(
        claim: MemoryClaim,
        entities: Iterable[EntityRecord],
    ) -> tuple[EntityRecord, list[EntityRecord]] | None:
        names = [
            (slugify(str(item.get("entity") or "")), str(item.get("role") or "").lower())
            for item in claim.about if item.get("entity")
        ]
        matches: dict[str, tuple[EntityRecord, set[str]]] = {}
        active = [entity for entity in entities if entity.status == "active"]
        for entity in active:
            aliases = {slugify(entity.title), *(slugify(alias) for alias in entity.aliases)}
            if entity.entity_id == "you":
                aliases.update({"user", "the-user"})
            roles = {role for name, role in names if name in aliases}
            if roles:
                matches[entity.entity_id] = (entity, roles)
        claim_words = f"-{slugify(claim.text)}-"
        text_matches: dict[str, EntityRecord] = {}
        for entity in active:
            aliases = {slugify(entity.title), *(slugify(alias) for alias in entity.aliases)}
            if entity.entity_id == "you":
                aliases.update({"user", "the-user"})
            if any(alias and f"-{alias}-" in claim_words for alias in aliases):
                text_matches[entity.entity_id] = entity
        # A second canonical entity named in the normalized assertion makes
        # ownership semantic, even when extraction omitted it from `about`.
        if set(text_matches) - set(matches):
            return None
        if len(matches) == 1:
            return next(iter(matches.values()))[0], []
        owners = [value[0] for value in matches.values() if "owner" in value[1]]
        if len(owners) == 1:
            owner = owners[0]
            return owner, [value[0] for value in matches.values() if value[0] != owner]
        subjects = [value[0] for value in matches.values() if "subject" in value[1]]
        if len(subjects) == 1:
            owner = subjects[0]
            return owner, [value[0] for value in matches.values() if value[0] != owner]
        if matches:
            return None
        if len(text_matches) == 1:
            return next(iter(text_matches.values())), []
        return None

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
    def _entity_registry(entities: Iterable[EntityRecord]) -> str:
        lines = []
        for entity in sorted(entities, key=lambda item: item.entity_id):
            if entity.status != "active":
                continue
            aliases = ", ".join(entity.aliases) or "none"
            lines.append(
                f"- id={entity.entity_id}; type={entity.entity_type}; "
                f"title={entity.title!r}; aliases={aliases}"
            )
        return "\n".join(lines) or "- none yet"

    @staticmethod
    def _format_evidence(aliases: dict[str, ClaimEvidence]) -> str:
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
                f"temporal_status={claim.temporal_status}; source_type={item.source.source_type}; "
                f"evidence_modality={claim.evidence_modality}\nclaim={claim.text}\n"
                f"qualifiers={facets or 'none'}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _has_named_participant_scope(source: SourceDocument) -> bool:
        if source.source_type not in {"multi_party_conversation", "meeting_transcript"}:
            return False
        names = {
            str(value).strip().lower()
            for value in [*source.participants, *(segment.speaker for segment in source.segments)]
            if value
        }
        return bool(names - {"user", "assistant", "system", "tool", "unknown"})

    @staticmethod
    def _failure(item: ClaimEvidence, reason: str) -> RoutingFailure:
        return RoutingFailure(item.claim.claim_id, item.raw_log_entry_id, reason)

    def _fail_batch(self, evidence: Iterable[ClaimEvidence], reason: str) -> RoutingResult:
        return RoutingResult(failures=[self._failure(item, reason) for item in evidence])


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
