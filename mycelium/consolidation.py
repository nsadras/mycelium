"""Claim routing stage for deterministic memory consolidation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from mycelium import prompts
from mycelium.artifacts import MemoryClaim, SourceDocument
from mycelium.ollama import OllamaClient
from mycelium.store import WikiStore
from mycelium.structured_outputs import consolidation_output_model


PLACEHOLDER_SLUG_RE = re.compile(
    r"^(page-slug|new-page|page|topic|untitled)(-\d+|-?[a-z])?$"
)
PAGE_TYPES = {"entity", "event", "topic"}


def slugify(value: str) -> str:
    value = value.strip()
    if value.startswith("[[") and value.endswith("]]" ):
        value = value[2:-2]
    value = value.removesuffix(".md").lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def is_placeholder_slug(slug: str) -> bool:
    return not slug or slug.isdigit() or bool(PLACEHOLDER_SLUG_RE.match(slug))


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
    page_slug: str
    page_type: str
    raw_log_entry_id: str


@dataclass(frozen=True)
class RoutingFailure:
    claim_id: str
    raw_log_entry_id: str
    reason: str


@dataclass
class RoutingResult:
    routes: list[ClaimRoute]
    failures: list[RoutingFailure]


class ClaimRouter:
    """Route every admitted claim exactly once with one structured LLM decision."""

    def __init__(self, llm: OllamaClient, wiki: WikiStore):
        self.llm = llm
        self.wiki = wiki

    async def route(self, evidence: list[ClaimEvidence]) -> RoutingResult:
        result = RoutingResult(routes=[], failures=[])
        evidence_by_source: dict[str, list[ClaimEvidence]] = {}
        for item in evidence:
            evidence_by_source.setdefault(item.raw_log_entry_id, []).append(item)
        for source_evidence in evidence_by_source.values():
            for offset in range(0, len(source_evidence), 32):
                batch = source_evidence[offset:offset + 32]
                batch_result = await self._route_batch(batch)
                result.routes.extend(batch_result.routes)
                result.failures.extend(batch_result.failures)
        return result

    async def _route_batch(self, evidence: list[ClaimEvidence]) -> RoutingResult:
        aliases = {f"C{index:03d}": item for index, item in enumerate(evidence, start=1)}
        output_model = consolidation_output_model(aliases)
        system, user = prompts.consolidation_identify_prompt(
            self._page_catalog(), self._format_evidence(aliases)
        )
        try:
            response = await self.llm.call_structured(
                system,
                user,
                output_model,
                num_predict=4096,
                debug_label="dream-claim-routing",
            )
            if not isinstance(response, dict):
                raise ValueError("Routing response was not an object")
            destinations = output_model.model_validate(response).model_dump()
        except Exception as exc:
            return self._fail_batch(
                evidence,
                f"Routing response did not satisfy the source contract: {type(exc).__name__}",
            )

        routed_slugs = {
            slugify(str(destination.get("page", "")))
            for destination in destinations.values()
        }
        if len(routed_slugs) > 8:
            return self._fail_batch(evidence, "Routing response exceeded eight pages")

        result = RoutingResult(routes=[], failures=[])
        for alias, item in aliases.items():
            destination = destinations[alias]
            page_slug = slugify(str(destination.get("page", "")))
            page_type = str(destination.get("page_type", "topic")).lower()
            if is_placeholder_slug(page_slug) or page_type not in PAGE_TYPES:
                result.failures.append(self._failure(item, "Invalid route decision"))
                continue
            if page_slug == "user-profile" and self._has_named_participant_scope(item.source):
                result.failures.append(
                    self._failure(item, "Named-participant evidence cannot target user-profile")
                )
                continue
            result.routes.append(ClaimRoute(
                claim_id=item.claim.claim_id,
                page_slug=page_slug,
                page_type=page_type,
                raw_log_entry_id=item.raw_log_entry_id,
            ))
        return result

    def _page_catalog(self) -> str:
        lines = ["Existing canonical pages:"]
        for page in sorted(self.wiki.list_all(), key=lambda item: item.slug):
            type_tag = next(
                (tag for tag in page.tags if str(tag).startswith("page-type-")),
                "page-type-topic",
            )
            lines.append(f"- [[{page.slug}]] title={page.title!r}; {type_tag}")
        return "\n".join(lines)

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
                f"[EVIDENCE {alias}]\n"
                f"claim_type={claim.claim_type}; entities={entities}; "
                f"temporal_status={claim.temporal_status}; source_type={item.source.source_type}\n"
                f"claim={claim.text}\nqualifiers={facets or 'none'}"
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
        return RoutingResult(
            routes=[],
            failures=[self._failure(item, reason) for item in evidence],
        )
