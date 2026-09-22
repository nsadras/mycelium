
from dataclasses import replace

import pytest

from mycelium.artifact_integrity import cited_source_segments, coverage_report
from mycelium.artifacts import ClaimProvenance, SourceDocument, SourceSegment
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
    from mycelium.memory_inputs import serialize_claim_context
    for read in [lambda: cited_source_segments(artifacts, item), lambda: serialize_claim_context(artifacts, item)]:
        with pytest.raises(ValueError, match=item.claim_id):
            read()


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
