from dataclasses import replace

import pytest

from mycelium import Mycelium
from mycelium.artifacts import ClaimProvenance, MemoryClaim, SourceDocument, SourceSegment
from mycelium.budget import count_tokens
from mycelium.claim_index import ClaimSearchHit
from mycelium.memory_tools import MemoryToolset
from mycelium.memory_workspace import merge_memory_evidence
from mycelium.evidence_budget import fit_memory_evidence
from mycelium.evidence_rendering import render_memory_evidence


def recording(memory):
    segments = [SourceSegment(f"recording#seg-{i+1:04d}", i,
        f"Workshop note {i}. The equipment will stay in the room until the group reviews the arrangements.",
        speaker="Speaker") for i in range(100)]
    memory.artifacts.save_source(SourceDocument("recording", "meeting_transcript", "meeting",
        "2031-04-02", None, ["Speaker"], segments))
    claim = MemoryClaim("memory", "The group is discussing equipment arrangements.", [],
        [ClaimProvenance("recording", [s.segment_id for s in segments])], "2031-04-02")
    memory.artifacts.save_claim(claim)
    return claim


def segment_ids(evidence):
    return {s.segment_id for source in evidence.sources for s in source.segments}


def test_refresh_only_refreshes_previously_shown_excerpts(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        claim = recording(memory)
        initial = memory.retriever.source_evidence([claim.claim_id], budget_tokens=700)
        assert 0 < len(segment_ids(initial)) < 100
        refreshed = memory.retriever.refresh_evidence(initial, budget_tokens=3000)
        assert segment_ids(refreshed) == segment_ids(initial)
        source = memory.artifacts.get_source("recording")
        shown = segment_ids(initial)
        source.segments = [replace(s, content="Corrected source wording.") if s.segment_id in shown else s for s in source.segments]
        memory.artifacts.save_source(source)
        refreshed = memory.retriever.refresh_evidence(initial, budget_tokens=3000)
        assert segment_ids(refreshed) == shown
        assert all(s.content == "Corrected source wording." for source in refreshed.sources for s in source.segments)


def test_workspace_fitting_keeps_whole_segments_when_source_group_is_large(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        claim = recording(memory)
        evidence = memory.retriever.source_evidence([claim.claim_id], budget_tokens=2000)
        fitted = fit_memory_evidence(evidence, lambda e: count_tokens(render_memory_evidence(e)) <= 1700)
        assert 0 < len(segment_ids(fitted)) < len(segment_ids(evidence))
        original = {s.segment_id: s for source in evidence.sources for s in source.segments}
        assert all(s == original[s.segment_id] for source in fitted.sources for s in source.segments)
        assert count_tokens(render_memory_evidence(fitted)) <= 1700


@pytest.mark.asyncio
async def test_source_tool_preserves_existing_excerpts_and_spends_on_new_evidence(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        claim = recording(memory)
        initial = memory.retriever.source_evidence([claim.claim_id], budget_tokens=700)
        tools = MemoryToolset(memory.retriever, request="Inspect the discussion.", initial_evidence=initial,
            evidence_budget_tokens=1300)
        old = segment_ids(initial)
        assert old
        result = await tools.run("memory_sources", {"claim_ids": [claim.claim_id]})
        shown = segment_ids(tools.workspace.evidence)
        assert old < shown
        assert count_tokens(result.model_result) <= tools.workspace_budget_tokens
        assert 0 <= tools.remaining_evidence_tokens < 1300
        # Canonical retraction must still remove the excerpts, even on a failed tool.
        memory.artifacts.save_claim(replace(claim, status="retracted"))
        result = await tools.run("memory_sources", {"claim_ids": ["unseen"]})
        assert not tools.workspace.evidence.sources
        assert not tools.workspace.evidence.records


def test_source_reads_advance_through_unseen_segments(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        claim = recording(memory)
        evidence = memory.retriever.source_evidence([claim.claim_id], budget_tokens=700)
        for _ in range(3):
            previous = segment_ids(evidence)
            result = memory.retriever.source_evidence([claim.claim_id], budget_tokens=300, known_evidence=evidence)
            assert segment_ids(result) and not (segment_ids(result) & previous)
            combined = merge_memory_evidence(evidence, result)
            assert count_tokens(render_memory_evidence(combined)) - count_tokens(render_memory_evidence(evidence)) <= 300
            evidence = combined


@pytest.mark.asyncio
async def test_repeated_source_read_reports_when_every_excerpt_is_already_shown(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        claim = recording(memory)
        initial = memory.retriever.source_evidence([claim.claim_id], budget_tokens=20000)
        tools = MemoryToolset(memory.retriever, request="Inspect.", initial_evidence=initial)
        result = await tools.run("memory_sources", {"claim_ids": [claim.claim_id]})
        assert segment_ids(tools.workspace.evidence) == segment_ids(initial)
        assert tools.remaining_evidence_tokens == 6000
        assert "No additional" in result.model_result


@pytest.mark.asyncio
async def test_source_tool_adds_neighboring_dialogue_after_cited_line_is_shown(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        claim = recording(memory)
        claim = replace(claim, provenance=[ClaimProvenance("recording", ["recording#seg-0050"])])
        memory.artifacts.save_claim(claim)
        hit = ClaimSearchHit(claim.claim_id, claim.text, "short_term", None, None, None, None, None)
        initial = memory.retriever.context_builder.build([hit], budget_tokens=2000)
        assert segment_ids(initial) == {"recording#seg-0050"}
        tools = MemoryToolset(memory.retriever, request="Inspect the surrounding discussion.", initial_evidence=initial)
        await tools.run("memory_sources", {"claim_ids": [claim.claim_id]})
        final = tools.workspace.evidence
        assert segment_ids(final) == {"recording#seg-0048", "recording#seg-0049", "recording#seg-0050", "recording#seg-0051"}
        assert final.sources[0].citations[0].segment_ids == ("recording#seg-0050",)
        refreshed = memory.retriever.refresh_evidence(final, budget_tokens=3000)
        assert refreshed.sources == final.sources


def test_unchanged_refresh_does_not_expand_citation_links_to_other_shown_segments(tmp_path):
    from mycelium.operations import EvidenceSourceCitation
    with Mycelium(tmp_path, memory_profile="none") as memory:
        claim = recording(memory)
        initial = memory.retriever.source_evidence([claim.claim_id], budget_tokens=700)
        source = initial.sources[0]
        # The workspace may have inspected other segments through a different claim.
        shown = replace(source, citations=(EvidenceSourceCitation(claim.claim_id, (source.segments[0].segment_id,)),))
        refreshed = memory.retriever.context_builder.refresh_sources((shown,))[0]
        assert refreshed.citations == shown.citations
        assert {s.segment_id for s in refreshed.segments} == {s.segment_id for s in shown.segments}
