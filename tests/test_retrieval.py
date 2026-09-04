from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    ConsolidatedFact,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.claim_index import ClaimSearchHit
from mycelium.budget import count_tokens
from mycelium.operations import RetrievalRequest
from mycelium.retrieval import MemoryRetriever
from mycelium.store import WikiStore


@pytest.mark.asyncio
async def test_retrieval_selects_claims_then_renders_facts_with_exact_evidence(
    tmp_path,
):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    source = SourceDocument(
        source_id="source-1",
        source_type="conversation",
        session_id="session-1",
        recorded_at="2026-01-01T00:00:00+00:00",
        occurred_at="2026-01-01T00:00:00+00:00",
        participants=["Mira"],
        segments=[
            SourceSegment(
                "segment-outside",
                0,
                "This earlier turn is outside the bounded neighborhood.",
                speaker="Jonah",
                metadata={"parent_segment_index": 0},
            ),
            SourceSegment(
                "segment-before-2",
                1,
                "What do you do on weekends?",
                speaker="Jonah",
                metadata={"parent_segment_index": 1},
            ),
            SourceSegment(
                "segment-before-1",
                2,
                "I keep a regular music routine.",
                speaker="Mira",
                metadata={"parent_segment_index": 2},
            ),
            SourceSegment(
                "segment-1",
                3,
                "I practice cello every Saturday.",
                speaker="Mira",
                metadata={"source_label": "D1:4", "parent_segment_index": 3},
            ),
            SourceSegment(
                "segment-after",
                4,
                "That sounds relaxing.",
                speaker="Jonah",
                metadata={"parent_segment_index": 4},
            ),
        ],
    )
    artifacts.save_source(source)
    claim = MemoryClaim(
        claim_id="claim-1",
        text="Mira practices cello every Saturday.",
        about=[{"entity": "Mira", "role": "subject"}],
        provenance=[ClaimProvenance("source-1", ["segment-1"])],
        recorded_at="2026-01-01T00:00:00+00:00",
        dream_disposition="routed",
        facets={
            "temporal": {
                "role": "recurrence",
                "start": "2026-01-03",
                "end": "2026-01-03",
                "expression": "every Saturday",
            }
        },
    )
    artifacts.save_claim(claim)
    entity = artifacts.create_entity("person", "Mira")
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
    artifacts.save_consolidated_fact(
        ConsolidatedFact(
            "fact-1",
            "Mira practices the cello each Saturday.",
            [claim.claim_id],
            entity.entity_id,
            "timeline",
            "current",
            [],
            "claim",
            0.9,
            "test",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
        )
    )
    index = AsyncMock()
    index.embedder = SimpleNamespace(model="embeddinggemma:latest")
    index.candidate_limit = 20
    index.search.return_value = [
        ClaimSearchHit(
            claim.claim_id,
            claim.text,
            "canonical",
            entity.entity_id,
            entity.title,
            entity.slug,
            "timeline",
            0.8,
        )
    ]
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "decisions": {
            "M001": {
                "disposition": "include",
                "confidence": 0.95,
                "reason": "It answers the question.",
            }
        }
    }
    retriever = MemoryRetriever(
        llm, wiki, artifacts, default_budget_tokens=2000, claim_index=index
    )

    result = await retriever.retrieve(RetrievalRequest("When does Mira practice?"))

    selection_user_prompt = llm.call_structured.await_args.args[1]
    assert "Claim: Mira practices cello every Saturday." in selection_user_prompt
    assert "Structured timing: recurrence 2026-01-03" in selection_user_prompt
    assert "Consolidated representations:" in selection_user_prompt
    assert "Mira practices the cello each Saturday." in selection_user_prompt
    assert "Mira practices the cello each Saturday." in result.rendered_context
    record = result.evidence.records[0]
    assert record.record_type == "fact"
    assert record.subject_entity_id == entity.entity_id
    assert record.subject_name == "Mira"
    assert record.claim_ids == ("claim-1",)
    assert record.temporal[0].role == "recurrence"
    assert record.temporal[0].start == "2026-01-03"
    assert record.citations[0].segment_ids == ("segment-1",)
    assert record.citations[0].source_time == "2026-01-01T00:00:00+00:00"
    assert result.evidence.sources == ()
    assert "source_evidence" not in result.rendered_context
    assert count_tokens(result.rendered_context) <= 2000

    expanded = retriever.source_evidence(["claim-1"], budget_tokens=2000)

    source_evidence = expanded.sources[0]
    assert source_evidence.conversation_time == "2026-01-01T00:00:00+00:00"
    assert source_evidence.segments[0].relationship == "cited"
    assert source_evidence.segments[0].content == "I practice cello every Saturday."
    context = [
        segment.content
        for segment in source_evidence.segments
        if segment.relationship == "context"
    ]
    assert "What do you do on weekends?" in context
    assert "That sounds relaxing." in context
    assert "This earlier turn is outside the bounded neighborhood." not in context
    assert result.trace["selected_claim_ids"] == ["claim-1"]
    assert result.trace["rendered_claim_ids"] == ["claim-1"]
