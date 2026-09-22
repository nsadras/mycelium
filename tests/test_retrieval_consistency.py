from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimEntityReference,
    ClaimProvenance,
    ConsolidatedFact,
    SourceSegment,
)
from mycelium.context_selection import (
    AssistantContextSelection,
    AssistantContextSelector,
)
from mycelium.retrieval_context import render_memory_evidence
from mycelium.memory_tools import MemoryToolset
from mycelium.memory_workspace import merge_memory_evidence
from mycelium.operations import (
    EvidenceSegment,
    EvidenceSource,
    EvidenceSourceCitation,
    MemoryEvidence,
    RetrievalError,
    RetrievalRequest,
)
from tests.test_audit_remediation import seed


def place(artifacts, claim, owner, *, with_view=False):
    artifacts.save_entity_reference(ClaimEntityReference("ref-" + claim.claim_id, claim.claim_id,
        "subject", owner.title, owner.entity_id, 1.0, "Fixture", "extraction", "test", "active", "2026-01-01"))
    if not with_view:
        return
    artifacts.save_consolidated_fact(ConsolidatedFact("owned-view", claim.text, [claim.claim_id], owner.entity_id,
        "Interests", "current", [], "manual", 1.0, "Reviewed view", "2026-01-01", "2026-01-01"))


@pytest.mark.asyncio
@pytest.mark.parametrize("change_again", [False, True])
@pytest.mark.parametrize("with_view", [False, True])
async def test_owner_move_reselects_using_canonical_metadata(
    tmp_path, monkeypatch, change_again, with_view
):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, hit = seed(tmp_path)
        first = artifacts.create_entity("person", "First owner")
        second = artifacts.create_entity("person", "Second owner")
        place(artifacts, claim, first, with_view=with_view)
        # The search index can keep returning an older projection after the mutation.
        stale_hit = replace(
            hit, owner_title="Index label", owner_entity_id=first.entity_id
        )
        memory.retriever.claim_index.search = AsyncMock(return_value=[stale_hit])
        seen = []

        async def select(self, query, candidates, **kwargs):
            seen.append(render_memory_evidence(candidates))
            if len(seen) == 1:
                place(artifacts, claim, second, with_view=with_view)
            elif change_again:
                place(artifacts, claim, first, with_view=with_view)
            return AssistantContextSelection(tuple(r.record_id for r in candidates.records), {})

        monkeypatch.setattr(AssistantContextSelector, "select_with_trace", select)
        if change_again:
            with pytest.raises(RetrievalError, match="concurrent_update"):
                await memory.retrieve_context(RetrievalRequest("Preferences?"))
        else:
            result = await memory.retrieve_context(RetrievalRequest("Preferences?"))
            assert result.evidence.records[0].subject_name == second.title
        assert len(seen) == 2 and first.title in seen[0] and second.title in seen[1]
        assert memory.retriever.claim_index.search.await_count == 2


@pytest.mark.asyncio
async def test_consolidation_during_selection_refreshes_admission_and_fact(
    tmp_path, monkeypatch
):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, hit = seed(tmp_path)
        owner = artifacts.create_entity("person", "Nora")
        place(artifacts, claim, owner)
        memory.retriever.claim_index.search = AsyncMock(return_value=[hit])
        seen = []

        async def select(self, query, candidates, **kwargs):
            seen.append(render_memory_evidence(candidates))
            if len(seen) == 1:
                artifacts.save_consolidated_fact(
                    ConsolidatedFact(
                        "f1",
                        "A consolidated preference",
                        [claim.claim_id],
                        owner.entity_id,
                        "interests_views",
                        "current",
                        [],
                        "claim",
                        1.0,
                        "Review",
                        "2026-01-01",
                        "2026-01-01",
                    )
                )
            return AssistantContextSelection(tuple(r.record_id for r in candidates.records), {})

        monkeypatch.setattr(AssistantContextSelector, "select_with_trace", select)
        result = await memory.retrieve_context(RetrievalRequest("Preferences?"))
        assert len(seen) == 2 and "A consolidated preference" in seen[1]
        assert [r.record_id for r in result.evidence.records] == ["c1", "f1"]


@pytest.mark.asyncio
async def test_source_retraction_during_selection_reselects_with_warning(
    tmp_path, monkeypatch
):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, hit = seed(tmp_path)
        source = artifacts.get_source("s1")
        artifacts.save_source(
            replace(
                source,
                source_id="s2",
                segments=[SourceSegment("seg2", 0, source.segments[0].content)],
            )
        )
        artifacts.save_claim(
            replace(
                claim, provenance=[*claim.provenance, ClaimProvenance("s2", ["seg2"])]
            )
        )
        memory.retriever.claim_index.search = AsyncMock(return_value=[hit])
        seen = []

        async def select(self, query, candidates, **kwargs):
            seen.append(render_memory_evidence(candidates))
            if len(seen) == 1:
                artifacts.save_source(
                    replace(
                        source,
                        status="retracted",
                        retracted_at="2026-02-01",
                        retraction_reason="Wrong import",
                    )
                )
            return AssistantContextSelection(tuple(r.record_id for r in candidates.records), {})

        monkeypatch.setattr(AssistantContextSelector, "select_with_trace", select)
        result = await memory.retrieve_context(RetrievalRequest("Preferences?"))
        assert len(seen) == 2
        assert "is retracted" in seen[1]
        assert "is retracted" in result.evidence.records[0].uncertainty[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["source", "segment"])
