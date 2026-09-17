
from mycelium.config import Config
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from mycelium.artifact_integrity import cited_source_segments, coverage_report
from mycelium.artifacts import ClaimProvenance, SourceDocument, SourceSegment
from mycelium.consolidation_formatting import RoutingFormatter
from mycelium.consolidation_models import ClaimEvidence
from mycelium.facts import FactResolver
from mycelium.truth_review import TruthReviewer
from tests.memory_helpers import claim, place, setup_owner


def damaged_claim(tmp_path, damage):
    artifacts = setup_owner(tmp_path)
    item = claim("record", "The user prefers written updates.", "2031-05-06")
    placement = place(artifacts, item)
    source = artifacts.get_source(item.provenance[0].source_id)
    if damage == "secondary_source":
        item.provenance.append(ClaimProvenance("absent", ["s1"]))
    elif damage == "segment":
        item.provenance[0].segment_ids.append("absent")
    elif damage == "wrong_source":
        artifacts.save_source(SourceDocument(
            "another", "agent_conversation", "conversation", "2031-05-06", None,
            ["user"], [SourceSegment("elsewhere", 0, "Another statement.")],
        ))
        item.provenance[0].segment_ids.append("elsewhere")
    elif damage == "empty_segments":
        item.provenance[0].segment_ids = []
    else:
        item.provenance = []
    artifacts.save_claim(item)
    return artifacts, item, placement, source


@pytest.mark.parametrize("damage", [
    "secondary_source", "segment", "wrong_source", "empty_segments", "empty_provenance",
])
def test_partial_citations_cannot_be_silently_formatted_as_complete(tmp_path, damage):
    artifacts, item, placement, source = damaged_claim(tmp_path, damage)
    resolver = FactResolver(AsyncMock(), artifacts, Config())
    readers = [
        lambda: cited_source_segments(artifacts, item),
        lambda: resolver._source_times(item),
        lambda: resolver._claims_text({"C1": item}, {item.claim_id: placement}, {}, {}),
        lambda: RoutingFormatter(artifacts).format_evidence(
            {"C1": ClaimEvidence(item, source)}, {},
        ),
    ]
    for read in readers:
        with pytest.raises(ValueError, match=item.claim_id):
            read()


@pytest.mark.asyncio
@pytest.mark.parametrize("incoming", [False, True])
async def test_singleton_projection_reports_corruption_without_model_or_fact(tmp_path, incoming):
    artifacts, item, placement, _ = damaged_claim(tmp_path, "secondary_source")
    llm = AsyncMock()
    result = await FactResolver(llm, artifacts, Config()).resolve(
        [placement], affected_entity_ids={"you"},
        incoming_claim_ids={item.claim_id} if incoming else set(), dream_run_id="test",
    )
    assert result.failures and item.claim_id in result.failures[0].claim_ids
    assert not result.facts and not result.deleted_fact_ids
    assert artifacts.get_claim(item.claim_id).status == "active"
    llm.call_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_truth_checks_singleton_evidence_before_skipping_comparisons(tmp_path):
    artifacts, item, placement, _ = damaged_claim(tmp_path, "segment")
    llm = AsyncMock()
    result = await TruthReviewer(llm, artifacts, Config()).review(
        {item.claim_id}, {item.claim_id: placement}, {}, dream_run_id="test",
    )
    assert result.failure_claim_ids == {item.claim_id}
    assert "missing segments" in result.errors[0]
    llm.call_structured.assert_not_awaited()


def test_resolver_preserves_retracted_source_status_for_explicit_history(tmp_path):
    artifacts = setup_owner(tmp_path)
    item = claim("record", "A retained statement.", "2031-05-06")
    place(artifacts, item)
    source = artifacts.get_source(item.provenance[0].source_id)
    artifacts.save_source(replace(
        source, status="retracted", retracted_at="2031-05-07", retraction_reason="Wrong import.",
    ))
    _, resolved, segments = cited_source_segments(artifacts, item)[0]
    assert resolved.status == "retracted"
    assert [s.segment_id for s in segments] == item.provenance[0].segment_ids


def test_coverage_does_not_credit_a_segment_cited_under_the_wrong_source(tmp_path):
    artifacts, item, _, _ = damaged_claim(tmp_path, "wrong_source")
    report = coverage_report(artifacts)
    assert report["claimed_segments"] == 1 and report["segment_coverage"] == 0.5
    assert report["unresolved_citations"] == [
        {"source_id": item.provenance[0].source_id, "segment_id": "elsewhere"}
    ]


def test_coverage_counts_distinct_source_segment_pairs(tmp_path):
    artifacts = setup_owner(tmp_path)
    item = claim("record", "A supported statement.", "2031-05-06")
    item.provenance = [ClaimProvenance("first", ["same-id"]), ClaimProvenance("second", ["same-id"])]
    place(artifacts, item)
    report = coverage_report(artifacts)
    assert report["segments"] == report["claimed_segments"] == 2
    assert report["segment_coverage"] == 1 and not report["unresolved_citations"]
