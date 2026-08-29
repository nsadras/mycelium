import pytest
from pydantic import ValidationError

from benchmarks.mycelium_bench.adapters import (
    MemoryRetrievalPlan,
    execute_memory_plan,
    memory_escalation_reason,
)
from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.memory_tools import MemoryToolset


def _claim(
    claim_id: str,
    text: str,
    *,
    entity: str,
    segment_ids: list[str],
    page: str,
) -> MemoryClaim:
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        about=[{"entity": entity, "role": "subject"}],
        provenance=[ClaimProvenance(
            source_id="source-1",
            segment_ids=segment_ids,
            raw_log_entry_id="2026-01-01#session-1",
            speaker=entity,
        )],
        recorded_at="2026-01-01T12:00:00",
        claim_type="event",
        predicate="lost_job" if "lost" in text else "started_business",
    )


def _toolset(tmp_path) -> MemoryToolset:
    store = ArtifactStore(tmp_path / "artifacts")
    store.save_source(SourceDocument(
        source_id="source-1",
        source_type="meeting_transcript",
        session_id="meeting-1",
        recorded_at="2026-01-01T12:00:00",
        occurred_at="2026-01-01T10:00:00",
        participants=["Jon", "Gina"],
        segments=[
            SourceSegment("source-1#seg-0001", 0, "Jon greeted Gina.", speaker="Jon"),
            SourceSegment(
                "source-1#seg-0002",
                1,
                "Jon lost his banking job.",
                speaker="Jon",
                metadata={"source_label": "D1:2"},
            ),
            SourceSegment(
                "source-1#seg-0003", 2, "Jon started a dance business.", speaker="Jon"
            ),
        ],
    ))
    for claim in (
        _claim(
            "claim-job",
            "Jon lost his banking job.",
            entity="Jon",
            segment_ids=["source-1#seg-0002"],
            page="jon",
        ),
        _claim(
            "claim-business",
            "Jon started a dance business.",
            entity="Jon",
            segment_ids=["source-1#seg-0003"],
            page="jon",
        ),
        _claim(
            "claim-gina",
            "Gina opened a clothing store.",
            entity="Gina",
            segment_ids=["source-1#seg-0003"],
            page="gina",
        ),
    ):
        store.save_claim(claim)
    jon = store.create_entity("person", "Jon")
    gina = store.create_entity("person", "Gina")
    for claim_id, owner in (
        ("claim-job", jon), ("claim-business", jon), ("claim-gina", gina)
    ):
        store.save_placement(ClaimPlacement(
            claim_id=claim_id,
            owner_entity_id=owner.entity_id,
            section_key="timeline",
            linked_entity_ids=[],
            status="placed",
            reason="fixture",
            created_at="2026-01-01T12:00:00",
            updated_at="2026-01-01T12:00:00",
        ))
    return MemoryToolset(store)


def test_memory_search_returns_ranked_canonical_claims(tmp_path):
    tools = _toolset(tmp_path)

    results = tools.search("When did Jon lose his banking job?", limit=2)

    assert results[0]["claim_id"] == "claim-job"
    assert results[0]["subjects"] == ["jon"]
    assert results[0]["source_ids"] == ["source-1"]
    assert results[0]["memory_tier"] == "canonical"


def test_memory_search_labels_unconsolidated_claims_as_short_term(tmp_path):
    tools = _toolset(tmp_path)
    claim = _claim(
        "claim-recent",
        "Jon plans a new ceramics class.",
        entity="Jon",
        segment_ids=["source-1#seg-0003"],
        page="jon",
    )
    tools.artifacts.save_claim(claim)

    results = tools.search("Jon ceramics", limit=2)

    recent = next(item for item in results if item["claim_id"] == claim.claim_id)
    assert recent["memory_tier"] == "short_term"
    assert recent["consolidation_status"] == "pending"


def test_memory_expand_follows_shared_entity_page_and_source(tmp_path):
    tools = _toolset(tmp_path)

    results = tools.expand(["claim-job"], limit=3)

    assert results[0]["claim_id"] == "claim-business"
    assert {result["claim_id"] for result in results} == {
        "claim-business", "claim-gina"
    }


def test_memory_sources_returns_exact_provenance_with_one_neighbor(tmp_path):
    tools = _toolset(tmp_path)

    results = tools.sources(["claim-job"], neighbor_count=1)

    assert results[0]["occurred_at"] == "2026-01-01T10:00:00"
    assert [segment["segment_id"] for segment in results[0]["segments"]] == [
        "source-1#seg-0001",
        "source-1#seg-0002",
        "source-1#seg-0003",
    ]
    assert results[0]["segments"][1]["source_label"] == "D1:2"


def test_memory_tool_runner_rejects_unknown_tool(tmp_path):
    tools = _toolset(tmp_path)

    assert "Unknown memory tool" in tools.run("memory_delete", {})


@pytest.mark.parametrize(
    ("question", "reason"),
    [
        ("What do Jon and Gina both have in common?", "composition"),
        ("Why did Jon start a dance studio?", "causal"),
        ("What should the ideal studio look like?", "multi_attribute"),
        ("Do Jon and Gina run their own businesses?", "multiple_subjects"),
        ("When did Jon lose his job?", None),
        ("What is Gina's favorite dance style?", None),
    ],
)
def test_memory_escalation_detects_composed_questions(question, reason):
    assert memory_escalation_reason(question) == reason


def test_memory_retrieval_plan_is_bounded():
    with pytest.raises(ValidationError):
        MemoryRetrievalPlan(
            searches=["one", "two", "three", "four", "five"],
            expand_top_hits=True,
            inspect_sources=False,
        )


def test_execute_memory_plan_gathers_claims_expansion_and_sources(tmp_path):
    tools = _toolset(tmp_path)
    plan = MemoryRetrievalPlan(
        searches=["Jon banking job", "Gina clothing store"],
        expand_top_hits=True,
        inspect_sources=True,
    )

    rendered, trace = execute_memory_plan(tools, plan)

    assert "[claim-job] Jon lost his banking job." in rendered
    assert "[claim-gina] Gina opened a clothing store." in rendered
    assert "VERIFIED SOURCE SEGMENTS" in rendered
    assert [search["query"] for search in trace["searches"]] == plan.searches
    assert set(trace["selected_claim_ids"]) == {
        "claim-job", "claim-business", "claim-gina"
    }
    assert trace["source_ids"] == ["source-1"]
    assert trace["evidence_chars"] == len(rendered)
    assert trace["truncated"] is False
