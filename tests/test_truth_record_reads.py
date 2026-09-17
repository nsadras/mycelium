from collections import Counter
from types import SimpleNamespace

import pytest

from mycelium.artifacts import (
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.truth_review import TruthReviewer


def setup(count=1000):
    source = SourceDocument(
        "shared",
        "meeting_transcript",
        "session",
        "2031-05-03",
        "2031-05-02",
        ["Rae"],
        [
            SourceSegment(
                f"s{i}",
                i,
                f"Statement {i}.",
                "Rae",
                "participant",
                timestamp="2031-05-02",
            )
            for i in range(count)
        ],
    )
    claims = {
        f"c{i}": MemoryClaim(
            f"c{i}",
            f"Statement {i}.",
            [],
            [ClaimProvenance("shared", [f"s{i}"])],
            "2031-05-03",
        )
        for i in range(count)
    }
    reads = Counter()

    def get_source(sid):
        reads[sid] += 1
        assert sid == "shared"
        return source

    artifacts = SimpleNamespace(
        get_source=get_source, list_entity_references=lambda **_: []
    )
    return TruthReviewer(None, artifacts), claims, source, reads


def test_truth_preparation_reads_shared_source_and_builds_segment_index_once():
    reviewer, claims, _, reads = setup()
    records = reviewer._records(claims, {}, {})
    assert len(records) == len(claims)
    assert reads == {"shared": 1}
    for i in range(len(claims)):
        assert records[f"c{i}"]["citations"] == [
            {
                "source_id": "shared",
                "segment_id": f"s{i}",
                "source_time": "2031-05-02",
                "message_time": "2031-05-02",
                "speaker": "Rae",
                "text": f"Statement {i}.",
            }
        ]


@pytest.mark.parametrize(
    "mutation", ["text", "retraction", "missing_segment", "missing_source"]
)
def test_next_truth_preparation_observes_source_changes(mutation):
    reviewer, claims, source, reads = setup(2)
    prior = reviewer._records(claims, {}, {})
    if mutation == "text":
        source.segments[0].content = "Corrected source."
        current = reviewer._records(claims, {}, {})
        assert current["c0"]["citations"][0]["text"] == "Corrected source."
        assert prior["c0"]["citations"][0]["text"] == "Statement 0."
        assert reads == {"shared": 2}
    else:
        if mutation == "retraction":
            source.status = "retracted"
        elif mutation == "missing_segment":
            source.segments.clear()
        else:

            def missing(_):
                raise FileNotFoundError("Source removed")

            reviewer.artifacts.get_source = missing
        with pytest.raises(ValueError, match="Claim c0 cites"):
            reviewer._records(claims, {}, {})
