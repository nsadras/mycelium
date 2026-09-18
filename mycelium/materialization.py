"""Deterministic wiki projection of independent, source-cited view items."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import cast

from mycelium.artifacts import ArtifactStore, ConsolidatedFact, EntityRecord, MemoryClaim
from mycelium.config import Config
from mycelium.artifact_integrity import cited_source_segments
from mycelium.models import Edge, UpdateLogEntry, WikiPage
from mycelium.ontology import ENTITY_ONTOLOGY, PageType
from mycelium.page_reviews import reviewed_page_exclusions
from mycelium.store import WikiStore
from mycelium.temporal import temporal_records

INDEX_GROUPS = tuple((definition.key, definition.plural_label) for definition in ENTITY_ONTOLOGY)


def sections_markdown(
    sections: list[dict],
    seen_fact_ids: set[str] | None = None,
) -> str:
    """Render sections, optionally deduplicating the same view item across prompt pages."""
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
        detail_lines: list[str] = []
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
            fact_id = item.get("fact_id")
            if seen_fact_ids is not None and fact_id:
                if fact_id in seen_fact_ids:
                    continue
                seen_fact_ids.add(fact_id)
            qualifiers = item.get("qualifiers", [])
            suffix = f" _({'; '.join(qualifiers)})_" if qualifiers else ""
            linked = " ".join(
                f"[[{link['slug']}]]" for link in item.get("links", [])
            )
            link_suffix = f" — {linked}" if linked else ""
            destination = detail_lines if item.get("prominence") == "detail" else item_lines
            destination.append(
                f"- {item['text']}{link_suffix}{suffix}"
                + evidence_suffix(item.get("sources", []))
            )
        if detail_lines:
            item_lines.extend(["", "<details>", "<summary>Supporting detail</summary>", "", *detail_lines, "", "</details>"])
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


class PageMaterializer:
    def __init__(self, wiki: WikiStore, artifacts: ArtifactStore, config: Config):
        self.wiki, self.artifacts, self.config = wiki, artifacts, config

    def regenerate(self, entity_ids: set[str]) -> MaterializationResult:
        # Projection is mechanical. No semantic rewriting occurs when support changes.
        result = MaterializationResult()
        entities = {e.entity_id: e for e in self.artifacts.list_entities()}
        claims = {c.claim_id: c for c in self.artifacts.list_claims()
                  if c.status == "active" and c.dream_disposition != "excluded_source_policy"}
        facts = sorted(self.artifacts.list_consolidated_facts(), key=lambda f: (f.created_at, f.fact_id))
        existing = {p.entity_id: p for p in self.wiki.list_all()}
        self._retracted_source_ids = {s.source_id for s in self.artifacts.list_sources() if s.status == "retracted"}
        self._identity_reviews = defaultdict(list)
        for decision in self.artifacts.list_entity_resolution_decisions(review_state="review_required"):
            for cid in decision.supporting_claim_ids:
                self._identity_reviews[cid].append(decision.decision_id)
        pending = defaultdict(set)
        for proposal in self.artifacts.list_reconsolidation_proposals(status="pending"):
            for cid in [*proposal.incoming_claim_ids, *proposal.target_claim_ids]:
                pending[cid].add(proposal.proposal_id)
        exclusions, _ = reviewed_page_exclusions(self.artifacts, claims)
        by_entity = defaultdict(list)
        by_claim = defaultdict(set)
        for fact in facts:
            endpoints = {fact.owner_entity_id, *fact.linked_entity_ids}
            for cid in fact.member_claim_ids:
                by_claim[cid].update(endpoints)
            # A synthesis with withdrawn support is hidden as a whole; the retained
            # statements and manual item remain available for inspection/review.
            if not all(cid in claims for cid in fact.member_claim_ids):
                continue
            if entities[fact.owner_entity_id].status != "active":
                continue
            for eid in endpoints:
                if entities[eid].status == "active" and not any(
                    eid in exclusions.get(cid, set()) for cid in fact.member_claim_ids
                ):
                    by_entity[eid].append(fact)
        projected = set(by_entity)
        if "you" in entities and entities["you"].status == "active":
            projected.add("you")
        changed_targets = projected ^ existing.keys()
        changed_targets.update(eid for eid in projected & existing.keys()
                               if entities[eid].title != existing[eid].title
                               or entities[eid].slug != existing[eid].slug)
        affected = set(entity_ids) | changed_targets
        # Follow shared evidence and page links once to their complete connected set.
        while True:
            expanded = affected | {eid for group in by_claim.values() if group & affected for eid in group}
            if expanded == affected:
                break
            affected = expanded
        if "you" in entities:
            affected.add("you")
        with self.artifacts.db.transaction():
            for eid in sorted(affected & entities.keys()):
                entity, old = entities[eid], existing.get(eid)
                if eid not in projected:
                    if old is not None:
                        result.deleted_slugs.add(old.slug)
                        self.wiki.delete(old.slug)
                    if entity.materialization_state != "provisional":
                        entity = replace(entity, materialization_state="provisional")
                        result.entities[eid] = entity
                        self.artifacts.save_entity(entity)
                    continue
                if entity.materialization_state != "materialized":
                    entity = replace(entity, materialization_state="materialized")
                    result.entities[eid] = entity
                    self.artifacts.save_entity(entity)
                groups = defaultdict(list)
                for fact in by_entity[eid]:
                    groups[fact.section_key].append(fact)
                sections = [{"key": heading, "title": heading, "items": self._fact_items(
                    group, entities, claims, page_entity_id=eid,
                    projected_entity_ids=projected, pending_proposals_by_claim=pending)}
                    for heading, group in groups.items()]
                if eid == "you":
                    links = self._memory_map(entities, projected)
                    if links:
                        sections.append({"key": "memory_map", "title": "Memory Map", "items": links})
                source_ids = sorted({p.raw_log_entry_id or p.source_id for fact in by_entity[eid]
                                     for cid in fact.member_claim_ids for p in claims[cid].provenance})
                related = sorted({other for fact in by_entity[eid]
                                  for other in [fact.owner_entity_id, *fact.linked_entity_ids]
                                  if other in projected and other != eid})
                now = datetime.now()
                page = WikiPage(slug=entity.slug, title=entity.title, content=sections_markdown(sections),
                    created=old.created if old else now, last_updated=now,
                    version=old.version if old else 1, page_type=cast(PageType, entity.entity_type),
                    tags=[], related=[Edge(target=entities[x].slug, relation="informs") for x in related],
                    source_log_entries=source_ids, update_log=list(old.update_log) if old else [],
                    entity_id=eid, entity_status=entity.status, aliases=entity.aliases, sections=sections)
                if old is not None and self._same_page(old, page) and old.slug == page.slug:
                    continue
                if old is None:
                    result.created_slugs.add(page.slug)
                else:
                    page.version += 1
                    result.updated_slugs.add(page.slug)
                    if old.slug != page.slug:
                        result.deleted_slugs.add(old.slug)
                        self.wiki.delete(old.slug)
                page.update_log.append(UpdateLogEntry(version=page.version, date=now,
                    session_id="system", trigger="dream", reason="Regenerated cited memory views"))
                result.changed_pages[page.slug] = page
                self.wiki.save(page)
            self.rebuild_index(result.changed_pages, result.deleted_slugs)
        return result

    def regenerate_all(self) -> MaterializationResult:
        return self.regenerate({e.entity_id for e in self.artifacts.list_entities()})

    def _fact_items(
        self,
        values: list[ConsolidatedFact],
        entities: dict[str, EntityRecord],
        claims_by_id: dict[str, MemoryClaim],
        *,
        page_entity_id: str,
        projected_entity_ids: set[str],
        pending_proposals_by_claim: dict[str, set[str]],
    ) -> list[dict]:
        if not values:
            return []
        items = []
        retracted_source_ids = self._retracted_source_ids

        for fact in sorted(values, key=lambda f: (f.created_at, f.fact_id)):
            members = [
                claims_by_id[claim_id] for claim_id in fact.member_claim_ids
                if claim_id in claims_by_id
            ]
            if not members:
                continue
            for member in members:
                cited_source_segments(self.artifacts, member)
            claim = members[0]
            member_ids = list(fact.member_claim_ids)
            review_ids = sorted({proposal_id for claim_id in member_ids
                                 for proposal_id in pending_proposals_by_claim.get(claim_id, set())})
            identity_reviews = sorted({did for cid in member_ids
                                       for did in self._identity_reviews.get(cid, [])})
            uncertain = bool(review_ids or identity_reviews)
            links = sorted(({fact.owner_entity_id, *fact.linked_entity_ids} - {page_entity_id})
                           & projected_entity_ids)
            qualifiers = []
            if claim.evidence_modality == "tool":
                qualifiers.append("external research")
            if review_ids:
                qualifiers.append("unresolved accounts; optional review")
            if identity_reviews:
                qualifiers.append("identity uncertain; optional review")
            retracted_sources = sorted({p.source_id for member in members for p in member.provenance
                                        if p.source_id in retracted_source_ids})
            if retracted_sources:
                qualifiers.append("supporting evidence retracted; interpretation uncertain")
                uncertain = True
            temporal_evidence = [
                dict(temporal)
                for member in members
                for temporal in temporal_records(member.facets)
                if temporal
            ]
            event_times = sorted({
                str(temporal["start"])
                for temporal in temporal_evidence
                if temporal.get("role") == "event_time" and temporal.get("start")
            })
            for temporal in temporal_evidence:
                start = str(temporal.get("start") or "")
                end = str(temporal.get("end") or start)
                if not start:
                    continue
                normalized = start if not end or end == start else f"{start}–{end}"
                role = str(temporal.get("role") or "date").replace("_", " ")
                qualifiers.append(f"{role} for {temporal['target']}: {normalized}")
            sources = [
                {
                    "source_id": provenance.source_id,
                    "segment_ids": list(provenance.segment_ids),
                    "raw_log_entry_id": provenance.raw_log_entry_id,
                    "speaker": provenance.speaker,
                }
                for member in members for provenance in member.provenance
            ]
            items.append({
                "kind": "fact",
                "fact_id": fact.fact_id,
                "text": fact.text,
                "claim_ids": member_ids,
                "synthesis_origin": fact.synthesis_origin,
                "memory_state": fact.state,
                "prominence": fact.prominence,
                "synthesis_confidence": fact.confidence,
                "synthesis_reason": fact.reason,
                "manual_text": fact.manual_text,
                "canonical_owner_entity_ids": [fact.owner_entity_id],
                "canonical_linked_entity_ids": list(fact.linked_entity_ids),
                "projection": "canonical" if page_entity_id == fact.owner_entity_id else "shared_endpoint",
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
                "authoritative": not uncertain,
                "reconciliation_proposal_ids": review_ids,
                "identity_review_ids": identity_reviews,
            })
        return items

    @staticmethod
    def _memory_map(entities: dict[str, EntityRecord], projected_entity_ids: set[str]) -> list[dict]:
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
            and entity.entity_id in projected_entity_ids
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
