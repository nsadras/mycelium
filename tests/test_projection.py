from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from mycelium.artifacts import ArtifactStore, ClaimProvenance, MemoryClaim, SourceDocument
from mycelium.config import Config
from mycelium.dream import DreamProcess
from mycelium.models import WikiPage
from mycelium.projection import (
    claim_date_key,
    compact_display_claims,
    compact_qualifiers,
    display_claim_text,
    partition_claims,
    project_claim,
)
from mycelium.store import WikiStore


def claim(claim_id: str, text: str, kind: str, *, salience: float = 0.5, facets=None):
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        kind=kind,
        about=[{"entity": "Ava"}],
        provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
        recorded_at="2024-01-10T12:00:00",
        salience=salience,
        facets=facets or {"observed_at": "4:24 pm on 10 January, 2024"},
    )


def test_projection_separates_durable_timeline_and_social_claims():
    claims = [
        claim("preference", "Ava prefers oolong tea.", "preference", salience=0.9),
        claim("event", "Ava visited Kyoto.", "event", salience=0.7),
        claim("greeting", "Ava greeted Ben.", "interaction", salience=0.8),
        claim("detail", "Ava described the room as blue.", "description", salience=0.3),
    ]
    projected = partition_claims(claims)

    assert [item.claim.claim_id for item in projected["main"]] == ["preference"]
    assert [item.claim.claim_id for item in projected["timeline"]] == ["event"]
    assert [item.claim.claim_id for item in projected["interaction_archive"]] == ["greeting"]
    assert [item.claim.claim_id for item in projected["details"]] == ["detail"]


def test_projection_routes_textual_speech_acts_to_interactions():
    item = claim("question", "Ava asked Ben about his pets.", "fact")

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["interaction_archive"]] == [
        "question"
    ]


def test_projection_shards_have_stable_bounded_names():
    dream = DreamProcess(MagicMock(), MagicMock(), MagicMock(), Config.defaults())
    parent = WikiPage(
        slug="person-ava", title="Ava", content="Overview",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.8,
    )
    items = [
        project_claim(claim(f"event-{index}", f"Ava attended community event {index} with several friends.", "event"))
        for index in range(12)
    ]

    shards = dream._projection_shards(parent, "timeline", "Timeline", items, max_chars=360)

    assert len(shards) > 1
    assert shards[0][0] == "person-ava-timeline"
    assert shards[1][0] == "person-ava-timeline-2"
    assert all(content.startswith("# Ava: Timeline") for _, _, content, _ in shards)
    assert "[[person-ava-timeline-2]]" in shards[0][2]


def test_projection_shards_cap_record_count():
    dream = DreamProcess(MagicMock(), MagicMock(), MagicMock(), Config.defaults())
    parent = WikiPage(
        slug="person-ava", title="Ava", content="Overview",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.8,
    )
    items = [
        project_claim(claim(f"detail-{index}", f"Ava recorded distinct detail {index}.", "fact"))
        for index in range(5)
    ]

    shards = dream._projection_shards(
        parent, "details", "Detailed Facts", items,
        max_chars=10000, max_records=2,
    )

    assert [len(included) for _, _, _, included in shards] == [2, 2, 1]


def test_projection_labels_observation_dates_without_calling_them_event_dates():
    item = claim("event", "Ava launched a project.", "event")

    assert claim_date_key(item) == "Observed 2024-01-10"


def test_projection_uses_normalized_relative_date_without_conflicting_calendar_date():
    item = claim(
        "event",
        "Ava left yesterday, January 10, 2024.",
        "event",
        facets={
            "when": "yesterday",
            "normalized_date": "2024-01-09",
            "observed_at": "2024-01-10T12:00:00",
        },
    )

    assert display_claim_text(item) == "Ava left yesterday."
    assert claim_date_key(item) == "2024-01-09"


