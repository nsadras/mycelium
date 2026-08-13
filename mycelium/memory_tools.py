"""Bounded read-only tools over canonical and short-term claims."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from mycelium.artifacts import ArtifactStore, MemoryClaim, temporal_record
from mycelium.lexical import query_term_weights, terms


MEMORY_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": (
                "Search active memory claims, including recent unconsolidated memory. Results "
                "identify their memory tier. Use focused queries for each person, event, relation, "
                "or missing part of a comparison."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_expand",
            "description": (
                "Find claims connected to seed claims by explicit links, subjects, wiki pages, "
                "or source episodes. Use this to follow a promising memory relationship."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 8,
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                },
                "required": ["claim_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_sources",
            "description": (
                "Read exact source segments supporting claims, with at most one neighboring "
                "segment for conversational context. Use this to verify attribution or wording."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 8,
                    },
                    "neighbor_count": {"type": "integer", "minimum": 0, "maximum": 1},
                },
                "required": ["claim_ids"],
            },
        },
    },
]


class MemoryToolset:
    """Execute a deliberately small, read-only memory exploration interface."""

    def __init__(self, artifacts: ArtifactStore):
        self.artifacts = artifacts

    def run(self, tool_name: str, arguments: dict[str, Any]) -> str:
        try:
            if tool_name == "memory_search":
                result = self.search(
                    str(arguments.get("query") or ""),
                    limit=_bounded_int(arguments.get("limit"), default=6, low=1, high=10),
                )
            elif tool_name == "memory_expand":
                result = self.expand(
                    _string_list(arguments.get("claim_ids"), limit=8),
                    limit=_bounded_int(arguments.get("limit"), default=8, low=1, high=12),
                )
            elif tool_name == "memory_sources":
                result = self.sources(
                    _string_list(arguments.get("claim_ids"), limit=8),
                    neighbor_count=_bounded_int(
                        arguments.get("neighbor_count"), default=1, low=0, high=1
                    ),
                )
            else:
                return json.dumps({"error": f"Unknown memory tool: {tool_name}"})
            return json.dumps(result, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def search(
        self,
        query: str,
        *,
        limit: int = 6,
        memory_tier: str | None = None,
    ) -> list[dict[str, Any]]:
        query = " ".join(query.split()).strip()
        if not query:
            raise ValueError("memory_search requires a nonempty query")
        claims = self.artifacts.list_claims(status="active")
        if memory_tier is not None:
            if memory_tier not in {"short_term", "canonical"}:
                raise ValueError("memory_tier must be short_term or canonical")
            claims = [
                claim for claim in claims
                if self.artifacts.memory_tier(claim.claim_id) == memory_tier
            ]
        documents = [self._search_document(claim) for claim in claims]
        weights = query_term_weights(documents, query)
        query_terms = terms(query)
        ranked: list[tuple[float, str, MemoryClaim]] = []
        for claim, document in zip(claims, documents, strict=True):
            document_terms = terms(document)
            score = sum(weights[term] for term in query_terms & document_terms)
            entity_terms = terms(" ".join(
                str(item.get("entity") or "") for item in claim.about
            ))
            score += 1.5 * sum(
                weights[term] for term in query_terms & entity_terms
            )
            if score > 0:
                ranked.append((score, claim.claim_id, claim))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [self._claim_result(claim, score) for score, _, claim in ranked[:limit]]

    def expand(
        self, claim_ids: list[str], *, limit: int = 8
    ) -> list[dict[str, Any]]:
        if not claim_ids:
            raise ValueError("memory_expand requires at least one claim ID")
        active = {claim.claim_id: claim for claim in self.artifacts.list_claims(status="active")}
        seeds = [active[claim_id] for claim_id in claim_ids if claim_id in active]
        if not seeds:
            raise ValueError("memory_expand received no active claim IDs")
        seed_ids = {claim.claim_id for claim in seeds}
        seed_entities = set().union(*(self._entities(claim) for claim in seeds))
        seed_owners = {
            placement.owner_entity_id
            for claim in seeds
            if (placement := self.artifacts.placement_for_claim(claim.claim_id))
            and placement.owner_entity_id
        }
        seed_sources = set().union(*(self._source_ids(claim) for claim in seeds))
        explicit_ids = {
            str(link.get("claim_id") or link.get("target_claim_id") or "")
            for claim in seeds
            for link in claim.links
        }
        ranked: list[tuple[float, str, MemoryClaim]] = []
        for claim in active.values():
            if claim.claim_id in seed_ids:
                continue
            score = 0.0
            if claim.claim_id in explicit_ids:
                score += 8.0
            score += 3.0 * len(seed_entities & self._entities(claim))
            placement = self.artifacts.placement_for_claim(claim.claim_id)
            if placement and placement.owner_entity_id in seed_owners:
                score += 2.0
            score += 1.0 * len(seed_sources & self._source_ids(claim))
            if score > 0:
                ranked.append((score, claim.claim_id, claim))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [self._claim_result(claim, score) for score, _, claim in ranked[:limit]]

    def sources(
        self, claim_ids: list[str], *, neighbor_count: int = 1
    ) -> list[dict[str, Any]]:
        if not claim_ids:
            raise ValueError("memory_sources requires at least one claim ID")
        active = {claim.claim_id: claim for claim in self.artifacts.list_claims(status="active")}
        source_cache = {source.source_id: source for source in self.artifacts.list_sources()}
        selected: dict[str, set[int]] = defaultdict(set)
        owners: dict[str, set[str]] = defaultdict(set)
        for claim_id in claim_ids:
            claim = active.get(claim_id)
            if claim is None:
                continue
            for provenance in claim.provenance:
                source = source_cache.get(provenance.source_id)
                if source is None:
                    continue
                indexes = {
                    segment.index
                    for segment in source.segments
                    if segment.segment_id in provenance.segment_ids
                }
                for index in indexes:
                    for selected_index in range(
                        max(0, index - neighbor_count),
                        min(len(source.segments), index + neighbor_count + 1),
                    ):
                        selected[source.source_id].add(selected_index)
                owners[source.source_id].add(claim_id)
        results = []
        for source_id in sorted(selected):
            source = source_cache[source_id]
            results.append({
                "source_id": source.source_id,
                "occurred_at": source.occurred_at,
                "claim_ids": sorted(owners[source_id]),
                "segments": [
                    {
                        "segment_id": source.segments[index].segment_id,
                        "source_label": source.segments[index].metadata.get("source_label"),
                        "speaker": source.segments[index].speaker,
                        "content": source.segments[index].content,
                    }
                    for index in sorted(selected[source_id])
                ],
            })
        return results

    @staticmethod
    def _entities(claim: MemoryClaim) -> set[str]:
        return {
            str(item.get("entity") or "").strip().lower()
            for item in claim.about
            if str(item.get("entity") or "").strip()
        }

    @staticmethod
    def _source_ids(claim: MemoryClaim) -> set[str]:
        return {provenance.source_id for provenance in claim.provenance}

    def _search_document(self, claim: MemoryClaim) -> str:
        temporal = temporal_record(claim.facets) or {}
        return " ".join([
            claim.text,
            claim.claim_type,
            claim.predicate or "",
            " ".join(self._entities(claim)),
            self._placement_text(claim.claim_id),
            str(temporal.get("expression") or ""),
            str(temporal.get("start") or ""),
            str(temporal.get("end") or ""),
        ])

    def _claim_result(self, claim: MemoryClaim, score: float) -> dict[str, Any]:
        return {
            "claim_id": claim.claim_id,
            "text": claim.text,
            "subjects": sorted(self._entities(claim)),
            "claim_type": claim.claim_type,
            "predicate": claim.predicate,
            "temporal": temporal_record(claim.facets),
            "memory_tier": self.artifacts.memory_tier(claim.claim_id),
            "consolidation_status": claim.dream_disposition,
            **self._placement_result(claim.claim_id),
            "source_ids": sorted(self._source_ids(claim)),
            "score": round(score, 4),
        }

    def _placement_text(self, claim_id: str) -> str:
        placement = self.artifacts.placement_for_claim(claim_id)
        if not placement or not placement.owner_entity_id:
            return ""
        try:
            entity = self.artifacts.get_entity(placement.owner_entity_id)
        except FileNotFoundError:
            return placement.owner_entity_id
        return " ".join([entity.entity_id, entity.title, entity.slug, *entity.aliases])

    def _placement_result(self, claim_id: str) -> dict[str, Any]:
        placement = self.artifacts.placement_for_claim(claim_id)
        if not placement or not placement.owner_entity_id:
            return {"owner_entity_id": None, "page_slug": None, "section_key": None}
        try:
            slug = self.artifacts.get_entity(placement.owner_entity_id).slug
        except FileNotFoundError:
            slug = None
        return {
            "owner_entity_id": placement.owner_entity_id,
            "page_slug": slug,
            "section_key": placement.section_key,
        }


def _bounded_int(value: Any, *, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(high, parsed))


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(
        str(item).strip() for item in value[:limit] if str(item).strip()
    ))
