from dataclasses import replace

from mycelium import Mycelium
from mycelium.artifacts import ClaimProvenance, SourceSegment
from mycelium.budget import count_tokens
from mycelium.operations import MemoryEvidence
from mycelium.retrieval_context import RetrievedContextBuilder, render_memory_evidence
from mycelium.store import WikiStore
from tests.test_audit_remediation import seed


def test_shared_exact_excerpt_keeps_each_claim_and_historical_state(tmp_path):
    artifacts, claim, hit = seed(tmp_path)
    old = replace(claim, claim_id="old", status="superseded")
    artifacts.save_claim(old)
    builder = RetrievedContextBuilder(WikiStore(tmp_path / "wiki"), artifacts)
    result = builder.build([hit, replace(hit, claim_id="old")], budget_tokens=2000)
    assert len(result.sources) == 1
    assert len(result.sources[0].segments) == 1
    assert {c.claim_id for c in result.sources[0].citations} == {"c1", "old"}
    assert {r.record_id: r.state for r in result.records}["old"] == "superseded"
    assert len({r.revision for r in (*result.records, *result.sources)}) == 1


def test_partial_source_budget_keeps_whole_cited_segments_without_neighbor_leaks(
    tmp_path,
):
    artifacts, claim, hit = seed(tmp_path)
    source = artifacts.get_source("s1")
    source.segments = [
        SourceSegment("huge", 0, "Long discussion. " * 3000),
        SourceSegment("seg1", 1, "Nora does not drink tea."),
        SourceSegment("neighbor", 2, "Uncited surrounding dialogue."),
    ]
    artifacts.save_source(source)
    artifacts.save_claim(
        replace(claim, provenance=[ClaimProvenance("s1", ["huge", "seg1"])])
    )
    builder = RetrievedContextBuilder(WikiStore(tmp_path / "wiki"), artifacts)
    result = builder.build([hit], budget_tokens=500)
    assert result.more_available
    assert result.records[0].claim_ids == ("c1",)
    assert [s.content for s in result.sources[0].segments] == [
        "Nora does not drink tea."
    ]
    assert result.sources[0].citations[0].segment_ids == ("seg1",)
    assert count_tokens(render_memory_evidence(result)) <= 500
    artifacts.save_claim(replace(claim, provenance=[ClaimProvenance("s1", ["huge"])]))
    inspected = builder.source_evidence(["c1"], budget_tokens=500)
    assert inspected.records and inspected.more_available
    assert inspected.sources == ()  # Context requires a retained cited anchor.


def test_omitted_interpretations_do_not_leak_their_sources(tmp_path):
    artifacts, claim, hit = seed(tmp_path)
    source = artifacts.get_source("s1")
    artifacts.save_source(
        replace(
            source,
            source_id="s2",
            segments=[SourceSegment("other", 0, "Private unrelated source.")],
        )
    )
    artifacts.save_claim(
        replace(
            claim,
            claim_id="large",
            text="An oversized record. " * 1000,
            provenance=[ClaimProvenance("s2", ["other"])],
        )
    )
    builder = RetrievedContextBuilder(WikiStore(tmp_path / "wiki"), artifacts)
    result = builder.build([replace(hit, claim_id="large"), hit], budget_tokens=500)
    assert result.claim_ids == ("c1",)
    assert {s.source_id for s in result.sources} == {"s1"}
    assert result.more_available


def test_refresh_adds_current_citations_to_old_claim_only_workspace(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, hit = seed(tmp_path)
        initial = memory.retriever.context_builder.build([hit], budget_tokens=2000)
        claim_only = MemoryEvidence(records=initial.records)
        source = artifacts.get_source("s1")
        artifacts.save_source(
            replace(
                source,
                source_id="s2",
                segments=[SourceSegment("new", 0, "Nora prefers coffee.")],
            )
        )
        artifacts.save_claim(
            replace(
                claim,
                text="Nora prefers coffee.",
                provenance=[ClaimProvenance("s2", ["new"])],
            )
        )
        for old in (initial, claim_only):
            refreshed = memory.retriever.refresh_evidence(old, budget_tokens=2000)
            assert refreshed.records[0].statement == "Nora prefers coffee."
            assert {s.source_id for s in refreshed.sources} == {"s2"}
            assert refreshed.sources[0].segments[0].segment_id == "new"
            assert refreshed.sources[0].revision > initial.sources[0].revision
