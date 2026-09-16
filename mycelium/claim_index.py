"""Rebuildable hybrid search projection over active memory claims."""

from __future__ import annotations

from mycelium.telemetry import trace_metadata

import asyncio
import hashlib
import json
import time
import logging
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

    def __init__(
        self, url: str, model: str, *, timeout: int, trace_path: Path | None = None
    ) -> None:
        self.model = model
        self.trace_path = trace_path
        self.client = AsyncClient(host=url.rstrip("/"), timeout=timeout)

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []
        response = await self._embed(
            stage="embedding-documents",
            input=[f"title: none | text: {document}" for document in documents],
            truncate=False,
        )
        return [list(vector) for vector in response.embeddings]

    async def embed_query(self, query: str) -> list[float]:
        response = await self._embed(
            stage="embedding-query",
            input=f"task: search result | query: {query}",
            truncate=False,
        )
        return list(response.embeddings[0])

    async def embed_queries(self, queries: list[str]) -> list[list[float]]:
        if not queries:
            return []
        response = await self._embed(stage="embedding-queries",
            input=[f"task: search result | query: {query}" for query in queries], truncate=False)
        return [list(vector) for vector in response.embeddings]

    async def identity(self) -> str:
        inventory = await self.client.list()
        qualified = self.model if ":" in self.model else self.model + ":latest"
        matches = [model for model in inventory.models if model.model in {self.model, qualified}]
        if len(matches) != 1 or not matches[0].digest:
            raise ValueError(f"Cannot identify configured embedding weights: {self.model}")
        return str(matches[0].digest)

    async def _embed(self, *, stage, input, truncate):
        started = time.perf_counter()
        response = None
        try:
            response = await self.client.embed(
                model=self.model, input=input, truncate=truncate
            )
            return response
        finally:
            if self.trace_path is not None:
                record = {
                    "trace": trace_metadata(),
                    "timestamp": time.time(),
                    "stage": stage,
                    "model": self.model,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "success": response is not None,
                    "items": len(input) if isinstance(input, list) else 1,
                    "metadata": {
                        key: getattr(response, key, None)
                        for key in (
                            "total_duration",
                            "load_duration",
                            "prompt_eval_count",
                        )
                    },
                }
                try:
                    self.trace_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.trace_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(record) + "\n")
                except OSError:
                    logging.getLogger(__name__).warning(
                        "Could not persist embedding timing", exc_info=True
                    )


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
        self._revision = None
        self._has_records = False

    async def search(
        self, query: str, *, limit: int | None = None
    ) -> list[ClaimSearchHit]:
        if not query.strip():
            return []
        result_limit = self.candidate_limit if limit is None else max(1, limit)
        async with self._lock:
            kinds = ("claims", "entities", "placements")
            revision = (
                self.embedder.model,
                tuple(self.artifacts.db.revision(kind) for kind in kinds),
            )
            if revision != self._revision:
                if self._revision is None or revision[0] != self._revision[0]:
                    records = self._claim_records()
                    await self._synchronize(records)
                    self._has_records = bool(records)
                else:
                    changed = {
                        kind: self.artifacts.db.changed_ids(kind, previous)
                        for kind, previous in zip(kinds, self._revision[1])
                    }
                    affected = changed["claims"] | changed["placements"]
                    for entity_id in changed["entities"]:
                        affected.update(
                            self.artifacts.db.ids(
                                "placements", "owner_entity_id", entity_id
                            )
                        )
                    if affected:
                        records = self._claim_records(affected)
                        await self._synchronize(records, affected)
                        with await self._connect() as db:
                            self._has_records = (
                                TABLE_NAME in (await db.list_tables()).tables
                                and await (await db.open_table(TABLE_NAME)).count_rows()
                                > 0
                            )
                self._revision = revision
            if not self._has_records:
                return []
            query_vector = await self.embedder.embed_query(query)
            rows = await self._hybrid_search(query, query_vector, limit=result_limit)
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

    def _claim_records(self, claim_ids=None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        claims = self.artifacts.list_claims() if claim_ids is None else []
        if claim_ids is not None:
            for identifier in sorted(claim_ids):
                try:
                    claims.append(self.artifacts.get_claim(identifier))
                except FileNotFoundError:
                    pass
        for claim in claims:
            if claim.status == "retracted":
                continue
            tier = self.artifacts.memory_tier(claim.claim_id)
            if tier == "source":
                continue
            if claim.status == "superseded":
                tier = "superseded"
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

    async def _synchronize(self, records: list[dict[str, Any]], affected=None) -> None:
        existing = await self._existing_rows(affected)
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

        prior_by_id = {str(row["claim_id"]): row for row in existing}
        changed = [
            row
            for row in records
            if actual.get(row["claim_id"]) != expected[row["claim_id"]]
        ]
        embedding_changes = [
            row
            for row in changed
            if (prior := prior_by_id.get(row["claim_id"])) is None
            or prior["document"] != row["document"]
            or prior["embedding_model"] != row["embedding_model"]
        ]
        vector_by_id = {}
        for start in range(0, len(embedding_changes), 24):
            batch = embedding_changes[start : start + 24]
            vectors = await self.embedder.embed_documents(
                [row["document"] for row in batch]
            )
            if len(vectors) != len(batch):
                raise ValueError(
                    "Embedding service returned the wrong number of vectors"
                )
            vector_by_id.update(
                {row["claim_id"]: vector for row, vector in zip(batch, vectors)}
            )
        reuse_ids = {row["claim_id"] for row in changed} - set(vector_by_id)
        with await self._connect() as db:
            if TABLE_NAME not in (await db.list_tables()).tables:
                if not changed:
                    return
                table = await db.create_table(
                    TABLE_NAME,
                    data=[
                        {**row, "vector": vector_by_id[row["claim_id"]]}
                        for row in changed
                    ],
                )
                await table.create_index("document", config=FTS())
                return
            table = await db.open_table(TABLE_NAME)
            if reuse_ids:
                for batch in _id_batches(reuse_ids):
                    reused = (
                        await table.query()
                        .where(_id_filter(batch))
                        .select(["claim_id", "vector"])
                        .to_list()
                    )
                    vector_by_id.update(
                        {row["claim_id"]: list(row["vector"]) for row in reused}
                    )
            if changed:
                await (
                    table.merge_insert("claim_id")
                    .when_matched_update_all()
                    .when_not_matched_insert_all()
                    .execute(
                        [
                            {**row, "vector": vector_by_id[row["claim_id"]]}
                            for row in changed
                        ]
                    )
                )
            deleted = set(actual) - set(expected)
            if deleted:
                for batch in _id_batches(deleted):
                    await table.delete(_id_filter(batch))

    async def _connect(self):
        self.path.mkdir(parents=True, exist_ok=True)
        return await lancedb.connect_async(self.path)

    async def _existing_rows(self, affected=None) -> list[dict[str, Any]]:
        with await self._connect() as db:
            if TABLE_NAME not in (await db.list_tables()).tables:
                return []
            table = await db.open_table(TABLE_NAME)
            columns = ["claim_id", "content_hash", "embedding_model", "document"]
            if affected is None:
                return await table.query().select(columns).to_list()
            rows = []
            for batch in _id_batches(affected):
                rows.extend(
                    await table.query()
                    .where(_id_filter(batch))
                    .select(columns)
                    .to_list()
                )
            return rows

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
            "Subjects: " + json.dumps(claim.about, ensure_ascii=False, sort_keys=True)
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


def _id_filter(ids: set[str]) -> str:
    return (
        "claim_id IN ("
        + ", ".join("'" + value.replace("'", "''") + "'" for value in sorted(ids))
        + ")"
    )


def _id_batches(ids: set[str]):
    ordered = sorted(ids)
    for start in range(0, len(ordered), 500):
        yield set(ordered[start : start + 500])
