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

    assert result.page_references == ()
    assert result.rendered_context == (
        "<memory-evidence>\nNo memory evidence found.\n</memory-evidence>"
    )
    assert result.trace["candidates"] == []


@pytest.mark.asyncio
async def test_multi_turn_session_retains_turns_with_unique_idempotency_keys(tmp_path):
    memory = Mycelium(store_path=tmp_path / "store", memory_profile="none")

    async with memory.session("Turn 1", session_id="shared-session") as sess:
        sess.record("user", "Hello there")
        sess.record("assistant", "General Kenobi")

    async with memory.session("Turn 2", session_id="shared-session") as sess:
        sess.record("user", "What did we just discuss?")
        sess.record("assistant", "A Star Wars meme.")

    sources = memory.artifacts.list_sources()
    assert len(sources) == 2
    assert all(source.session_id == "shared-session" for source in sources)
    assert len(memory.artifacts.list_episodes()) == 2
