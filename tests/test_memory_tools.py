import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mycelium.memory_tools import MEMORY_TOOL_DEFINITIONS, MemoryToolset
from mycelium.operations import (
    EvidenceRecord,
    EvidenceSegment,
    EvidenceSource,
    MemoryEvidence,
)
from mycelium.retrieval_context import render_memory_evidence


def _result(context: str, claim_ids: list[str]):
    evidence = MemoryEvidence(
        records=tuple(
            EvidenceRecord(
                record_id=claim_id,
                record_type="claim",
                statement=context,
                subject_entity_id=None,
                subject_name=None,
                claim_ids=(claim_id,),
            )
            for claim_id in claim_ids
        )
    )
    return SimpleNamespace(
        evidence=evidence,
        rendered_context=render_memory_evidence(evidence),
        trace={"returned_claim_ids": claim_ids},
    )


def _toolset(*, evidence_budget_tokens: int = 1000, search_limit: int = 2):
    retriever = SimpleNamespace(
        search_evidence=AsyncMock(
            side_effect=[
                _result("evidence for claim two", ["claim-2"]),
                _result("evidence for claim three", ["claim-3"]),
            ]
        ),
        source_evidence=Mock(
            return_value=MemoryEvidence(
                sources=(
                    EvidenceSource(
                        source_id="source-2",
                        conversation_time="2026-01-01T00:00:00+00:00",
                        segments=(
                            EvidenceSegment(
                                segment_id="source-2#seg-1",
                                relationship="cited",
                                speaker="Mira",
                                content="exact dialogue for claim two",
                            ),
                        ),
                    ),
                )
            )
        ),
    )
    return MemoryToolset(
        retriever,
        result_limit=4,
        search_limit=search_limit,
        evidence_budget_tokens=evidence_budget_tokens,
        initial_claim_ids=["claim-1"],
    ), retriever


def test_memory_tool_schemas_expose_search_and_source_inspection():
    names = [definition["function"]["name"] for definition in MEMORY_TOOL_DEFINITIONS]

    assert names == ["memory_sources", "memory_search"]
    functions = {
        definition["function"]["name"]: definition["function"]
        for definition in MEMORY_TOOL_DEFINITIONS
    }
    search = functions["memory_search"]
    sources = functions["memory_sources"]
    assert "additional structured claim or fact records" in search["description"]
    assert "unresolved evidence requirement" not in search["description"]
    assert "exact cited source lines" in sources["description"]
    assert "supporting claim IDs" in sources["description"]


@pytest.mark.asyncio
async def test_memory_search_uses_ranked_retrieval_and_accumulates_claim_ids():
    tools, retriever = _toolset()

    result = await tools.search("Mira's weekend music", limit=3)

    retriever.search_evidence.assert_awaited_once_with(
        "Mira's weekend music",
        limit=3,
        budget_tokens=1000,
        exclude_claim_ids={"claim-1"},
    )
    assert result["claim_ids"] == ["claim-2"]
    assert result["memory_evidence"]["records"][0]["statement"] == (
        "evidence for claim two"
    )
    assert tools.returned_claim_ids == {"claim-1", "claim-2"}


@pytest.mark.asyncio
async def test_memory_search_is_bounded_across_one_response():
    tools, retriever = _toolset(search_limit=1)

    await tools.search("first missing relation")
    result = await tools.search("second missing relation")

    assert "limit" in result["error"]
    assert retriever.search_evidence.await_count == 1


@pytest.mark.asyncio
async def test_memory_sources_only_reads_claims_already_returned():
    tools, retriever = _toolset()
    await tools.search("missing event")

    result = tools.sources(["claim-2", "unseen-claim"])

    retriever.source_evidence.assert_called_once()
    assert result["claim_ids"] == ["claim-2"]
    source = result["memory_evidence"]["sources"][0]
    assert source["segments"][0]["content"] == "exact dialogue for claim two"


def test_memory_sources_rejects_unseen_claim_ids():
    tools, _ = _toolset()

    with pytest.raises(ValueError, match="shown in this response"):
        tools.sources(["unseen-claim"])


@pytest.mark.asyncio
async def test_tool_runner_returns_json_and_defers_non_memory_tools():
    tools, _ = _toolset()

    memory_result = await tools.run("memory_search", {"query": "missing event"})
    web_result = await tools.run("web_search", {"query": "current event"})

    assert json.loads(memory_result)["claim_ids"] == ["claim-2"]
    assert web_result is None


@pytest.mark.asyncio
async def test_memory_evidence_budget_is_cumulative():
    tools, retriever = _toolset(evidence_budget_tokens=1)

    await tools.search("missing event")
    result = await tools.search("another event")

    assert result["error"] == "The memory evidence budget has been exhausted."
    assert retriever.search_evidence.await_count == 1
