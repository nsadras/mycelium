from copy import deepcopy

import pytest

from benchmarks.suites.daily_driver.assessment_inputs import (
    assessment_inputs,
    evidence_key,
)


def source(sid, label, text="Source statement"):
    return {
        "source_id": sid,
        "source_type": "agent_conversation",
        "occurred_at": "2031-05-06",
        "segments": [
            {
                "segment_id": "segment",
                "content": text,
                "speaker": "User",
                "role": "user",
                "metadata": {"fixture_segment_id": label},
            }
        ],
    }


def claim(cid, sid, label):
    return {
        "claim_id": cid,
        "text": "Generated statement",
        "fixture_evidence": [label],
        "status": "active",
        "dream_disposition": "routed",
        "provenance": [{"source_id": sid, "segment_ids": ["segment"]}],
    }


def fixture(references=None):
    return {
        "scenario": {"user": {"speaker_label": "User", "name": "Avery"}},
        "gold_claims": {
            "claims": references
            or [{"id": "gold", "text": "Reference statement", "evidence": ["first"]}]
        },
    }


def test_candidates_are_scoped_by_exact_source_and_segment_pairs():
    snapshot = {
        "sources": [source("s1", "first"), source("s2", "second")],
        "claims": [claim("a", "s1", "first"), claim("b", "s2", "second")],
    }
    result = assessment_inputs(fixture(), snapshot)
    requests = result["requests"]
    assert len(requests) == 2
    first = next(r["payload"] for r in requests if r["payload"]["references"])
    assert first["references"]["gold"]["candidate_claim_ids"] == ["a"]
    assert set(first["source_evidence"]) == {evidence_key("s1", "segment")}
    assert first["source_participants"] == {"User": "Avery"}
    extra = next(r["payload"] for r in requests if not r["payload"]["references"])
    assert set(extra["generated_claims"]) == {"b"}
    assert set(extra["source_evidence"]) == {evidence_key("s2", "segment")}


def test_assessment_identity_tracks_meaning_and_source_changes_not_projection_states():
    snapshot = {
        "sources": [source("s1", "first")],
        "claims": [claim("a", "s1", "first")],
    }
    before = deepcopy(snapshot)
    first = assessment_inputs(fixture(), snapshot)
    snapshot["claims"][0].update(status="superseded", dream_disposition="deferred")
    snapshot["placements"] = [{"claim_id": "a", "owner_entity_id": "different"}]
    assert assessment_inputs(fixture(), snapshot) == first
    changed = deepcopy(before)
    changed["claims"][0]["text"] = "Changed meaning"
    assert (
        assessment_inputs(fixture(), changed)["input_digest"] != first["input_digest"]
    )
    changed = deepcopy(before)
    changed["sources"][0]["segments"][0]["content"] = "Changed source"
    assert (
        assessment_inputs(fixture(), changed)["input_digest"] != first["input_digest"]
    )
    different = fixture()
    different["gold_claims"]["claims"][0]["text"] = "Changed reference"
    assert assessment_inputs(different, before)["input_digest"] != first["input_digest"]


def test_later_unrelated_sources_preserve_per_request_cache_identity():
    snapshot = {
        "sources": [source("s1", "first")],
        "claims": [claim("a", "s1", "first")],
    }
    first = assessment_inputs(fixture(), snapshot)
    snapshot["sources"].append(source("s2", "second"))
    snapshot["claims"].append(claim("b", "s2", "second"))
    second = assessment_inputs(fixture(), snapshot)
    assert first["input_digest"] != second["input_digest"]
    assert first["requests"][0] in second["requests"]


def test_pair_batches_cover_every_candidate_once_without_semantic_pruning():
    refs = [
        {"id": f"g{i}", "text": "Reference", "evidence": ["first"]} for i in range(5)
    ]
    snapshot = {
        "sources": [source("s1", "first")],
        "claims": [claim(f"c{i:02d}", "s1", "first") for i in range(17)],
    }
    result = assessment_inputs(fixture(refs), snapshot)
    pairs = []
    for request in result["requests"]:
        payload = request["payload"]
        batch = [
            (rid, cid)
            for rid, row in payload["references"].items()
            for cid in row["candidate_claim_ids"]
        ]
        assert len(batch) <= 32
        pairs.extend(batch)
    assert len(pairs) == len(set(pairs)) == 85
    assert set(pairs) == {(f"g{i}", f"c{j:02d}") for i in range(5) for j in range(17)}


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "segment",
        "labels",
        "empty",
        "duplicate_claim",
        "duplicate_source",
        "duplicate_label",
    ],
)
def test_missing_or_ambiguous_provenance_is_explicit(mutation):
    snapshot = {
        "sources": [source("s1", "first")],
        "claims": [claim("a", "s1", "first")],
    }
    if mutation == "source":
        snapshot["claims"][0]["provenance"][0]["source_id"] = "missing"
    elif mutation == "segment":
        snapshot["claims"][0]["provenance"][0]["segment_ids"] = ["missing"]
    elif mutation == "labels":
        snapshot["claims"][0]["fixture_evidence"] = ["wrong"]
    elif mutation == "empty":
        snapshot["claims"][0]["provenance"] = []
    elif mutation == "duplicate_claim":
        snapshot["claims"].append(deepcopy(snapshot["claims"][0]))
    elif mutation == "duplicate_source":
        snapshot["sources"].append(deepcopy(snapshot["sources"][0]))
    else:
        snapshot["sources"].append(source("s2", "first"))
    with pytest.raises(ValueError):
        assessment_inputs(fixture(), snapshot)


def test_capture_before_build_needs_no_semantic_match_and_later_evidence_is_explicit():
    snapshot = {"sources": [source("s1", "first")], "claims": []}
    result = assessment_inputs(fixture(), snapshot)
    assert result["requests"] == []
    assert result["unmatched_reference_ids"] == ["gold"]
    snapshot["claims"] = [claim("a", "s1", "first")]
    targets = fixture(
        [{"id": "gold", "text": "Reference", "evidence": ["first", "later"]}]
    )
    payload = assessment_inputs(targets, snapshot)["requests"][0]["payload"]
    assert payload["references"]["gold"]["evidence_ids"] == [
        evidence_key("s1", "segment")
    ]
    assert payload["references"]["gold"]["unavailable_evidence_ids"] == ["later"]


def test_split_source_turn_retains_all_native_segments_under_one_fixture_label():
    first = source("s1", "first")
    first["segments"].append(
        {
            **first["segments"][0],
            "segment_id": "second-part",
            "content": "Another part of the same turn.",
        }
    )
    second_claim = claim("b", "s1", "first")
    second_claim["provenance"][0]["segment_ids"] = ["second-part"]
    snapshot = {"sources": [first], "claims": [claim("a", "s1", "first"), second_claim]}
    inputs = assessment_inputs(fixture(), snapshot)
    payload = inputs["requests"][0]["payload"]
    assert payload["references"]["gold"]["candidate_claim_ids"] == ["a", "b"]
    assert set(payload["source_evidence"]) == {
        evidence_key("s1", "segment"),
        evidence_key("s1", "second-part"),
    }
    assert payload["generated_claims"]["b"]["evidence_ids"] == [
        evidence_key("s1", "second-part")
    ]
