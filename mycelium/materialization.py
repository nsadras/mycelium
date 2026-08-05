"""Deterministic wiki materialization stage for routed memory claims."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from mycelium.artifacts import ArtifactStore, MemoryClaim
from mycelium.config import Config
from mycelium.consolidation import ClaimRoute, is_placeholder_slug
from mycelium.models import UpdateLogEntry, WikiPage
from mycelium.projection import (
    ProjectedClaim,
    compact_record_qualifiers,
    display_claim_text,
    partition_claims,
)
from mycelium.store import WikiStore


@dataclass
class MaterializationResult:
    changed_pages: dict[str, WikiPage]
    created_slugs: set[str]
    updated_slugs: set[str]
    claim_pages: dict[str, str]
    deleted_slugs: set[str]


class PageMaterializer:
    def __init__(self, wiki: WikiStore, artifacts: ArtifactStore, config: Config):
        self.wiki = wiki
        self.artifacts = artifacts
        self.config = config

    def stage(self, routes: list[ClaimRoute]) -> MaterializationResult:
        grouped: dict[str, list[ClaimRoute]] = defaultdict(list)
        for route in routes:
            grouped[route.page_slug].append(route)

        changed: dict[str, WikiPage] = {}
        created: set[str] = set()
        updated: set[str] = set()
        claim_pages: dict[str, str] = {}
        now = datetime.now()

        for slug, page_routes in sorted(grouped.items()):
            for route in page_routes:
                claim_pages[route.claim_id] = slug
            claims = self._page_claims(slug, [route.claim_id for route in page_routes])
            if not claims:
                continue
            page_type = self._page_type(page_routes)
            page = self._build_page(slug, page_type, claims, now)
            existing = self.wiki.get(slug) if self.wiki.exists(slug) else None
            if existing is None:
                page.update_log = [UpdateLogEntry(
                    version=1,
                    date=now,
                    session_id="system",
                    trigger="dream",
                    reason="Initial deterministic claim projection",
                    previous_confidence=0.0,
                    new_confidence=page.confidence,
                )]
                changed[slug] = page
                created.add(slug)
                continue

            page.created = existing.created
            page.title = existing.title or page.title
            page.version = existing.version
            page.update_log = list(existing.update_log)
            if self._same_page(existing, page):
                continue
            page.version += 1
            page.update_log.append(UpdateLogEntry(
                version=page.version,
                date=now,
                session_id="system",
                trigger="dream",
                reason="Regenerated deterministic claim projection",
                previous_confidence=existing.confidence,
                new_confidence=page.confidence,
            ))
            changed[slug] = page
            updated.add(slug)

        return MaterializationResult(changed, created, updated, claim_pages, set())

    def persist(self, result: MaterializationResult) -> None:
        for page in result.changed_pages.values():
            self.wiki.save(page)
        for slug in result.deleted_slugs:
            self.wiki.delete(slug)
        for claim_id, page_slug in result.claim_pages.items():
            self.artifacts.set_claim_page(claim_id, page_slug)
        self.rebuild_index(result.changed_pages, result.deleted_slugs)

    def regenerate(self, page_slugs: set[str]) -> MaterializationResult:
        """Regenerate explicit pages after a reviewed canonical-claim change."""
        changed: dict[str, WikiPage] = {}
        created: set[str] = set()
        updated: set[str] = set()
        deleted: set[str] = set()
        now = datetime.now()
        for slug in sorted(page_slugs):
            claims = self._page_claims(slug, [])
            existing = self.wiki.get(slug) if self.wiki.exists(slug) else None
            if not claims:
                if existing is not None:
                    deleted.add(slug)
                continue
            page_type = "topic"
            if existing is not None:
                page_type = next(
                    (
                        tag.removeprefix("page-type-")
                        for tag in existing.tags
                        if tag.startswith("page-type-")
                    ),
                    "topic",
                )
            page = self._build_page(slug, page_type, claims, now)
            if existing is None:
                page.update_log = [UpdateLogEntry(
                    version=1,
                    date=now,
                    session_id="system",
                    trigger="reconsolidation",
                    reason="Initial deterministic claim projection after review",
                    previous_confidence=0.0,
                    new_confidence=page.confidence,
                )]
                changed[slug] = page
                created.add(slug)
                continue
            page.created = existing.created
            page.title = existing.title or page.title
            page.version = existing.version
            page.update_log = list(existing.update_log)
            if self._same_page(existing, page):
                continue
            page.version += 1
            page.update_log.append(UpdateLogEntry(
                version=page.version,
                date=now,
                session_id="system",
                trigger="reconsolidation",
                reason="Regenerated deterministic claim projection after review",
                previous_confidence=existing.confidence,
                new_confidence=page.confidence,
            ))
            changed[slug] = page
            updated.add(slug)
        result = MaterializationResult(changed, created, updated, {}, deleted)
        self.persist(result)
        return result

    def _page_claims(self, page_slug: str, incoming_ids: list[str]) -> list[MemoryClaim]:
        claims = {
            claim.claim_id: claim
            for claim in self.artifacts.claims_for_page(page_slug)
            if claim.status == "active" and not claim.derivation_operation
        }
        for claim_id in incoming_ids:
            try:
                claim = self.artifacts.get_claim(claim_id)
            except FileNotFoundError:
                continue
            if claim.status == "active" and not claim.derivation_operation:
                claims[claim.claim_id] = claim
        return sorted(claims.values(), key=lambda claim: claim.claim_id)

    def _build_page(
        self, slug: str, page_type: str, claims: list[MemoryClaim], now: datetime
    ) -> WikiPage:
        confidences = [max(0.0, min(1.0, claim.confidence)) for claim in claims]
        source_ids = sorted({
            provenance.raw_log_entry_id or provenance.source_id
            for claim in claims
            for provenance in claim.provenance
        })
        return WikiPage(
            slug=slug,
            title=self._title(slug),
            content=self.render(claims),
            created=now,
            last_updated=now,
            version=1,
            confidence=sum(confidences) / len(confidences),
            importance=max((claim.salience for claim in claims), default=0.5),
            tags=[f"page-type-{page_type}"],
            related=[],
            source_log_entries=source_ids,
        )

    def render(self, claims: list[MemoryClaim]) -> str:
        pending_claim_ids = self.artifacts.pending_reconsolidation_claim_ids()
        projected = partition_claims(
            claims, main_claim_limit=self.config.dream.main_page_claim_limit
        )
        lines = self._section("Memory", projected["main"], pending_claim_ids=pending_claim_ids)
        lines.extend(self._section(
            "Timeline", projected["timeline"], date_grouped=True,
            pending_claim_ids=pending_claim_ids,
        ))
        lines.extend(self._section(
            "Detailed Facts", projected["details"], pending_claim_ids=pending_claim_ids
        ))
        lines.extend(self._section(
            "Interaction Archive",
            projected["interaction_archive"],
            date_grouped=True,
            interactions=True,
            pending_claim_ids=pending_claim_ids,
        ))
        return "\n".join(lines).strip()

    @staticmethod
    def _section(
        title: str,
        items: list[ProjectedClaim],
        *,
        date_grouped: bool = False,
        interactions: bool = False,
        pending_claim_ids: set[str] | None = None,
    ) -> list[str]:
        if not items:
            return [f"## {title}"] if title == "Memory" else []
        lines = [f"## {title}"] if title == "Memory" else ["", f"## {title}"]
        grouped: dict[str, list[ProjectedClaim]] = defaultdict(list)
        for item in items:
            heading = (
                "Repeated interactions"
                if interactions and len(item.members) > 1
                else item.date_key if date_grouped else item.bucket
            )
            grouped[heading].append(item)
        seen: set[str] = set()
        for heading in sorted(grouped):
            rendered = []
            for item in grouped[heading]:
                text = display_claim_text(item.claim)
                normalized = " ".join(text.lower().split())
                if normalized in seen:
                    continue
                seen.add(normalized)
                qualifiers = compact_record_qualifiers(item, include_date=not date_grouped)
                if pending_claim_ids and any(
                    claim_id in pending_claim_ids for claim_id in item.claim_ids
                ):
                    qualifiers.append("pending reconciliation")
                suffix = f" _({'; '.join(qualifiers)})_" if qualifiers else ""
                rendered.append(f"- {text}{suffix}")
            if rendered:
                lines.extend(["", f"### {heading}", *rendered])
        return lines

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
            "",
            "## Pages",
        ]
        for page in sorted(
            pages.values(), key=lambda value: (value.slug != "user-profile", value.slug)
        ):
            if is_placeholder_slug(page.slug):
                continue
            lines.append(f"- [[{page.slug}]]: {self._summary(page)}")
        self.wiki.save_index("\n".join(lines) + "\n")

    @staticmethod
    def _page_type(routes: list[ClaimRoute]) -> str:
        values = [route.page_type for route in routes]
        return values[0] if values and all(value == values[0] for value in values) else "topic"

    @staticmethod
    def _title(slug: str) -> str:
        return " ".join(word.capitalize() for word in slug.split("-") if word) or "Untitled"

    @staticmethod
    def _same_page(left: WikiPage, right: WikiPage) -> bool:
        return (
            " ".join(left.content.split()) == " ".join(right.content.split())
            and left.tags == right.tags
            and left.related == right.related
            and left.source_log_entries == right.source_log_entries
            and abs(left.confidence - right.confidence) < 1e-9
            and abs(left.importance - right.importance) < 1e-9
        )

    @staticmethod
    def _summary(page: WikiPage) -> str:
        body = next(
            (
                line.strip().lstrip("- ")
                for line in page.content.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ),
            page.title,
        )
        body = re.sub(r"\[\[([^]]+)]]", r"\1", re.sub(r"\s+", " ", body))
        return f"{page.title} - {body[:137] + '...' if len(body) > 140 else body}"
