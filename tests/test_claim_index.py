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
