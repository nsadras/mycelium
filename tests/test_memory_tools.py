from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mycelium.memory_tools import MEMORY_TOOL_DEFINITIONS, MemoryToolset
from mycelium.memory_workspace import merge_memory_evidence
from mycelium.operations import (
    EvidenceRecord,
    EvidenceSegment,
    EvidenceSource,
    EvidenceSourceCitation,
    MemoryEvidence,
)
from mycelium.budget import count_tokens
from mycelium.retrieval_context import (
    render_memory_evidence,
    render_memory_search_result,
)


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
                        citations=(
                            EvidenceSourceCitation(
                                claim_id="claim-2",
                                segment_ids=("source-2#seg-1",),
                            ),
                        ),
                        segments=(
                            EvidenceSegment(
                                segment_id="source-2#seg-1",
                                relationship="cited",
                                speaker="Mira",
                                content="exact dialogue for claim two",
                                index=1,
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
        request="What happened?",
        initial_evidence=_result("initial evidence", ["claim-1"]).evidence,
    ), retriever


def test_memory_tool_schemas_expose_search_and_source_inspection():
    names = [definition["function"]["name"] for definition in MEMORY_TOOL_DEFINITIONS]

    assert names == ["memory_sources", "memory_search"]
    assert all("parameters" in definition["function"] for definition in MEMORY_TOOL_DEFINITIONS)


@pytest.mark.asyncio
async def test_memory_search_uses_ranked_retrieval_and_accumulates_claim_ids():
    tools, retriever = _toolset()

    result = await tools.search("Mira's weekend music", limit=3)

    retriever.search_evidence.assert_awaited_once_with(
        "Mira's weekend music",
        limit=3,
        budget_tokens=(
            1000
            - count_tokens(
                render_memory_search_result(
                    MemoryEvidence(),
                    query="Mira's weekend music",
                    remaining_searches=1,
                )
            )
        ),
        exclude_claim_ids={"claim-1"},
    )
    assert result.evidence.claim_ids == ("claim-2",)
    assert result.evidence.records[0].statement == "evidence for claim two"
    assert tools.returned_claim_ids == {"claim-1", "claim-2"}


@pytest.mark.asyncio
async def test_memory_search_is_bounded_across_one_response():
    tools, retriever = _toolset(search_limit=1)

    await tools.search("first missing relation")
    with pytest.raises(ValueError, match="search limit"):
        await tools.search("second missing relation")

    assert retriever.search_evidence.await_count == 1


@pytest.mark.asyncio
async def test_memory_sources_only_reads_claims_already_returned():
    tools, retriever = _toolset()
    await tools.search("missing event")

    result = tools.sources(["claim-2", "unseen-claim"])

    retriever.source_evidence.assert_called_once()
    assert result.claim_ids == ("claim-2",)
    source = result.evidence.sources[0]
    assert source.segments[0].content == "exact dialogue for claim two"


def test_memory_sources_rejects_unseen_claim_ids():
    tools, _ = _toolset()

    with pytest.raises(ValueError, match="shown in this response"):
        tools.sources(["unseen-claim"])


@pytest.mark.asyncio
async def test_tool_runner_returns_structured_text_and_defers_non_memory_tools():
    tools, _ = _toolset()

    memory_result = await tools.run("memory_search", {"query": "missing event"})
    web_result = await tools.run("web_search", {"query": "current event"})

    assert memory_result.result.startswith("<memory-search-results>")
    assert memory_result.metadata["workspace_revision"] == 1
    assert tools.workspace.snapshot.evidence.claim_ids == ("claim-1", "claim-2")
    assert web_result is None


@pytest.mark.asyncio
async def test_source_tool_result_associates_claim_with_cited_transcript_line():
    tools, _ = _toolset()
    await tools.run("memory_search", {"query": "missing event"})

    result = await tools.run(
        "memory_sources", {"claim_ids": ["claim-2"]}
    )

    assert result.result.startswith("<memory-source-results>")
    assert result.metadata["workspace_revision"] == 2
    source = tools.workspace.snapshot.evidence.sources[0]
    assert source.citations[0].claim_id == "claim-2"
    assert source.segments[0].content == "exact dialogue for claim two"


@pytest.mark.asyncio
async def test_memory_evidence_budget_is_cumulative():
    tools, retriever = _toolset(evidence_budget_tokens=1)

    with pytest.raises(ValueError, match="budget has been exhausted"):
        await tools.search("missing event")

    retriever.search_evidence.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_memory_operation_is_recorded_without_changing_evidence():
    tools, _ = _toolset()

    result = await tools.run(
        "memory_sources", {"claim_ids": ["claim-not-shown"]}
    )

    workspace = tools.workspace.snapshot
    assert result.metadata["workspace_revision"] == 1
    assert workspace.evidence.claim_ids == ("claim-1",)
    assert workspace.operations[0].status == "failed"
    assert workspace.operations[0].error


def test_workspace_merges_source_segments_in_chronological_order():
    def evidence(segment_id: str, index: int, claim_id: str) -> MemoryEvidence:
        return MemoryEvidence(sources=(EvidenceSource(
            source_id="source-shared",
            conversation_time="2026-01-01T00:00:00+00:00",
            citations=(EvidenceSourceCitation(
                claim_id=claim_id,
                segment_ids=(segment_id,),
            ),),
            segments=(EvidenceSegment(
                segment_id=segment_id,
                relationship="cited",
                speaker="Mira",
                content=claim_id,
                index=index,
            ),),
        ),))

    merged = merge_memory_evidence(
        evidence("source-shared#seg-3", 3, "claim-3"),
        evidence("source-shared#seg-1", 1, "claim-1"),
    )

    assert [segment.index for segment in merged.sources[0].segments] == [1, 3]
    assert [citation.claim_id for citation in merged.sources[0].citations] == [
        "claim-3",
        "claim-1",
    ]
