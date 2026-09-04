"""Rebuildable hybrid search projection over active memory claims."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import lancedb
from lancedb.index import FTS
from lancedb.rerankers import RRFReranker
from ollama import AsyncClient

from mycelium.artifacts import ArtifactStore, MemoryClaim


TABLE_NAME = "claims"


@dataclass(frozen=True)
class ClaimSearchHit:
    claim_id: str
    claim_text: str
    memory_tier: str
    owner_entity_id: str | None
    owner_title: str | None
    page_slug: str | None
    section_key: str | None
    score: float | None


class ClaimEmbedder(Protocol):
    model: str

    async def embed_documents(self, documents: list[str]) -> list[list[float]]: ...

    async def embed_query(self, query: str) -> list[float]: ...


class OllamaEmbedder:
    """EmbeddingGemma client with the task prefixes its model card specifies."""

    def __init__(self, url: str, model: str, *, timeout: int) -> None:
        self.model = model
        self.client = AsyncClient(host=url.rstrip("/"), timeout=timeout)

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []
        response = await self.client.embed(
            model=self.model,
            input=[f"title: none | text: {document}" for document in documents],
            truncate=False,
        )
        return [list(vector) for vector in response.embeddings]

    async def embed_query(self, query: str) -> list[float]:
        response = await self.client.embed(
            model=self.model,
            input=f"task: search result | query: {query}",
            truncate=False,
        )
        return list(response.embeddings[0])


class LanceClaimIndex:
    """Synchronize and search a derived LanceDB projection of claim artifacts."""

    def __init__(
        self,
        path: Path,
        artifacts: ArtifactStore,
        embedder: ClaimEmbedder,
        *,
        candidate_limit: int = 20,
    ) -> None:
        self.path = path
        self.artifacts = artifacts
        self.embedder = embedder
        self.candidate_limit = candidate_limit
        self._lock = asyncio.Lock()

    async def search(
        self, query: str, *, limit: int | None = None
    ) -> list[ClaimSearchHit]:
        if not query.strip():
            return []
        result_limit = self.candidate_limit if limit is None else max(1, limit)
        async with self._lock:
            records = self._claim_records()
            if not records:
                return []
            await self._synchronize(records)
            query_vector = await self.embedder.embed_query(query)
            rows = await self._hybrid_search(
                query, query_vector, limit=result_limit
            )
        return [
            ClaimSearchHit(
                claim_id=str(row["claim_id"]),
                claim_text=str(row["claim_text"]),
                memory_tier=str(row["memory_tier"]),
                owner_entity_id=_optional(row.get("owner_entity_id")),
                owner_title=_optional(row.get("owner_title")),
                page_slug=_optional(row.get("page_slug")),
                section_key=_optional(row.get("section_key")),
                score=_float_or_none(row.get("_relevance_score")),
            )
            for row in rows
        ]

    def _claim_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for claim in self.artifacts.list_claims(status="active"):
            tier = self.artifacts.memory_tier(claim.claim_id)
            if tier == "source":
                continue
            placement = self.artifacts.placement_for_claim(claim.claim_id)
            entity = None
            if placement and placement.owner_entity_id:
                try:
                    entity = self.artifacts.get_entity(placement.owner_entity_id)
                except FileNotFoundError:
                    entity = None
            document = _search_document(claim, entity.title if entity else None)
            record = {
                "claim_id": claim.claim_id,
                "document": document,
                "claim_text": claim.text,
                "memory_tier": tier,
                "owner_entity_id": placement.owner_entity_id if placement else "",
                "owner_title": entity.title if entity else "",
                "page_slug": entity.slug if entity else "",
                "section_key": placement.section_key if placement else "",
                "embedding_model": self.embedder.model,
            }
            record["content_hash"] = hashlib.sha256(
                json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            records.append(record)
        return records

    async def _synchronize(self, records: list[dict[str, Any]]) -> None:
        existing = await self._existing_rows()
        expected = {
            row["claim_id"]: (row["content_hash"], row["embedding_model"])
            for row in records
        }
        actual = {
            str(row["claim_id"]): (row.get("content_hash"), row.get("embedding_model"))
            for row in existing
        }
        if expected == actual:
            return

        reusable = {
            str(row["claim_id"]): row
            for row in existing
            if expected.get(str(row["claim_id"]))
            == (row.get("content_hash"), row.get("embedding_model"))
        }
        changed = [row for row in records if row["claim_id"] not in reusable]
        vectors = await self.embedder.embed_documents(
            [str(row["document"]) for row in changed]
        )
        if len(vectors) != len(changed):
            raise ValueError("Embedding service returned the wrong number of vectors")
        vector_by_id = {
            str(row["claim_id"]): vector for row, vector in zip(changed, vectors)
        }
        indexed = []
        for record in records:
            prior = reusable.get(str(record["claim_id"]))
            indexed.append({
                **record,
                "vector": (
                    list(prior["vector"])
                    if prior is not None
                    else vector_by_id[str(record["claim_id"])]
                ),
            })
        await self._replace_table(indexed)

    async def _connect(self):
        self.path.mkdir(parents=True, exist_ok=True)
        return await lancedb.connect_async(self.path)

    async def _existing_rows(self) -> list[dict[str, Any]]:
        with await self._connect() as db:
            if TABLE_NAME not in (await db.list_tables()).tables:
                return []
            table = await db.open_table(TABLE_NAME)
            return (await table.to_arrow()).to_pylist()

    async def _replace_table(self, rows: list[dict[str, Any]]) -> None:
        with await self._connect() as db:
            table = await db.create_table(TABLE_NAME, data=rows, mode="overwrite")
            await table.create_index("document", config=FTS(), replace=True)

    async def _hybrid_search(
        self, query: str, query_vector: list[float], *, limit: int
    ) -> list[dict[str, Any]]:
        with await self._connect() as db:
            table = await db.open_table(TABLE_NAME)
            search = (
                table.query()
                .nearest_to(query_vector)
                .nearest_to_text(query)
                .rerank(RRFReranker())
                .limit(limit)
            )
            return await search.to_list()


def _search_document(claim: MemoryClaim, owner_title: str | None) -> str:
    parts = []
    if owner_title:
        parts.append(f"Subject: {owner_title}")
    elif claim.about:
        parts.append(
            "Subjects: "
            + json.dumps(claim.about, ensure_ascii=False, sort_keys=True)
        )
    if claim.predicate:
        parts.append(f"Relation: {claim.predicate}")
    parts.append(f"Memory: {claim.text}")
    temporal = claim.facets.get("temporal")
    if temporal:
        parts.append(
            "Temporal context: "
            + json.dumps(temporal, ensure_ascii=False, sort_keys=True)
        )
    return "\n".join(parts)


def _optional(value: Any) -> str | None:
    rendered = str(value or "").strip()
    return rendered or None


def _float_or_none(value: Any) -> float | None:
    return float(value) if value is not None else None
