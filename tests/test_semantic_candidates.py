from pathlib import Path

import pytest

from mycelium.database import MemoryDatabase
from mycelium.semantic_candidates import SemanticCandidates


class Embedder:
    model = "test-embedding"

    def __init__(self):
        self.digest = "weights-1"
        self.document_calls = []
        self.query_calls = []
        self.document_vectors = {f"document-{i}": [1.0, i / 100] for i in range(30)}
        self.query_vectors = {"near-first": [1.0, 0.0], "near-last": [-1.0, 1.0]}

    async def identity(self):
        return self.digest

    async def embed_documents(self, documents):
        self.document_calls.append(list(documents))
        return [self.document_vectors[text] for text in documents]

    async def embed_queries(self, queries):
        self.query_calls.append(list(queries))
        return [self.query_vectors[text] for text in queries]


@pytest.fixture
def fixture(tmp_path):
    db = MemoryDatabase(tmp_path / "store")
    embedder = Embedder()
    index = SemanticCandidates(tmp_path / "vectors", embedder, db)
    documents = {f"id-{i:02d}": f"document-{i}" for i in range(30)}
    yield index, embedder, documents
    db.close()


@pytest.mark.asyncio
async def test_bound_fair_query_coverage_and_required_ids(fixture):
    index, embedder, documents = fixture
    result = await index.select(
        documents, ["near-first", "near-last"], limit=4, required_ids=["id-12"]
    )
    assert len(result) == len(set(result)) == 4
    assert result[0] == "id-12"
    assert {"id-00", "id-29"} <= set(result)
    assert all(len(batch) <= 24 for batch in embedder.document_calls)


@pytest.mark.asyncio
async def test_unchanged_candidates_and_queries_survive_reopening_without_embedding(
    fixture,
):
    index, embedder, documents = fixture
    expected = await index.select(documents, ["near-first"], limit=3)
    counts = len(embedder.document_calls), len(embedder.query_calls)
    reopened = SemanticCandidates(Path(index.path), embedder, index.cache_store)
    assert await reopened.select(documents, ["near-first"], limit=3) == expected
    assert (len(embedder.document_calls), len(embedder.query_calls)) == counts


@pytest.mark.asyncio
async def test_only_changed_documents_reembed_and_deleted_ids_cannot_return(fixture):
    index, embedder, documents = fixture
    await index.select(documents, ["near-first"], limit=3)
    del documents["id-00"]
    documents["id-01"] = "changed"
    embedder.document_vectors["changed"] = [-1.0, 0.0]
    result = await index.select(documents, ["near-first"], limit=3)
    assert not {"id-00", "id-01"} & set(result)
    assert embedder.document_calls[-1] == ["changed"]
    assert len(embedder.query_calls) == 1


@pytest.mark.asyncio
async def test_new_weights_and_dimensions_rebuild_vectors_and_query_cache(fixture):
    index, embedder, documents = fixture
    before = await index.select(documents, ["near-first"], limit=3)
    embedder.digest = "weights-2"
    embedder.document_vectors = {
        text: [*vector, 0.1] for text, vector in embedder.document_vectors.items()
    }
    embedder.query_vectors = {
        text: [*vector, 0.1] for text, vector in embedder.query_vectors.items()
    }
    assert await index.select(documents, ["near-first"], limit=3) == before
    assert len(embedder.document_calls) == 4
    assert len(embedder.query_calls) == 2


@pytest.mark.asyncio
async def test_small_or_fully_required_registry_does_not_need_embeddings(fixture):
    index, embedder, documents = fixture
    small = {key: documents[key] for key in ["id-00", "id-01"]}
    assert await index.select(small, [], limit=3) == ["id-00", "id-01"]
    required = ["id-12", "id-15", "id-19"]
    assert await index.select(documents, [], limit=3, required_ids=required) == required
    assert embedder.document_calls == embedder.query_calls == []
    with pytest.raises(ValueError, match="Required"):
        await index.select(documents, [], limit=2, required_ids=required)
    with pytest.raises(ValueError, match="Required"):
        await index.select(documents, [], required_ids=["invented"])


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [[0.0, 0.0], [float("nan"), 1.0], []])
async def test_invalid_embeddings_fail_before_returning_candidates(fixture, invalid):
    index, embedder, documents = fixture
    embedder.document_vectors["document-0"] = invalid
    with pytest.raises(ValueError, match="Embeddings"):
        await index.select(documents, ["near-first"], limit=3)


@pytest.mark.asyncio
async def test_long_documents_keep_later_evidence_and_return_distinct_entities(
    fixture, monkeypatch
):
    index, embedder, documents = fixture
    # A document may contribute many close chunks; they must not crowd out
    # other entity IDs or make a later source chunk unsearchable.
    monkeypatch.setattr(
        "mycelium.semantic_candidates.split_text_by_tokens",
        lambda text, budget: text.split("\n"),
    )
    embedder.document_vectors.update({"early": [-1.0, 0.0], "late": [1.0, 0.0]})
    documents["id-15"] = "early\nlate\nlate\nlate\nlate"
    selected = await index.select(documents, ["near-first"], limit=4)
    assert "id-15" in selected
    assert len(set(selected)) == len(selected) == 4
    embedded = [text for batch in embedder.document_calls for text in batch]
    assert "early" in embedded and embedded.count("late") == 4


@pytest.mark.asyncio
async def test_long_queries_preserve_each_chunk_and_cache_repeated_work(
    fixture, monkeypatch
):
    index, embedder, documents = fixture
    monkeypatch.setattr(
        "mycelium.semantic_candidates.split_text_by_tokens",
        lambda text, budget: text.split("\n"),
    )
    selected = await index.select(documents, ["near-first\nnear-last"], limit=4)
    assert {"id-00", "id-29"} <= set(selected)
    assert embedder.query_calls == [["near-first", "near-last"]]
    await index.select(documents, ["near-first\nnear-last"], limit=4)
    assert len(embedder.query_calls) == 1
