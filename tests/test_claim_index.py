from dataclasses import replace

import pytest

from mycelium.artifacts import ArtifactStore, ClaimPlacement, ClaimProvenance, MemoryClaim
from mycelium.claim_index import LanceClaimIndex


class FakeEmbedder:
    model = "test-embedding"

    def __init__(self):
        self.document_batches: list[list[str]] = []

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        self.document_batches.append(documents)
        return [
            [1.0, 0.0] if "cello" in document else [0.0, 1.0]
            for document in documents
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
async def test_claim_index_hybrid_search_is_rebuildable_and_excludes_source_only(tmp_path):
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
        artifacts.save_placement(ClaimPlacement(
            claim.claim_id,
            entity.entity_id,
            "timeline",
            [],
            "placed",
            "test",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        ))
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
async def test_incremental_index_reuses_vectors_for_metadata_and_removes_deleted_claims(tmp_path):
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
    import json
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
    path = artifacts.claims_dir / "two.json"
    data = json.loads(path.read_text())
    data["text"] = "Mira enjoys weaving."
    path.write_text(json.dumps(data))
    hits = await index.search("weaving")
    assert any(hit.claim_text == "Mira enjoys weaving." for hit in hits)