async def test_missing_provenance_during_selection_is_typed_failure(
    tmp_path, monkeypatch, missing
):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, _, hit = seed(tmp_path)
        memory.retriever.claim_index.search = AsyncMock(return_value=[hit])

        async def select(self, query, candidates, **kwargs):
            if missing == "source":
                artifacts.db.delete("sources", "s1")
            else:
                artifacts.save_source(replace(artifacts.get_source("s1"), segments=[]))
            return AssistantContextSelection(tuple(r.record_id for r in candidates.records), {})

        monkeypatch.setattr(AssistantContextSelector, "select_with_trace", select)
        with pytest.raises(RetrievalError, match="evidence_integrity.*missing"):
            await memory.retrieve_context(RetrievalRequest("Preferences?"))
        assert memory.retriever.claim_index.search.await_count == 2


def test_refresh_rebuilds_source_text_metadata_and_citations(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, _ = seed(tmp_path)
        source = artifacts.get_source("s1")
        source.segments += [SourceSegment("context", 1, "Earlier context")]
        artifacts.save_source(source)
        evidence = memory.retriever.source_evidence(
            [claim.claim_id], budget_tokens=3000
        )
        source.occurred_at = "2026-02-01"
        source.segments = [
            SourceSegment(
                "seg1", 0, "Edited original line", speaker="Corrected speaker"
            ),
            SourceSegment("new", 1, "Uninspected line"),
        ]
        artifacts.save_source(source)
        refreshed = memory.retriever.refresh_evidence(evidence, budget_tokens=3000)
        shown = refreshed.sources[0]
        assert shown.revision > evidence.sources[0].revision
        assert shown.conversation_time == source.occurred_at
        assert [(s.segment_id, s.content, s.speaker) for s in shown.segments] == [
            ("seg1", "Edited original line", "Corrected speaker")
        ]
        assert shown.citations == (EvidenceSourceCitation("c1", ("seg1",)),)
        # A newer snapshot must replace removed excerpts; older replies cannot revive them.
        assert merge_memory_evidence(evidence, refreshed).sources == refreshed.sources
        assert merge_memory_evidence(refreshed, evidence).sources == refreshed.sources


def test_equal_revision_merge_promotes_context_to_cited(tmp_path):
    context = EvidenceSegment("s2", "context", None, "Second line", 1)
    first = EvidenceSource(
        "s",
        "2026-01-01",
        (EvidenceSourceCitation("c1", ("s1",)),),
        (
            EvidenceSegment("s1", "cited", None, "First line", 0),
            context,
        ),
        revision=3,
    )
    second = replace(
        first,
        citations=(EvidenceSourceCitation("c2", ("s2",)),),
        segments=(replace(context, relationship="cited"),),
    )
    merged = merge_memory_evidence(
        MemoryEvidence(sources=(first,)), MemoryEvidence(sources=(second,))
    )
    assert [s.relationship for s in merged.sources[0].segments] == ["cited", "cited"]
    assert {c.claim_id for c in merged.sources[0].citations} == {"c1", "c2"}


@pytest.mark.asyncio
async def test_failed_tool_refreshes_retracted_records_and_excerpts(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, _ = seed(tmp_path)
        evidence = memory.retriever.source_evidence(
            [claim.claim_id], budget_tokens=3000
        )
        toolset = MemoryToolset(
            memory.retriever, request="Preferences?", initial_evidence=evidence
        )
        artifacts.save_claim(replace(claim, status="retracted"))
        result = await toolset.run("memory_sources", {"claim_ids": ["unseen"]})
        assert not toolset.workspace.evidence.records and not toolset.workspace.evidence.sources
        assert claim.text not in result.model_result
        assert result.metadata["workspace_operation"]["status"] == "failed"


@pytest.mark.asyncio
async def test_failed_search_refreshes_edits_made_while_awaiting(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, _ = seed(tmp_path)
        evidence = memory.retriever.source_evidence(
            [claim.claim_id], budget_tokens=3000
        )
        toolset = MemoryToolset(
            memory.retriever, request="Preferences?", initial_evidence=evidence
        )

        async def search(*args, **kwargs):
            source = artifacts.get_source("s1")
            source.segments[0].content = "Corrected source wording"
            artifacts.save_source(source)
            raise RetrievalError("search", "Unavailable")

        memory.retriever.search_evidence = search
        result = await toolset.run("memory_search", {"query": "Additional preferences"})
        assert "Corrected source wording" in result.model_result
        assert result.metadata["workspace_operation"]["status"] == "failed"


@pytest.mark.asyncio
async def test_broken_provenance_clears_stale_workspace_with_explicit_error(tmp_path):
    with Mycelium(tmp_path, memory_profile="none") as memory:
        artifacts, claim, _ = seed(tmp_path)
        evidence = memory.retriever.source_evidence(
            [claim.claim_id], budget_tokens=3000
        )
        toolset = MemoryToolset(
            memory.retriever, request="Preferences?", initial_evidence=evidence
        )
        artifacts.db.delete("sources", "s1")
        result = await toolset.run("memory_sources", {"claim_ids": ["unseen"]})
        assert "evidence_integrity" in result.result
        assert "already shown" in result.result
        assert not toolset.workspace.evidence.records and not toolset.workspace.evidence.sources
