from collections import Counter
from types import SimpleNamespace

import pytest

from mycelium.identity_candidates import identity_records


def setup(count=20):
    source = SimpleNamespace(
        status="active", segments=[SimpleNamespace(segment_id="s1")]
    )
    claims = {
        cid: SimpleNamespace(
            status="active",
            text=f"Statement {cid}",
            provenance=[SimpleNamespace(source_id="source", segment_ids=["s1"])],
        )
        for cid in ("c1", "c2")
    }
    entities = [
        SimpleNamespace(
            entity_id=f"e{i}",
            status="active",
            entity_type="project",
            title=f"Project {i}",
            aliases=[],
            materialization_state="materialized",
        )
        for i in range(count)
    ]
    decisions = [
        SimpleNamespace(
            decision_id=f"{e.entity_id}-d{i}",
            entity_id=e.entity_id,
            review_state="accepted",
            created_at=f"2031-01-0{i + 1}",
            identity_evidence_claim_ids=list(claims),
            reviewer_note=f"Review {i}",
            candidate_entity_ids=[],
        )
        for e in entities
        for i in range(4)
    ]
    reads = Counter()

    def get_claim(cid):
        reads[("claim", cid)] += 1
        return claims[cid]

    def get_source(sid):
        reads[("source", sid)] += 1
        assert sid == "source"
        return source

    artifacts = SimpleNamespace(
        list_entity_resolution_decisions=lambda: decisions,
        get_claim=get_claim,
        get_source=get_source,
    )
    return artifacts, entities, claims, source, reads


def test_shared_identity_evidence_is_loaded_once_per_preparation():
    artifacts, entities, _, _, reads = setup(count=100)
    result = identity_records(artifacts, entities)
    assert reads == {("claim", "c1"): 1, ("claim", "c2"): 1, ("source", "source"): 1}
    assert len(result) == 100
    for entity in entities:
        row = result[entity.entity_id]
        assert row["reviewer_notes"] == ["Review 0", "Review 1", "Review 2", "Review 3"]
        assert row["identity_evidence"] == [
            {
                "claim_id": cid,
                "text": f"Statement {cid}",
                "citations": [{"source_id": "source", "segment_ids": ["s1"]}],
            }
            for cid in ("c1", "c2")
        ]


def test_new_preparation_observes_claim_edits_supersession_and_source_retraction():
    artifacts, entities, claims, source, reads = setup()
    before = identity_records(artifacts, entities)
    claims["c1"].text = "Revised canonical statement"
    claims["c2"].status = "superseded"
    revised = identity_records(artifacts, entities)
    for eid in revised:
        assert len(revised[eid]["identity_evidence"]) == 1
        assert (
            revised[eid]["identity_evidence"][0]["text"]
            == "Revised canonical statement"
        )
        assert before[eid]["identity_evidence"][0]["text"] == "Statement c1"
    source.status = "retracted"
    assert all(
        not r["identity_evidence"]
        for r in identity_records(artifacts, entities).values()
    )
    assert reads[("source", "source")] == 3


@pytest.mark.parametrize(
    "broken", ["segments", "empty_provenance", "empty_segments", "missing"]
)
def test_reuse_preserves_exact_provenance_failures(broken):
    artifacts, entities, claims, source, _ = setup()
    identity_records(artifacts, entities)
    expected = ValueError
    if broken == "segments":
        source.segments = []
    elif broken == "empty_provenance":
        claims["c1"].provenance = []
    elif broken == "empty_segments":
        claims["c1"].provenance[0].segment_ids = []
    else:

        def missing(_):
            raise FileNotFoundError("Source disappeared")

        artifacts.get_source = missing
        expected = FileNotFoundError
    with pytest.raises(expected):
        identity_records(artifacts, entities)
