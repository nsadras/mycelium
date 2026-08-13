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
    EntityRecord,
    MemoryClaim,
)
from mycelium.config import Config
from mycelium.consolidation import ClaimRoute, placement_from_route
from mycelium.models import Edge, PAGE_SECTION_KEYS, PageType, UpdateLogEntry, WikiPage
from mycelium.projection import (
    compact_display_claims,
    compact_record_qualifiers,
    display_claim_text,
    project_claim,
)
from mycelium.store import WikiStore


INDEX_GROUPS: tuple[tuple[PageType, str], ...] = (
    ("you", "You"),
    ("project", "Projects"),
    ("person", "People"),
    ("topic", "Topics"),
    ("organization", "Organizations"),
    ("place", "Places"),
    ("event", "Events"),
)


@dataclass
class MaterializationResult:
    changed_pages: dict[str, WikiPage] = field(default_factory=dict)
    created_slugs: set[str] = field(default_factory=set)
    updated_slugs: set[str] = field(default_factory=set)
    deleted_slugs: set[str] = field(default_factory=set)
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    placements: dict[str, ClaimPlacement] = field(default_factory=dict)


class PageMaterializer:
    def __init__(self, wiki: WikiStore, artifacts: ArtifactStore, config: Config):
        self.wiki = wiki
        self.artifacts = artifacts
        self.config = config

    def stage(
        self, routes: list[ClaimRoute], new_entities: list[EntityRecord] | None = None
    ) -> MaterializationResult:
        result = MaterializationResult()
        result.entities = {entity.entity_id: entity for entity in new_entities or []}
        now = datetime.now().astimezone().isoformat()
        for route in routes:
            result.placements[route.claim_id] = placement_from_route(route, now=now)
        affected = {
            entity_id
            for placement in result.placements.values()
            for entity_id in [placement.owner_entity_id, *placement.linked_entity_ids]
            if entity_id
        }
        existing_entities = {
            entity.entity_id: entity for entity in self.artifacts.list_entities()
        }
        for entity_id in affected:
            if entity_id not in result.entities and entity_id in existing_entities:
                result.entities[entity_id] = replace(
                    existing_entities[entity_id], updated_at=now
                )
        if result.entities:
            affected.add("you")
        self._stage_entities(result, affected)
        return result

    def persist(self, result: MaterializationResult) -> None:
        for entity in result.entities.values():
            self.artifacts.save_entity(entity)
        for placement in result.placements.values():
            self.artifacts.save_placement(placement)
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
            if entity.status != "merged"
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
        claims = {claim.claim_id: claim for claim in self.artifacts.list_claims(status="active")}
        pending_ids = self.artifacts.pending_reconsolidation_claim_ids()

        for entity_id in sorted(entity_ids):
            entity = entities.get(entity_id)
            if entity is None or entity.status != "active":
                continue
            entity_claims = [
                (claims[placement.claim_id], placement)
                for placement in placements.values()
                if placement.status == "placed"
                and placement.owner_entity_id == entity_id
                and placement.claim_id in claims
                and not claims[placement.claim_id].derivation_operation
            ]
            existing = self._existing_page(entity)
            page = self._build_page(
                entity, entity_claims, entities, placements, pending_ids, existing
            )
            if existing is None:
                page.update_log = [UpdateLogEntry(
                    version=1,
                    date=datetime.now(),
                    session_id="system",
                    trigger="dream",
                    reason="Initial entity-owned deterministic projection",
                    previous_confidence=0.0,
                    new_confidence=page.confidence,
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
                    previous_confidence=existing.confidence,
                    new_confidence=page.confidence,
                )]
                result.changed_pages[entity.slug] = page
                result.updated_slugs.add(entity.slug)

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
        pending_ids: set[str],
        existing: WikiPage | None,
    ) -> WikiPage:
        sections = self._sections(entity, owned, entities, placements, pending_ids)
        claims = [claim for claim, _ in owned]
        confidences = [max(0.0, min(1.0, claim.confidence)) for claim in claims]
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
            content=self._markdown(sections),
            created=existing.created if existing else now,
            last_updated=now,
            version=existing.version if existing else 1,
            confidence=sum(confidences) / len(confidences) if confidences else 1.0,
            importance=max((claim.salience for claim in claims), default=1.0 if entity.entity_type == "you" else 0.5),
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
        pending_ids: set[str],
    ) -> list[dict]:
        grouped: dict[str, list[tuple[MemoryClaim, ClaimPlacement]]] = defaultdict(list)
        review: list[tuple[MemoryClaim, ClaimPlacement]] = []
        for claim, placement in owned:
            if claim.claim_id in pending_ids:
                review.append((claim, placement))
            else:
                grouped[str(placement.section_key)].append((claim, placement))

        sections: list[dict] = []
        for key, title in PAGE_SECTION_KEYS[cast(PageType, entity.entity_type)]:
            if key == "memory_map" and entity.entity_type == "you":
                links = self._memory_map(entities)
                if links:
                    sections.append({"key": key, "title": title, "items": links})
                continue
            if key == "recent_changes" and entity.entity_type == "you":
                links = self._recent_entities(entities)
                if links:
                    sections.append({"key": key, "title": title, "items": links})
                continue
            values = (
                [*grouped.get(key, []), *review]
                if key == "needs_review" else grouped.get(key, [])
            )
            items = self._fact_items(values, entities, pending=(key == "needs_review"))
            if items:
                sections.append({"key": key, "title": title, "items": items})
        return sections

    @staticmethod
    def _fact_items(
        values: list[tuple[MemoryClaim, ClaimPlacement]],
        entities: dict[str, EntityRecord],
        *,
        pending: bool,
    ) -> list[dict]:
        if not values:
            return []
        placement_by_claim = {claim.claim_id: placement for claim, placement in values}
        projected = compact_display_claims([project_claim(claim) for claim, _ in values])
        items = []
        for item in projected:
            claim = item.claim
            member_ids = list(item.claim_ids)
            links = sorted({
                linked_id
                for claim_id in member_ids
                for linked_id in placement_by_claim[claim_id].linked_entity_ids
                if linked_id in entities and entities[linked_id].status == "active"
            })
            qualifiers = compact_record_qualifiers(item, include_date=True)
            if claim.evidence_modality == "tool":
                qualifiers.append("external research")
            if pending:
                qualifiers.append("pending reconciliation")
            sources = [
                {
                    "source_id": provenance.source_id,
                    "segment_ids": list(provenance.segment_ids),
                    "raw_log_entry_id": provenance.raw_log_entry_id,
                    "speaker": provenance.speaker,
                }
                for member in item.members for provenance in member.provenance
            ]
            items.append({
                "kind": "fact",
                "text": display_claim_text(claim),
                "claim_ids": member_ids,
                "qualifiers": list(dict.fromkeys(qualifiers)),
                "evidence_modality": claim.evidence_modality,
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
            if entity.entity_id != "you" and entity.status == "active"
        ]

    @staticmethod
    def _recent_entities(entities: dict[str, EntityRecord]) -> list[dict]:
        values = sorted(
            (
                entity for entity in entities.values()
                if entity.entity_id != "you" and entity.status == "active"
            ),
            key=lambda value: (value.updated_at, value.entity_id),
            reverse=True,
        )[:5]
        return [
            {
                "kind": "link",
                "entity_id": entity.entity_id,
                "slug": entity.slug,
                "title": entity.title,
                "entity_type": entity.entity_type,
            }
            for entity in values
        ]

    @staticmethod
    def _markdown(sections: list[dict]) -> str:
        lines: list[str] = []
        for section in sections:
            if lines:
                lines.append("")
            lines.append(f"## {section['title']}")
            lines.append("")
            for item in section["items"]:
                if item["kind"] == "link":
                    lines.append(f"- [[{item['slug']}]] — {item['title']}")
                    continue
                qualifiers = item.get("qualifiers", [])
                suffix = f" _({'; '.join(qualifiers)})_" if qualifiers else ""
                linked = " ".join(f"[[{link['slug']}]]" for link in item.get("links", []))
                link_suffix = f" — {linked}" if linked else ""
                lines.append(f"- {item['text']}{link_suffix}{suffix}")
        return "\n".join(lines).strip()

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
            and abs(left.confidence - right.confidence) < 1e-9
            and abs(left.importance - right.importance) < 1e-9
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
