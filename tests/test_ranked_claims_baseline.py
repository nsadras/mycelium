from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from benchmarks.experiments.ranked_claims_baseline import retrieve_ranked_claims
from mycelium.claim_index import ClaimSearchHit
from mycelium.operations import RetrievalRequest
from mycelium.retrieval import MemoryRetriever
from mycelium.store import WikiStore
from tests.memory_helpers import claim, fact, place, setup_owner


@pytest.mark.asyncio
async def test_ranked_control_keeps_canonical_state_and_citations_without_fact_prose(
    tmp_path,
):
    artifacts = setup_owner(tmp_path)
    rows = [claim(f"c{i}", f"Source assertion {i}.", "2031-05-03") for i in range(4)]
    for row in rows:
        place(artifacts, row)
    artifacts.save_claim(replace(rows[0], dream_disposition="excluded_source_policy"))
    artifacts.save_claim(replace(rows[1], status="retracted"))
    artifacts.save_claim(replace(rows[2], status="superseded"))
    artifacts.save_consolidated_fact(
        replace(fact(rows[3]), text="Derived combined prose.")
    )
    hits = [
        ClaimSearchHit(
            row.claim_id, "Stale indexed text", "canonical", None, None, None, None, 1.0
        )
        for row in rows
    ]
    index = SimpleNamespace(search=AsyncMock(return_value=hits), candidate_limit=20)
    llm = AsyncMock()
    retriever = MemoryRetriever(
        llm,
        WikiStore(tmp_path / "wiki"),
        artifacts,
        default_budget_tokens=3000,
        claim_index=index,
        initial_result_limit=2,
    )
    result = await retrieve_ranked_claims(
        retriever, RetrievalRequest(query="What is known?")
    )
    assert set(result.evidence.claim_ids) == {"c2", "c3"}
    assert all(record.record_type == "claim" for record in result.evidence.records)
    assert result.evidence.records[0].state == "superseded"
    assert "Derived combined prose" not in result.rendered_context
    assert "Stale indexed text" not in result.rendered_context
    assert "Source assertion 3" in result.rendered_context
    assert result.evidence.sources and all(r.citations for r in result.evidence.records)
    assert result.page_references == ()
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_ranked_control_enforces_same_result_and_context_bounds(tmp_path):
    artifacts = setup_owner(tmp_path)
    rows = [
        claim(f"c{i}", "Recorded assertion " + "long " * 600, "2031-05-03")
        for i in range(3)
    ]
    for row in rows:
        place(artifacts, row)
    hits = [
        ClaimSearchHit(row.claim_id, row.text, "canonical", None, None, None, None, 1.0)
        for row in rows
    ]
    index = SimpleNamespace(search=AsyncMock(return_value=hits), candidate_limit=20)
    retriever = MemoryRetriever(
        AsyncMock(),
        WikiStore(tmp_path / "wiki"),
        artifacts,
        default_budget_tokens=3000,
        claim_index=index,
        initial_result_limit=1,
    )
    result = await retrieve_ranked_claims(
        retriever, RetrievalRequest(query="What is known?", budget_tokens=300)
    )
    from mycelium.budget import count_tokens

    assert len(result.trace["selected_claim_ids"]) == 1
    assert not result.evidence.records
    assert count_tokens(result.rendered_context) <= 300
