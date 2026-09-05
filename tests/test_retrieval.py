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
from mycelium.models import WikiPage
from mycelium.retrieval import MemoryRetriever
from mycelium.retrieval_context import (
    RetrievedContextBuilder,
    render_memory_evidence,
    render_memory_source_result,
)
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
    assert source_evidence.citations[0].claim_id == "claim-1"
    assert source_evidence.citations[0].segment_ids == ("segment-1",)
    cited = next(
        segment
        for segment in source_evidence.segments
        if segment.relationship == "cited"
    )
    assert cited.content == "I practice cello every Saturday."
    assert [segment.segment_id for segment in source_evidence.segments] == [
        "segment-before-2",
        "segment-before-1",
        "segment-1",
        "segment-after",
    ]
    context = [
        segment.content
        for segment in source_evidence.segments
        if segment.relationship == "context"
    ]
    assert "What do you do on weekends?" in context
    assert "That sounds relaxing." in context
    assert "This earlier turn is outside the bounded neighborhood." not in context
    rendered_sources = render_memory_source_result(
        expanded, requested_claim_ids=["claim-1"]
    )
    assert (
        "Supports claims:\n- `claim-1`: cited segments `segment-1`" in rendered_sources
    )
    transcript = rendered_sources.split("<transcript>", 1)[1]
    assert transcript.index("segment-before-2") < transcript.index("segment-1")
    assert transcript.index("segment-1") < transcript.index("segment-after")
    assert 'cited-for="claim-1"' in rendered_sources
    assert result.trace["selected_claim_ids"] == ["claim-1"]
    assert result.trace["rendered_claim_ids"] == ["claim-1"]

    # Two index hits for one consolidated fact must not duplicate its evidence.
    index.search.return_value *= 2
    duplicate = await retriever.search_evidence("music", limit=5, budget_tokens=2000)
    assert duplicate.evidence.records == result.evidence.records


@pytest.fixture
def compact_claim(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    entity = artifacts.create_entity("person", "Nora")
    artifacts.save_source(
        SourceDocument(
            source_id="source-note",
            source_type="conversation",
            session_id="session-note",
            recorded_at="2026-09-01T12:00:00+00:00",
            occurred_at=None,
            participants=["Nora"],
            segments=[
                SourceSegment("segment-note", 0, "Long surrounding discussion. " * 200)
            ],
        )
    )
    claim = MemoryClaim(
        claim_id="claim-note",
        text="Nora prefers morning meetings.",
        about=[],
        provenance=[ClaimProvenance("source-note", ["segment-note"])],
        recorded_at="2026-09-01T12:00:00+00:00",
    )
    artifacts.save_claim(claim)
    hit = ClaimSearchHit(
        claim.claim_id,
        claim.text,
        "short_term",
        entity.entity_id,
        entity.title,
        entity.slug,
        None,
        0.9,
    )
    return RetrievedContextBuilder(wiki, artifacts), hit, entity


def test_compact_record_fits_exact_budget_without_expanding_transcript(compact_claim):
    builder, hit, _ = compact_claim
    full = builder.build([hit], budget_tokens=2000)
    budget = count_tokens(render_memory_evidence(full))

    fitted = builder.build([hit], budget_tokens=budget)

    assert fitted == full
    assert fitted.records[0].citations[0].segment_ids == ("segment-note",)
    assert fitted.sources == ()
    omitted = builder.build([hit], budget_tokens=budget - 1)
    assert omitted.records == ()
    assert omitted.more_available
    assert count_tokens(render_memory_evidence(omitted)) <= budget - 1


def test_retrieval_page_references_only_describe_real_pages(compact_claim):
    builder, hit, entity = compact_claim
    evidence = builder.build([hit, hit], budget_tokens=2000)
    assert len(evidence.records) == 1
    assert builder.page_references(evidence) == ()
    builder.wiki.save(
        WikiPage(
            slug=entity.slug,
            title=entity.title,
            entity_id=entity.entity_id,
            page_type="person",
            content="Human-facing briefing",
            created=None,
            last_updated=None,
            version=3,
        )
    )

    references = builder.page_references(evidence)

    assert len(references) == 1
    assert references[0].slug == entity.slug
    assert references[0].version == 3
    assert not hasattr(references[0], "content")
    assert builder.build([hit], budget_tokens=2000) == evidence


def test_retrieval_rejects_budget_smaller_than_evidence_envelope(compact_claim):
    builder, hit, _ = compact_claim
    with pytest.raises(ValueError, match="empty evidence envelope"):
        builder.build([hit], budget_tokens=0)
