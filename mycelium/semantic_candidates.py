"""Bounded vector candidates; only later model decisions establish meaning."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from pathlib import Path
from weakref import WeakValueDictionary

import lancedb

from mycelium.decision_cache import DecisionCache
from mycelium.batching import split_text_by_tokens

_LOCKS: WeakValueDictionary = WeakValueDictionary()


def _hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _vectors(values, count, dimension=None):
    if len(values) != count or not values:
        raise ValueError("Embedding response must account for every input")
    dimension = dimension or len(values[0])
    if not dimension or any(
        len(v) != dimension or not all(math.isfinite(x) for x in v) or not any(v)
        for v in values
    ):
        raise ValueError("Embeddings must be finite and share a nonzero dimension")
    return values


class SemanticCandidates:
    """Synchronize changed documents and rank candidates without lexical rules."""

    def __init__(self, path: Path, embedder, cache_store):
        self.path, self.embedder, self.cache_store = path, embedder, cache_store
        self.lock = _LOCKS.setdefault(path.resolve(), asyncio.Lock())
        self.last_trace = {}

    async def select(
        self, documents, queries, *, limit=24, required_ids=(), eligible_ids=None
    ):
        required = sorted(set(required_ids))
        eligible = set(documents) if eligible_ids is None else set(eligible_ids)
        if not eligible <= documents.keys():
            raise ValueError("Eligible candidate IDs must belong to this snapshot")
        self.last_trace = {
            "required_ids": required,
            "limit": limit,
            "document_count": len(documents),
            "eligible_count": len(eligible),
        }
        if limit < 1 or len(required) > limit or not set(required) <= eligible:
            raise ValueError(
                "Required candidate IDs must fit the bound and belong to this snapshot"
            )
        if len(required) == limit:
            return required
        if len(eligible) <= limit:
            return [
                *required,
                *(
                    identifier
                    for identifier in sorted(eligible)
                    if identifier not in required
                ),
            ]
        if not queries:
            raise ValueError("Semantic candidate discovery requires evidence queries")
        async with self.lock:
            signature = await self.embedder.identity()
            self.path.mkdir(parents=True, exist_ok=True)
            with await lancedb.connect_async(self.path) as db:
                table = await self._synchronize(db, documents, signature)
                vectors = await self._queries(
                    [
                        chunk
                        for query in queries
                        for chunk in split_text_by_tokens(query, 512)
                    ],
                    signature,
                )
                ranked = []
                excluded = documents.keys() - eligible
                # Exact ID eligibility narrows a ranking domain, not meaning.
                # Prefer the smaller predicate while retaining one shared index.
                values, operator = (
                    (eligible, "IN")
                    if len(eligible) <= len(excluded)
                    else (excluded, "NOT IN")
                )
                predicate = (
                    (
                        "parent_id "
                        + operator
                        + " ("
                        + ", ".join(
                            "'" + value.replace("'", "''") + "'"
                            for value in sorted(values)
                        )
                        + ")"
                    )
                    if values
                    else None
                )
                row_count = await table.count_rows(predicate)
                for vector in vectors:
                    # ANN is deliberately gated on the separate recall experiment.
                    count = min(row_count, limit)
                    while True:
                        query = table.query().nearest_to(vector)
                        if predicate:
                            query = query.where(predicate)
                        rows = await (
                            query.distance_type("cosine")
                            .bypass_vector_index()
                            .limit(count)
                            .select(["parent_id", "_distance"])
                            .to_list()
                        )
                        unique = list(dict.fromkeys(row["parent_id"] for row in rows))
                        if len(unique) >= limit or count == row_count:
                            break
                        count = min(row_count, count * 2)
                    ranked.append(unique[:limit])
                self.last_trace.update(model_digest=signature, ranked_ids=ranked)
                if await self.embedder.identity() != signature:
                    raise ValueError(
                        "Embedding weights changed during candidate discovery"
                    )
        selected = list(required)
        # Give each evidence query a place in the bounded pool. This combines
        # learned vector rankings; it does not resolve any identity or truth.
        for rank in range(limit):
            for candidates in ranked:
                if rank < len(candidates) and candidates[rank] not in selected:
                    selected.append(candidates[rank])
                    if len(selected) == limit:
                        return selected
        return selected

    async def _queries(self, queries, signature):
        keys = [
            DecisionCache(
                self.cache_store,
                {
                    "kind": "semantic-query-vector-v1",
                    "weights": signature,
                    "model": self.embedder.model,
                    "query": query,
                },
            )
            for query in queries
        ]
        records = [key.get() for key in keys]
        missing = [i for i, record in enumerate(records) if record is None]
        if missing:
            vectors = _vectors(
                await self.embedder.embed_queries([queries[i] for i in missing]),
                len(missing),
            )
            if await self.embedder.identity() != signature:
                raise ValueError("Embedding weights changed while encoding queries")
            for i, vector in zip(missing, vectors):
                keys[i].save(
                    vector, model_digest=signature, stage="semantic-query-vector"
                )
                records[i] = {"response": vector}
        return _vectors([record["response"] for record in records], len(queries))

    async def _synchronize(self, db, documents, signature):
        chunks = {}
        parents = {}
        for parent_id, document in documents.items():
            pieces = split_text_by_tokens(document, 512)
            if not pieces:
                raise ValueError("Candidate documents must contain evidence")
            for offset, chunk in enumerate(pieces):
                chunk_id = _hash([parent_id, offset, chunk])
                chunks[chunk_id] = chunk
                parents[chunk_id] = parent_id
        documents = chunks
        exists = "candidates" in (await db.list_tables()).tables
        table = await db.open_table("candidates") if exists else None
        prior = (
            await table.query().select(["id", "content_hash", "model_digest"]).to_list()
            if exists
            else []
        )
        replace = any(row["model_digest"] != signature for row in prior)
        old_hashes = (
            {} if replace else {row["id"]: row["content_hash"] for row in prior}
        )
        hashes = {
            identifier: _hash([signature, document])
            for identifier, document in documents.items()
        }
        changed = [
            identifier
            for identifier in sorted(documents)
            if old_hashes.get(identifier) != hashes[identifier]
        ]
        rows = []
        dimension = None
        for start in range(0, len(changed), 24):
            batch = changed[start : start + 24]
            vectors = _vectors(
                await self.embedder.embed_documents([documents[i] for i in batch]),
                len(batch),
                dimension,
            )
            dimension = len(vectors[0])
            rows.extend(
                {
                    "id": identifier,
                    "content_hash": hashes[identifier],
                    "model_digest": signature,
                    "parent_id": parents[identifier],
                    "vector": vector,
                }
                for identifier, vector in zip(batch, vectors)
            )
        if await self.embedder.identity() != signature:
            raise ValueError("Embedding weights changed while encoding candidates")
        if not exists or replace:
            return await db.create_table("candidates", data=rows, mode="overwrite")
        if rows:
            await (
                table.merge_insert("id")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute(rows)
            )
        removed = set(old_hashes) - documents.keys()
        for start in range(0, len(removed), 500):
            values = sorted(removed)[start : start + 500]
            expression = (
                "id IN ("
                + ", ".join("'" + value.replace("'", "''") + "'" for value in values)
                + ")"
            )
            await table.delete(expression)
        return table
