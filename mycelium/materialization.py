"""Deterministic typed wiki projection from entities, claims, and placements."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal, cast

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ConsolidatedFact,
    EntityRecord,
    MemoryClaim,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimRoute, placement_from_route
from mycelium.models import Edge, UpdateLogEntry, WikiPage
from mycelium.ontology import ENTITY_ONTOLOGY, PageType, section_pairs
from mycelium.projection import display_claim_text
from mycelium.store import WikiStore
from mycelium.temporal import temporal_record


INDEX_GROUPS: tuple[tuple[PageType, str], ...] = tuple(
    (cast(PageType, definition.key), definition.plural_label)
    for definition in ENTITY_ONTOLOGY
)


def sections_markdown(
    sections: list[dict],
    seen_claim_ids: set[str] | None = None,
) -> str:
    """Render sections, optionally deduplicating shared statements across prompt pages."""
    lines: list[str] = []
    evidence_labels: dict[tuple[str, tuple[str, ...]], str] = {}

    def evidence_suffix(sources: list[dict]) -> str:
        labels: list[str] = []
        for source in sources:
            key = (
                str(source["source_id"]),
                tuple(str(value) for value in source.get("segment_ids", [])),
            )
            label = evidence_labels.setdefault(key, f"e{len(evidence_labels) + 1}")
            if label not in labels:
                labels.append(label)
        return "".join(f" [^{label}]" for label in labels)

    for section in sections:
        item_lines: list[str] = []
        for item in section["items"]:
            if item["kind"] == "link":
                item_lines.append(f"- [[{item['slug']}]] — {item['title']}")
                continue
            if item["kind"] == "encounter":
                item_lines.append(
                    f"- {item['text']}"
                    + evidence_suffix([{
                        "source_id": item["source_id"],
                        "segment_ids": [],
                    }])
                )
                continue
            claim_ids = set(item.get("claim_ids", []))
            if seen_claim_ids is not None:
                if claim_ids and claim_ids <= seen_claim_ids:
                    continue
                seen_claim_ids.update(claim_ids)
            qualifiers = item.get("qualifiers", [])
            suffix = f" _({'; '.join(qualifiers)})_" if qualifiers else ""
            linked = " ".join(
                f"[[{link['slug']}]]" for link in item.get("links", [])
            )
            link_suffix = f" — {linked}" if linked else ""
            item_lines.append(
                f"- {item['text']}{link_suffix}{suffix}"
                + evidence_suffix(item.get("sources", []))
            )
        if not item_lines:
            continue
        if lines:
            lines.append("")
        lines.extend([f"## {section['title']}", "", *item_lines])
    if evidence_labels:
        lines.extend(["", "## Sources", ""])
        for (source_id, segment_ids), label in evidence_labels.items():
            segments = " · ".join(f"`{segment_id}`" for segment_id in segment_ids)
            suffix = f" · {segments}" if segments else ""
            lines.append(f"[^{label}]: `{source_id}`{suffix}")
    return "\n".join(lines).strip()


@dataclass
class MaterializationResult:
    changed_pages: dict[str, WikiPage] = field(default_factory=dict)
    created_slugs: set[str] = field(default_factory=set)
    updated_slugs: set[str] = field(default_factory=set)
    deleted_slugs: set[str] = field(default_factory=set)
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    placements: dict[str, ClaimPlacement] = field(default_factory=dict)
    facts: dict[str, ConsolidatedFact] = field(default_factory=dict)
    deleted_fact_ids: set[str] = field(default_factory=set)


class PageMaterializer:
    def __init__(self, wiki: WikiStore, artifacts: ArtifactStore, config: Config):
        self.wiki = wiki
        self.artifacts = artifacts
        self.config = config

    def stage(
        self,
        routes: list[ClaimRoute],
        new_entities: list[EntityRecord] | None = None,
        facts: list[ConsolidatedFact] | None = None,
        deleted_fact_ids: set[str] | None = None,
        placement_overrides: list[ClaimPlacement] | None = None,
    ) -> MaterializationResult:
        result = MaterializationResult()
        result.entities = {entity.entity_id: entity for entity in new_entities or []}
        now = datetime.now().astimezone().isoformat()
        for route in routes:
            result.placements[route.claim_id] = placement_from_route(route, now=now)
        result.placements.update({
            placement.claim_id: placement for placement in placement_overrides or []
        })
        result.facts = {fact.fact_id: fact for fact in facts or []}
        result.deleted_fact_ids = set(deleted_fact_ids or ())
        affected = {
            entity_id
            for placement in result.placements.values()
            for entity_id in [placement.owner_entity_id, *placement.linked_entity_ids]
            if entity_id
        }
        # A removed destination must be regenerated too, not just the new destinations.
        affected.update(
            entity_id
            for claim_id in result.placements
            for prior in [self.artifacts.placement_for_claim(claim_id)] if prior is not None
            for entity_id in [prior.owner_entity_id, *prior.page_sections] if entity_id
        )
        affected.update(fact.owner_entity_id for fact in result.facts.values())
        deleted_facts = {
            fact.fact_id: fact for fact in self.artifacts.list_consolidated_facts()
            if fact.fact_id in result.deleted_fact_ids
        }
        affected.update(fact.owner_entity_id for fact in deleted_facts.values())
        existing_entities = {
            entity.entity_id: entity for entity in self.artifacts.list_entities()
        }
        for entity_id in affected:
            if entity_id not in result.entities and entity_id in existing_entities:
                result.entities[entity_id] = replace(
                    existing_entities[entity_id], updated_at=now
                )
        if result.entities:
            affected.update(result.entities)
            affected.add("you")
        self._stage_entities(result, affected)
        return result

    def persist(self, result: MaterializationResult) -> None:
        for entity in result.entities.values():
            self.artifacts.save_entity(entity)
        for placement in result.placements.values():
            self.artifacts.save_placement(placement)
        for fact_id in result.deleted_fact_ids:
            self.artifacts.delete_consolidated_fact(fact_id)
        for fact in result.facts.values():
            self.artifacts.save_consolidated_fact(fact)
        for slug in result.deleted_slugs:
            self.wiki.delete(slug)
        for page in result.changed_pages.values():
            self.wiki.save(page)
        self.rebuild_index(result.changed_pages, result.deleted_slugs)

    def regenerate(self, entity_ids: set[str]) -> MaterializationResult:
        result = MaterializationResult()
        self._stage_entities(result, entity_ids)
        self.persist(result)
        return result

    def regenerate_all(self) -> MaterializationResult:
        return self.regenerate({
            entity.entity_id for entity in self.artifacts.list_entities()
            if entity.status != "merged" and entity.materialization_state == "materialized"
        })

    def _stage_entities(
        self, result: MaterializationResult, entity_ids: set[str]
    ) -> None:
        entities = {entity.entity_id: entity for entity in self.artifacts.list_entities()}
        entities.update(result.entities)
        placements = {
            placement.claim_id: placement for placement in self.artifacts.list_placements()
        }
        placements.update(result.placements)
        all_claims = {
            claim.claim_id: claim for claim in self.artifacts.list_claims()
        }
        claims = {
            claim_id: claim
            for claim_id, claim in all_claims.items()
            if claim.status == "active"
        }
        pending_proposals_by_claim: dict[str, set[str]] = defaultdict(set)
        for proposal in self.artifacts.list_reconsolidation_proposals(status="pending"):
            for claim_id in {
                *proposal.incoming_claim_ids,
                *proposal.target_claim_ids,
            }:
                pending_proposals_by_claim[claim_id].add(proposal.proposal_id)
        encounters = self.artifacts.list_encounters()
        facts = {
            fact.fact_id: fact
            for fact in self.artifacts.list_consolidated_facts()
            if fact.fact_id not in result.deleted_fact_ids
        }
        facts.update(result.facts)
        entity_ids = self._expand_placement_endpoints(
            entity_ids, all_claims, placements, entities
        )

        for entity_id in sorted(entity_ids):
            entity = entities.get(entity_id)
            if (
                entity is None
                or entity.status != "active"
            ):
                continue
            entity_claims = []
            for placement in placements.values():
                claim = claims.get(placement.claim_id)
                if (
                    claim is None
                    or placement.status != "placed"
                ):
                    continue
                page_placement = self._page_placement(
                    entity_id, claim, placement, entities
                )
                if page_placement is not None:
                    entity_claims.append((claim, page_placement))
            entity_facts = []
            for fact in facts.values():
                page_facts = self._page_facts(
                    entity_id, fact, claims, placements, entities
                )
                entity_facts.extend(page_facts)
            existing = self._existing_page(entity)
            if not entity_facts and entity_id != "you":
                result.entities[entity_id] = replace(entity, materialization_state="provisional")
                entities[entity_id] = result.entities[entity_id]
                if existing is not None:
                    result.deleted_slugs.add(entity.slug)
                continue
            if entity.materialization_state != "materialized":
                entity = replace(entity, materialization_state="materialized")
                result.entities[entity_id] = entities[entity_id] = entity
            page = self._build_page(
                entity, entity_claims, entities, placements,
                pending_proposals_by_claim,
                encounters, entity_facts, claims, existing,
            )
            if existing is None:
                page.update_log = [UpdateLogEntry(
                    version=1,
                    date=datetime.now(),
                    session_id="system",
                    trigger="dream",
                    reason="Initial entity-owned deterministic projection",
                )]
                result.changed_pages[entity.slug] = page
                result.created_slugs.add(entity.slug)
            elif not self._same_page(existing, page):
                page.created = existing.created
                page.version = existing.version + 1
                page.update_log = [*existing.update_log, UpdateLogEntry(
                    version=page.version,
                    date=datetime.now(),
                    session_id="system",
                    trigger="dream",
                    reason="Regenerated entity-owned deterministic projection",
                )]
                result.changed_pages[entity.slug] = page
                result.updated_slugs.add(entity.slug)

    @classmethod
    def _expand_placement_endpoints(
        cls,
        entity_ids: set[str],
        claims: dict[str, MemoryClaim],
        placements: dict[str, ClaimPlacement],
        entities: dict[str, EntityRecord],
    ) -> set[str]:
        """Regenerate every selected view when a canonical statement changes."""
        expanded = set(entity_ids)
        for placement in placements.values():
            claim = claims.get(placement.claim_id)
            if claim is None or placement.status != "placed":
                continue
            endpoints = {placement.owner_entity_id, *placement.page_sections} - {None}
            if endpoints & expanded:
                expanded.update(endpoints)
        return expanded

    @classmethod
    def _page_placement(
        cls,
        entity_id: str,
        claim: MemoryClaim,
        placement: ClaimPlacement,
        entities: dict[str, EntityRecord],
    ) -> ClaimPlacement | None:
        if placement.owner_entity_id == entity_id:
            return placement
        if entity_id in placement.page_sections:
            return replace(
                placement,
                owner_entity_id=entity_id,
                section_key=placement.page_sections[entity_id],
                linked_entity_ids=sorted({placement.owner_entity_id, *placement.page_sections} - {entity_id, None}),
            )
        return None

    @classmethod
    def _page_facts(
        cls,
        entity_id: str,
        fact: ConsolidatedFact,
        claims: dict[str, MemoryClaim],
        placements: dict[str, ClaimPlacement],
        entities: dict[str, EntityRecord],
    ) -> list[ConsolidatedFact]:
        if fact.owner_entity_id == entity_id:
            return [fact] if set(fact.member_claim_ids) <= claims.keys() else []
        grouped: dict[str, list[str]] = defaultdict(list)
        for claim_id in fact.member_claim_ids:
            placement = placements.get(claim_id)
            if claim_id in claims and placement and placement.status == "placed":
                section = placement.page_sections.get(entity_id)
                if section:
                    grouped[section].append(claim_id)
        views = []
        for section, member_ids in grouped.items():
            complete = set(member_ids) == set(fact.member_claim_ids)
            # A synthesized group may contain claims not selected for this page. In that
            # case display only its selected canonical statements, never the whole group.
            views.append(replace(
                fact, owner_entity_id=entity_id, section_key=section,
                member_claim_ids=member_ids,
                text=fact.text if complete else " ".join(display_claim_text(claims[c]) for c in member_ids),
                linked_entity_ids=sorted({fact.owner_entity_id, *(
                    e for c in member_ids for e in placements[c].page_sections
                )} - {entity_id}),
                synthesis_origin=fact.synthesis_origin if complete else "claim",
                manual_text=fact.manual_text if complete else False,
            ))
        return views

    def _existing_page(self, entity: EntityRecord) -> WikiPage | None:
        if entity.status == "archived":
            return None
        if not self.wiki.exists(entity.slug):
            return None
        page = self.wiki.get(entity.slug)
        if not page.entity_id:
            raise ValueError(
                "Wiki uses the pre-entity schema. Clear the derived wiki and rebuild from claims."
            )
        if page.entity_id != entity.entity_id:
            raise ValueError(f"Wiki slug {entity.slug!r} belongs to another entity")
        return page

    def _build_page(
        self,
        entity: EntityRecord,
        owned: list[tuple[MemoryClaim, ClaimPlacement]],
        entities: dict[str, EntityRecord],
        placements: dict[str, ClaimPlacement],
        pending_proposals_by_claim: dict[str, set[str]],
        encounters: list,
        facts: list[ConsolidatedFact],
        claims_by_id: dict[str, MemoryClaim],
        existing: WikiPage | None,
    ) -> WikiPage:
        sections = self._sections(
            entity, owned, entities, placements, pending_proposals_by_claim,
            encounters,
            facts, claims_by_id,
        )
        claims = [claim for claim, _ in owned]
        source_ids = sorted({
            provenance.raw_log_entry_id or provenance.source_id
            for claim in claims for provenance in claim.provenance
        })
        related_ids = sorted({
            linked_id for _, placement in owned for linked_id in placement.linked_entity_ids
            if linked_id in entities and entities[linked_id].status == "active"
        } | {
            placement.owner_entity_id
            for placement in placements.values()
            if entity.entity_id in placement.linked_entity_ids
            and placement.owner_entity_id in entities
            and entities[placement.owner_entity_id].status == "active"
        })
        now = datetime.now()
        return WikiPage(
            slug=entity.slug,
            title=entity.title,
            content=sections_markdown(sections),
            created=existing.created if existing else now,
            last_updated=now,
            version=existing.version if existing else 1,
            page_type=cast(PageType, entity.entity_type),
            tags=[],
            related=[
                Edge(target=entities[entity_id].slug, relation="informs")
                for entity_id in related_ids
            ],
            source_log_entries=source_ids,
            update_log=list(existing.update_log) if existing else [],
            entity_id=entity.entity_id,
            entity_status=cast(Literal["active", "archived", "merged"], entity.status),
            aliases=list(entity.aliases),
            sections=sections,
        )

    def _sections(
        self,
        entity: EntityRecord,
        owned: list[tuple[MemoryClaim, ClaimPlacement]],
        entities: dict[str, EntityRecord],
        placements: dict[str, ClaimPlacement],
        pending_proposals_by_claim: dict[str, set[str]],
        encounters: list,
        facts: list[ConsolidatedFact],
        claims_by_id: dict[str, MemoryClaim],
    ) -> list[dict]:
        grouped: dict[str, list[ConsolidatedFact]] = defaultdict(list)
        review: list[ConsolidatedFact] = []
        for fact in facts:
            if set(fact.member_claim_ids) & set(pending_proposals_by_claim):
                review.append(fact)
            else:
                grouped[fact.section_key].append(fact)

        encounter_items: list[dict] = []
        if entity.entity_type == "person":
            represented_source_ids = {
                provenance.source_id for claim, _ in owned for provenance in claim.provenance
            }
            for encounter in encounters:
                if (
                    encounter.entity_id != entity.entity_id
                    or encounter.source_id in represented_source_ids
                ):
                    continue
                date = str(encounter.occurred_at or "").split("T", 1)[0]
                context = encounter.title or "a recorded meeting"
                date_suffix = f" on {date}" if date else ""
                encounter_items.append({
                    "kind": "encounter",
                    "encounter_id": encounter.encounter_id,
                    "text": f"Participated in {context}{date_suffix}.",
                    "source_id": encounter.source_id,
                    "raw_log_entry_id": encounter.raw_log_entry_id,
                    "event_time": date or None,
                })

        sections: list[dict] = []
        for key, title in section_pairs(entity.entity_type):
            if key == "memory_map" and entity.entity_type == "you":
                links = self._memory_map(entities)
                if links:
                    sections.append({"key": key, "title": title, "items": links})
                continue
            values = (
                [*grouped.get(key, []), *review]
                if key == "needs_review" else grouped.get(key, [])
            )
            items = self._fact_items(
                values,
                entities,
                claims_by_id,
                pending=(key == "needs_review"),
                page_entity_id=entity.entity_id,
                canonical_placements=placements,
                chronological=(key == "timeline"),
                pending_proposals_by_claim=pending_proposals_by_claim,
            )
            if key == "timeline" and encounter_items:
                items.extend(encounter_items)
            if key == "timeline":
                items.sort(key=lambda item: (
                    not bool(item.get("event_time")),
                    str(item.get("event_time") or ""),
                    str(item.get("fact_id") or item.get("encounter_id") or ""),
                ))
            if items:
                sections.append({"key": key, "title": title, "items": items})
        return sections

    def _fact_items(
        self,
        values: list[ConsolidatedFact],
        entities: dict[str, EntityRecord],
        claims_by_id: dict[str, MemoryClaim],
        *,
        pending: bool,
        page_entity_id: str,
        canonical_placements: dict[str, ClaimPlacement],
        chronological: bool,
        pending_proposals_by_claim: dict[str, set[str]],
    ) -> list[dict]:
        if not values:
            return []
        items = []

        def fact_order(value: ConsolidatedFact) -> tuple:
            if not chronological:
                return (value.created_at, value.fact_id)
            starts = sorted(
                str(temporal["start"])
                for claim_id in value.member_claim_ids
                if claim_id in claims_by_id
                for temporal in [temporal_record(claims_by_id[claim_id].facets)]
                if temporal and temporal.get("start")
            )
            return (
                not bool(starts),
                starts[0] if starts else value.created_at,
                value.fact_id,
            )

        for fact in sorted(values, key=fact_order):
            members = [
                claims_by_id[claim_id] for claim_id in fact.member_claim_ids
                if claim_id in claims_by_id
            ]
            if not members:
                continue
            claim = members[0]
            member_ids = list(fact.member_claim_ids)
            links = sorted({
                linked_id for linked_id in fact.linked_entity_ids
                if linked_id in entities and entities[linked_id].status == "active"
            })
            qualifiers = []
            if claim.evidence_modality == "tool":
                qualifiers.append("external research")
            if pending:
                qualifiers.append("pending reconciliation")
            temporal_evidence = [
                dict(temporal)
                for member in members
                for temporal in [temporal_record(member.facets)]
                if temporal
            ]
            event_times = sorted({
                str(temporal["start"])
                for temporal in temporal_evidence
                if temporal.get("start")
            })
            for temporal in temporal_evidence:
                start = str(temporal.get("start") or "")
                end = str(temporal.get("end") or start)
                if not start:
                    continue
                normalized = start if not end or end == start else f"{start}–{end}"
                role = str(temporal.get("role") or "date").replace("_", " ")
                qualifiers.append(f"{role}: {normalized}")
            sources = [
                {
                    "source_id": provenance.source_id,
                    "segment_ids": list(provenance.segment_ids),
                    "raw_log_entry_id": provenance.raw_log_entry_id,
                    "speaker": provenance.speaker,
                }
                for member in members for provenance in member.provenance
            ]
            canonical_owner_ids = sorted({
                cast(str, canonical_placements[claim_id].owner_entity_id)
                for claim_id in member_ids
                if claim_id in canonical_placements
                and canonical_placements[claim_id].owner_entity_id
            })
            canonical_linked_ids = sorted({
                linked_id
                for claim_id in member_ids
                if claim_id in canonical_placements
                for linked_id in canonical_placements[claim_id].linked_entity_ids
            })
            items.append({
                "kind": "fact",
                "fact_id": fact.fact_id,
                "text": fact.text,
                "claim_ids": member_ids,
                "synthesis_origin": fact.synthesis_origin,
                "memory_state": fact.state,
                "synthesis_confidence": fact.confidence,
                "synthesis_reason": fact.reason,
                "manual_text": fact.manual_text,
                "canonical_owner_entity_ids": canonical_owner_ids,
                "canonical_linked_entity_ids": canonical_linked_ids,
                "relationship_kind": (
                    "project_role"
                    if any(
                        canonical_placements[claim_id].relationship_kind
                        == "project_role"
                        for claim_id in member_ids
                        if claim_id in canonical_placements
                    )
                    else None
                ),
                "projection": (
                    "shared_endpoint"
                    if any(owner_id != page_entity_id for owner_id in canonical_owner_ids)
                    else "canonical"
                ),
                "qualifiers": list(dict.fromkeys(qualifiers)),
                "evidence_modality": claim.evidence_modality,
                "event_time": event_times[0] if event_times else None,
                "temporal_evidence": temporal_evidence,
                "sources": sources,
                "links": [
                    {
                        "entity_id": linked_id,
                        "slug": entities[linked_id].slug,
                        "title": entities[linked_id].title,
                    }
                    for linked_id in links
                ],
                "authoritative": not pending,
                "reconciliation_proposal_ids": sorted({
                    proposal_id
                    for claim_id in member_ids
                    for proposal_id in pending_proposals_by_claim.get(claim_id, set())
                }),
            })
        return items

    @staticmethod
    def _memory_map(entities: dict[str, EntityRecord]) -> list[dict]:
        return [
            {
                "kind": "link",
                "entity_id": entity.entity_id,
                "slug": entity.slug,
                "title": entity.title,
                "entity_type": entity.entity_type,
            }
            for entity in sorted(entities.values(), key=lambda value: (value.entity_type, value.title.lower()))
            if entity.entity_id != "you"
            and entity.status == "active"
            and entity.materialization_state == "materialized"
        ]

    def rebuild_index(
        self,
        changed_pages: dict[str, WikiPage],
        deleted_slugs: set[str] | None = None,
    ) -> None:
        pages = {page.slug: page for page in self.wiki.list_all()}
        pages.update(changed_pages)
        for slug in deleted_slugs or set():
            pages.pop(slug, None)
        lines = [
            "# Wiki Index",
            "",
            f"_last updated: {datetime.now().isoformat(timespec='seconds')}_",
        ]
        for page_type, label in INDEX_GROUPS:
            group = sorted(
                (
                    page for page in pages.values()
                    if page.page_type == page_type and page.entity_status == "active"
                ),
                key=lambda page: (page.title.lower(), page.slug),
            )
            if not group:
                continue
            lines.extend(["", f"## {label}"])
            lines.extend(f"- [[{page.slug}]]: {self._summary(page)}" for page in group)
        self.wiki.save_index("\n".join(lines) + "\n")

    @staticmethod
    def _same_page(left: WikiPage, right: WikiPage) -> bool:
        return (
            " ".join(left.content.split()) == " ".join(right.content.split())
            and left.entity_id == right.entity_id
            and left.title == right.title
            and left.page_type == right.page_type
            and left.entity_status == right.entity_status
            and left.aliases == right.aliases
            and left.sections == right.sections
            and left.related == right.related
            and left.source_log_entries == right.source_log_entries
        )

    @staticmethod
    def _summary(page: WikiPage) -> str:
        body = next(
            (
                str(item.get("text") or item.get("title") or "")
                for section in page.sections for item in section.get("items", [])
                if item.get("text") or item.get("title")
            ),
            page.title,
        )
        body = re.sub(r"\s+", " ", body).strip()
        return f"{page.title} - {body[:137] + '...' if len(body) > 140 else body}"
