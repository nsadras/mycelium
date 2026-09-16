from dataclasses import replace

import pytest

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    MemoryClaim,
)
from mycelium.claim_index import LanceClaimIndex


class FakeEmbedder:
    model = "test-embedding"
    digest = "weights-one"

    async def identity(self):
        return self.digest

    def __init__(self):
        self.document_batches: list[list[str]] = []

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        self.document_batches.append(documents)
        return [
            [1.0, 0.0] if "cello" in document else [0.0, 1.0] for document in documents
        ]

    async def embed_query(self, _query: str) -> list[float]:
        return [1.0, 0.0]


def _claim(claim_id: str, text: str, *, disposition: str = "routed") -> MemoryClaim:
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        about=[{"entity": "Mira", "role": "subject"}],
        provenance=[ClaimProvenance("source", ["segment"])],
        recorded_at="2026-01-01T00:00:00+00:00",
        dream_disposition=disposition,
    )


@pytest.mark.asyncio
async def test_claim_index_hybrid_search_is_rebuildable_and_excludes_source_only(
    tmp_path,
):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    entity = artifacts.create_entity("person", "Mira")
    cello = _claim("cello", "Mira plays the cello.")
    garden = _claim("garden", "Mira grows tomatoes.")
    excluded = _claim(
        "excluded", "Mira mentioned a cello.", disposition="excluded_source_policy"
    )
    for claim in (cello, garden, excluded):
        artifacts.save_claim(claim)
    for claim in (cello, garden):
        artifacts.save_placement(
            ClaimPlacement(
                claim.claim_id,
                entity.entity_id,
                "timeline",
                [],
                "placed",
                "test",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            )
        )
    embedder = FakeEmbedder()
    index = LanceClaimIndex(tmp_path / "claims.lance", artifacts, embedder)

    first = await index.search("What instrument does Mira play?")
    assert first[0].claim_id == "cello"
    assert {hit.claim_id for hit in first} == {"cello", "garden"}
    assert len(embedder.document_batches) == 1
    assert len(embedder.document_batches[0]) == 2

    await index.search("What instrument does Mira play?")
    assert len(embedder.document_batches) == 1

    artifacts.save_claim(replace(garden, text="Mira grows peppers."))
    await index.search("What instrument does Mira play?")
    assert len(embedder.document_batches) == 2
    assert len(embedder.document_batches[1]) == 1


@pytest.mark.asyncio
async def test_incremental_index_reuses_vectors_for_metadata_and_removes_deleted_claims(
    tmp_path,
):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    claim = _claim("cello", "Mira plays the cello.", disposition="deferred")
    artifacts.save_claim(claim)
    embedder = FakeEmbedder()
    index = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    assert (await index.search("cello"))[0].memory_tier == "short_term"
    artifacts.save_claim(replace(claim, dream_disposition="routed"))
    await index.search("cello")
    assert len(embedder.document_batches) == 1
    artifacts.save_claim(replace(claim, status="superseded"))
    assert (await index.search("cello"))[0].memory_tier == "superseded"
    restarted = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    assert (await restarted.search("cello"))[0].memory_tier == "superseded"
    artifacts.save_claim(replace(claim, status="retracted"))
    assert await restarted.search("cello") == []