def test_projection_removes_standalone_calendar_date_that_conflicts_with_normalized_date():
    item = claim(
        "event",
        "Ava left her job on 10 January, 2024.",
        "event",
        facets={
            "when": "yesterday",
            "normalized_date": "2024-01-09",
            "observed_at": "2024-01-10T12:00:00",
        },
    )

    assert display_claim_text(item) == "Ava left her job."


def test_display_compaction_recognizes_safe_lexical_equivalents():
    first = claim("first", "Ava started an online clothing store.", "biographical_fact")
    second = claim("second", "Ava opened an online clothes shop.", "biographical_fact")

    compacted = compact_display_claims([project_claim(first), project_claim(second)])

    assert len(compacted) == 1
    assert set(compacted[0].claim_ids) == {"first", "second"}


def test_main_projection_caps_a_single_repetitive_bucket():
    claims = [
        claim(
            f"goal-{index}",
            f"Ava plans distinct project milestone {index}.",
            "plan",
            salience=0.9,
        )
        for index in range(20)
    ]

    projected = partition_claims(claims, main_claim_limit=12)

    assert len(projected["main"]) <= 4
    assert len(projected["main"]) + len(projected["details"]) == 20


def test_display_compaction_preserves_member_claim_ids():
    first = claim("first", "Ava stated that she will not quit.", "commitment")
    second = claim("second", "Ava confirmed that she will not quit.", "commitment")

    compacted = compact_display_claims([project_claim(first), project_claim(second)])

    assert len(compacted) == 1
    assert set(compacted[0].claim_ids) == {"first", "second"}


def test_compact_qualifiers_hide_provenance_and_redundant_values():
    item = claim(
        "preference",
        "Ava prefers tea because it is calming.",
        "preference",
        facets={
            "observed_at": "2024-01-10T12:00:00",
            "reason": "because it is calming",
            "location": "tea house",
        },
    )

    qualifiers = compact_qualifiers(item, include_date=True)

    assert all("observed" not in value for value in qualifiers)
    assert all("reason" not in value for value in qualifiers)
    assert "location: tea house" in qualifiers


@pytest.mark.asyncio
async def test_claim_compaction_rebuilds_parent_and_derived_views(tmp_path):
    config = Config.defaults()
    config.dream.evidence_mode = "claims"
    wiki = WikiStore(tmp_path / "wiki")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    parent = WikiPage(
        slug="person-ava", title="Ava", content="Old verbose memory ledger",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.8,
    )
    wiki.save(parent)
    artifacts.save_source(SourceDocument(
        source_id="source-1",
        source_type="meeting_transcript",
        session_id="session-1",
        recorded_at="2024-01-10T12:00:00",
        occurred_at="2024-01-10T12:00:00",
        participants=["Ava", "Ben"],
        segments=[],
        raw_log_entry_id="source-log-1",
    ))
    for item in (
        claim("preference", "Ava prefers oolong tea.", "preference", salience=0.9),
        claim("event", "Ava visited Kyoto.", "event", salience=0.7),
        claim("greeting", "Ava greeted Ben.", "interaction", salience=0.2),
    ):
        item.page_slugs = ["person-ava"]
        item.provenance[0].raw_log_entry_id = "source-log-1"
        artifacts.save_claim(item)

    llm = AsyncMock()
    llm.call_structured.return_value = {
        "title": "Ava",
        "content": "Ava is remembered for durable preferences and experiences.",
        "confidence": 0.9,
        "importance": 0.8,
        "tags": ["person"],
    }
    logs = MagicMock()
    dream = DreamProcess(llm, wiki, logs, config, artifacts)

    report = await dream.compact()

    rebuilt = wiki.get("person-ava")
    assert report.pages_updated == 1
    assert report.pages_created == 2
    assert "Old verbose memory ledger" not in rebuilt.content
    assert "## Memory" in rebuilt.content
    assert "[[person-ava-timeline]]" in rebuilt.content
    assert "[[person-ava-interactions]]" in rebuilt.content
    assert "Ava visited Kyoto." in wiki.get("person-ava-timeline").content
    assert "Ava greeted Ben." in wiki.get("person-ava-interactions").content
    logs.get_many.assert_not_called()
