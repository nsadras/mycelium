import pytest

from mycelium.claim_index import LanceClaimIndex
from mycelium.core import Mycelium
from mycelium.operations import RetrievalRequest


def test_core_composes_store_owned_claim_index(tmp_path):
    memory = Mycelium(store_path=tmp_path / "store")

    assert isinstance(memory.retriever.claim_index, LanceClaimIndex)
    assert memory.retriever.claim_index.path == (
        tmp_path / "store" / "indexes" / "lancedb"
    )
    assert memory.retriever.claim_index.embedder.model == "embeddinggemma:latest"


@pytest.mark.asyncio
async def test_empty_memory_retrieval_does_not_call_embedding_or_chat_models(tmp_path):
    memory = Mycelium(store_path=tmp_path / "store", memory_profile="none")

    result = await memory.retrieve_context(RetrievalRequest("Any remembered plans?"))

    assert result.pages == ()
    assert result.rendered_context == (
        "<memory-evidence>\nNo memory evidence found.\n</memory-evidence>"
    )
    assert result.trace["candidates"] == []