@pytest.mark.asyncio
async def test_incremental_index_bounds_embedding_batches(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    for i in range(49):
        artifacts.save_claim(_claim(f"c{i}", f"Memory {i}", disposition="deferred"))
    embedder = FakeEmbedder()
    index = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    await index.search("Memory")
    assert [len(batch) for batch in embedder.document_batches] == [24, 24, 1]


@pytest.mark.asyncio
async def test_incremental_fts_finds_new_text_and_external_edits(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.save_claim(_claim("one", "Mira plays cello.", disposition="deferred"))
    embedder = FakeEmbedder()
    index = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    await index.search("cello")
    artifacts.save_claim(_claim("two", "Mira enjoys ceramics.", disposition="deferred"))
    await index.search("ceramics")
    with await index._connect() as db:
        table = await db.open_table("claims")
        rows = await table.query().nearest_to_text("ceramics").to_list()
        assert [row["claim_id"] for row in rows] == ["two"]
    data = artifacts.get_claim("two")
    data.text = "Mira enjoys weaving."
    artifacts.save_claim(data)
    hits = await index.search("weaving")
    assert any(hit.claim_text == "Mira enjoys weaving." for hit in hits)


@pytest.mark.asyncio
async def test_same_tag_new_weights_rebuild_vectors_and_dimensions(tmp_path):
    class ChangingEmbedder(FakeEmbedder):
        async def embed_documents(self, documents):
            vectors = await super().embed_documents(documents)
            return (
                [v + [0.5] for v in vectors]
                if self.digest == "weights-two"
                else vectors
            )

        async def embed_query(self, query):
            vector = await super().embed_query(query)
            return vector + [0.5] if self.digest == "weights-two" else vector

    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.save_claim(_claim("one", "Mira plays cello.", disposition="deferred"))
    embedder = ChangingEmbedder()
    index = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    await index.search("cello")
    embedder.digest = "weights-two"
    assert [hit.claim_id for hit in await index.search("cello")] == ["one"]
    assert len(embedder.document_batches) == 2
    with await index._connect() as db:
        rows = await (await db.open_table("claims")).to_arrow()
        assert len(rows.to_pylist()[0]["vector"]) == 3
        assert rows.to_pylist()[0]["embedding_model"].endswith("@weights-two")
    restarted = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    assert restarted._lock is index._lock
    await restarted.search("cello")
    assert len(embedder.document_batches) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["documents", "query"])
async def test_weight_change_during_request_is_explicit_failure(tmp_path, stage):
    class UnstableEmbedder(FakeEmbedder):
        async def embed_documents(self, documents):
            result = await super().embed_documents(documents)
            if stage == "documents":
                self.digest = "new-weights"
            return result

        async def embed_query(self, query):
            result = await super().embed_query(query)
            if stage == "query":
                self.digest = "new-weights"
            return result

    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.save_claim(_claim("one", "Mira plays cello.", disposition="deferred"))
    index = LanceClaimIndex(tmp_path / "index", artifacts, UnstableEmbedder())
    with pytest.raises(ValueError, match="weights changed"):
        await index.search("cello")
    assert artifacts.get_claim("one").status == "active"
    assert [h.claim_id for h in await index.search("cello")] == ["one"]


@pytest.mark.asyncio
async def test_typed_date_change_updates_search_embedding(tmp_path):
    from mycelium.temporal import normalize_temporal_facets
    from tests.test_temporal_contract import annotation

    artifacts = ArtifactStore(tmp_path / "artifacts")
    item = _claim(
        "deadline", "The user will send the letter tomorrow.", disposition="deferred"
    )
    detail = annotation(
        {"kind": "day_offset", "days": 1}, expression="tomorrow", segment="segment"
    )
    item.facets = normalize_temporal_facets(
        {"times": [detail.model_dump()], "inference_basis": None},
        {"segment": "2031-05-01"},
    )
    artifacts.save_claim(item)
    embedder = FakeEmbedder()
    index = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    await index.search("letter")
    assert "2031-05-02" in embedder.document_batches[0][0]
    item.facets = normalize_temporal_facets(
        {"times": [detail.model_dump()], "inference_basis": None},
        {"segment": "2031-05-03"},
    )
    artifacts.save_claim(item)
    await index.search("letter")
    assert len(embedder.document_batches) == 2
    assert "2031-05-04" in embedder.document_batches[1][0]


@pytest.mark.asyncio
async def test_flat_index_exhausts_partitions_and_searches_appends_and_deletions(
    tmp_path, monkeypatch
):
    import hashlib

    class ScaleEmbedder(FakeEmbedder):
        async def embed_documents(self, documents):
            return [
                [-1000.0, 0.0]
                if "needle" in d
                else [
                    float(int(hashlib.sha256(d.encode()).hexdigest()[:6], 16) % 1000),
                    1.0,
                ]
                for d in documents
            ]

        async def embed_query(self, query):
            return [-1000.0, 0.0]

    artifacts = ArtifactStore(tmp_path / "artifacts")
    for i in range(256):
        artifacts.save_claim(_claim(str(i), f"Record {i}", disposition="deferred"))
    index = LanceClaimIndex(tmp_path / "index", artifacts, ScaleEmbedder())
    monkeypatch.setattr(index, "_VECTOR_INDEX_MIN_ROWS", 128)
    monkeypatch.setattr(index, "_VECTOR_INDEX_PARTITIONS", 4)
    await index.search("record")
    new = _claim("addition", "A needle entry.", disposition="deferred")
    artifacts.save_claim(new)
    assert (await index.search("needle"))[0].claim_id == "addition"
    with await index._connect() as db:
        table = await db.open_table("claims")
        stats = await table.index_stats("vector_idx")
        assert stats.index_type == "IVF_FLAT" and stats.distance_type == "l2"
        assert stats.num_unindexed_rows == 1
        base = table.query().nearest_to([-1000.0, 0.0]).limit(20).select(["claim_id"])
        indexed = await base.nprobes(4).to_list()
        exact = await base.bypass_vector_index().to_list()
        assert {r["claim_id"] for r in indexed} == {r["claim_id"] for r in exact}
    artifacts.save_claim(replace(new, status="retracted"))
    assert "addition" not in {h.claim_id for h in await index.search("needle")}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "vectors", [[], [[float("nan"), 0.0]], [[float("inf"), 0.0]], [[]]]
)
async def test_malformed_embeddings_never_enter_derived_index(tmp_path, vectors):
    from unittest.mock import AsyncMock

    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.save_claim(_claim("one", "Mira plays cello.", disposition="deferred"))
    embedder = FakeEmbedder()
    embedder.embed_documents = AsyncMock(return_value=vectors)
    index = LanceClaimIndex(tmp_path / "index", artifacts, embedder)
    with pytest.raises(ValueError, match="[Ee]mbedding"):
        await index.search("cello")
    assert await index._existing_rows() == []
