from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.config import Config
from mycelium.dream import DreamProcess, EvidenceChunk
from mycelium.models import WikiPage
from mycelium.projection import (
    claim_date_key,
    compact_display_claims,
    compact_qualifiers,
    compact_record_qualifiers,
    display_claim_text,
    partition_claims,
    project_claim,
)
from mycelium.store import WikiStore


def claim(
    claim_id: str,
    text: str,
    kind: str,
    *,
    salience: float = 0.5,
    facets=None,
    claim_type: str | None = None,
    evidence_modality: str = "unknown",
    temporal_status: str = "unknown",
    predicate: str | None = None,
    derivation_operation: str | None = None,
):
    normalized_kind = kind.replace("_", " ").lower()
    semantic_type = claim_type or {
        "preference": "preference",
        "event": "event",
        "interaction": "interaction",
        "description": "observation",
        "biographical fact": "identity",
        "plan": "plan",
        "commitment": "commitment",
    }.get(normalized_kind, "observation")
    return MemoryClaim(
        claim_id=claim_id,
        text=text,
        kind=kind,
        about=[{"entity": "Ava"}],
        provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
        recorded_at="2024-01-10T12:00:00",
        salience=salience,
        facets=facets or {"observed_at": "4:24 pm on 10 January, 2024"},
        claim_type=semantic_type,
        evidence_modality=evidence_modality,
        temporal_status=temporal_status,
        predicate=predicate,
        derivation_operation=derivation_operation,
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


def test_projection_keeps_traceable_inferences_in_separate_insights_scope():
    item = claim(
        "derived-duration",
        "Ava completed the project in four months.",
        "derived duration",
        facets={
            "basis_claim_ids": ["started", "finished"],
            "inference_basis": "The recorded start and finish dates are four months apart.",
        },
        claim_type="event",
        derivation_operation="temporal_arithmetic",
    )
    item.inferred = True

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["insights"]] == [
        "derived-duration"
    ]
    assert "based on 2 facts" in compact_qualifiers(item)


def test_projection_reports_repeated_support_as_sessions_not_event_count():
    item = claim("preference", "Ava prefers tea.", "preference")
    item.provenance.append(ClaimProvenance("source-2", ["source-2#seg-0001"]))

    projected = partition_claims([item])
    qualifiers = compact_record_qualifiers(projected["main"][0])

    assert "recorded in 2 sessions" in qualifiers
    assert all("times" not in qualifier for qualifier in qualifiers)


def test_projection_routes_interaction_from_semantics_not_wording():
    item = claim(
        "question", "Ava and Ben discussed his pets.", "fact",
        claim_type="interaction", predicate="discussed_with",
    )

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["interaction_archive"]] == [
        "question"
    ]


def test_projection_routes_visual_evidence_to_details_despite_kind_and_wording():
    item = claim(
        "photo", "Ava's newly arranged desk has a blue surface.", "fact",
        claim_type="state", evidence_modality="visual", predicate="has_surface_color",
    )

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["details"]] == ["photo"]
    assert not projected["main"]


def test_projection_routes_conversational_departure_by_claim_type():
    item = claim(
        "departure", "Ava ended the conversation.", "plan",
        claim_type="interaction", predicate="ended_conversation", temporal_status="past",
    )

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["interaction_archive"]] == [
        "departure"
    ]
    assert not projected["main"]


def test_projection_routes_dated_event_to_timeline_despite_main_kind():
    item = claim(
        "purchase",
        "Ava bought a book three days ago.",
        "plan",
        facets={"normalized_date": "2024-01-07", "date_precision": "day"},
        claim_type="event", predicate="purchased", temporal_status="past",
    )

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["timeline"]] == ["purchase"]
    assert not projected["main"]


def test_projection_routes_undated_event_from_semantics_not_past_tense():
    item = claim(
        "purchase", "A book purchase by Ava occurred.", "action item",
        claim_type="event", predicate="purchased", temporal_status="past",
    )

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["timeline"]] == ["purchase"]
    assert not projected["main"]


def test_projection_does_not_treat_a_photo_word_as_visual_evidence():
    item = claim(
        "photo", "Ava stores family photos in the attic.", "biographical fact",
        claim_type="state", evidence_modality="speech", predicate="stores",
    )

    projected = partition_claims([item])

    assert [value.claim.claim_id for value in projected["main"]] == ["photo"]
    assert not projected["details"]


def test_projection_is_invariant_to_event_paraphrasing():
    items = [
        claim(
            "plain", "Ava bought a book.", "custom subtype",
            claim_type="event", predicate="purchased", temporal_status="past",
        ),
        claim(
            "nominal", "A book purchase by Ava occurred.", "another subtype",
            claim_type="event", predicate="purchased", temporal_status="past",
        ),
    ]

    assert [project_claim(item).scope for item in items] == ["timeline", "timeline"]


def test_derived_basis_validation_uses_semantics_not_conclusion_phrases():
    dated_events = []
    for index, text in enumerate((
        "Ava attended once.",
        "An attendance by Ava occurred.",
        "Ava was present at another gathering.",
    ), start=1):
        item = claim(
            f"event-{index}", text, "arbitrary",
            claim_type="event", predicate="attended", temporal_status="past",
            facets={"normalized_date": f"2024-01-0{index}"},
        )
        item.provenance = [ClaimProvenance(
            f"source-{index}", [f"source-{index}#seg-0001"]
        )]
        dated_events.append(item)

    assert DreamProcess._valid_derivation_basis("event_count", dated_events[:2])
    assert DreamProcess._valid_derivation_basis("recurring_pattern", dated_events)

    mention = claim(
        "mention", "Ava mentioned three events.", "event",
        claim_type="observation", predicate="mentioned", temporal_status="past",
        facets={"normalized_date": "2024-01-04"},
    )
    assert not DreamProcess._valid_derivation_basis(
        "event_count", [dated_events[0], mention]
    )


def test_cross_fact_derivation_requires_multiple_structured_relations():
    employer = claim(
        "employer", "Ava works at Acme.", "fact",
        claim_type="state", predicate="works_at", temporal_status="current",
    )
    role = claim(
        "role", "Ava is Acme's designer.", "fact",
        claim_type="identity", predicate="has_role", temporal_status="current",
    )
    duplicate_relation = claim(
        "employer-2", "Acme employs Ava.", "fact",
        claim_type="state", predicate="works_at", temporal_status="current",
    )

    assert DreamProcess._valid_derivation_basis(
        "cross_fact_relationship", [employer, role]
    )
    assert not DreamProcess._valid_derivation_basis(
        "cross_fact_relationship", [employer, duplicate_relation]
    )


def test_projection_demotes_visual_records_from_main_page():
    item = claim(
        "photo", "Ava shared a photo showing a blue room.", "image description",
        salience=1.0, claim_type="observation", evidence_modality="visual",
    )
    item.confidence = 1.0

    projected = partition_claims([item])

    assert projected["main"] == []
    assert [value.claim.claim_id for value in projected["details"]] == ["photo"]


def test_multi_party_routing_uses_real_about_entities_not_synthetic_speakers(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.save_source(SourceDocument(
        source_id="source-1", source_type="multi_party_conversation",
        session_id="session-1", recorded_at="2024-01-10T12:00:00",
        occurred_at="2024-01-10T12:00:00", participants=["John", "Tim"],
        segments=[
            SourceSegment("source-1#seg-0001", 0, "Good to meet.", speaker="John"),
            SourceSegment("source-1#seg-0002", 1, "Likewise.", speaker="Tim"),
        ],
    ))
    relationship = MemoryClaim(
        claim_id="relationship", text="John met Tim.", kind="interaction",
        about=[{"entity": "John"}, {"entity": "Tim"}],
        provenance=[ClaimProvenance(
            "source-1", ["source-1#seg-0001", "source-1#seg-0002"],
            speaker="John/Tim",
        )],
        recorded_at="2024-01-10T12:00:00",
    )
    artifacts.save_claim(relationship)
    wiki = MagicMock()
    wiki.exists.return_value = False
    dream = DreamProcess(MagicMock(), wiki, MagicMock(), Config.defaults(), artifacts)
    evidence = [EvidenceChunk(
        evidence_id="relationship::claim", entry_id="entry-1", session_id="session-1",
        timestamp=datetime.now(), content="John met Tim.", importance=0.8,
        durability="durable", chunk_index=1, chunk_count=1,
        claim_ids=("relationship",), source_id="source-1",
    )]

    targets = dream._identify_participant_claim_targets(evidence)

    assert {target["page"] for target in targets} == {"person-john", "person-tim"}


def test_projection_shards_have_stable_bounded_names(tmp_path):
    dream = DreamProcess(
        MagicMock(), MagicMock(), MagicMock(), Config.defaults(),
        ArtifactStore(tmp_path / "artifacts"),
    )
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


def test_projection_shards_cap_record_count(tmp_path):
    dream = DreamProcess(
        MagicMock(), MagicMock(), MagicMock(), Config.defaults(),
        ArtifactStore(tmp_path / "artifacts"),
    )
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


def test_display_compaction_does_not_conflate_handwritten_synonyms():
    first = claim("first", "Ava started an online clothing store.", "biographical_fact")
    second = claim("second", "Ava opened an online clothes shop.", "biographical_fact")

    compacted = compact_display_claims([project_claim(first), project_claim(second)])

    assert len(compacted) == 2


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


@pytest.mark.asyncio
async def test_claim_compaction_persists_grounded_derived_insights(tmp_path):
    config = Config.defaults()
    config.dream.evidence_mode = "claims"
    wiki = WikiStore(tmp_path / "wiki")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki.save(WikiPage(
        slug="person-ava", title="Ava", content="Old memory",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.8,
    ))
    artifacts.save_source(SourceDocument(
        source_id="source-1", source_type="meeting_transcript",
        session_id="session-1", recorded_at="2024-05-01T12:00:00",
        occurred_at="2024-05-01T12:00:00", participants=["Ava"],
        segments=[], raw_log_entry_id="source-log-1",
    ))
    started = claim(
        "claim-started", "Ava started the project in January.", "event",
        facets={"normalized_date": "2024-01-01", "date_precision": "month"},
    )
    finished = claim(
        "claim-finished", "Ava finished the project in May.", "event",
        facets={"normalized_date": "2024-05-01", "date_precision": "month"},
    )
    for item in (started, finished):
        item.page_slugs = ["person-ava"]
        artifacts.save_claim(item)

    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"claims": [{
            "text": "Ava completed the project in four months.",
            "kind": "derived duration",
            "predicate": "completed_in_duration",
            "temporal_status": "past",
            "derivation_operation": "temporal_arithmetic",
            "inference_basis": (
                "claim-started and claim-finished place the endpoints four months apart."
            ),
            "confidence": 0.9,
            "facets": {"duration": "four months"},
        }]},
        {
            "title": "Ava", "content": "A compact overview.",
            "confidence": 0.9, "importance": 0.8, "tags": ["person"],
        },
    ]
    dream = DreamProcess(llm, wiki, MagicMock(), config, artifacts)

    await dream.compact()

    inferred = [item for item in artifacts.list_claims() if item.inferred]
    assert len(inferred) == 1
    assert inferred[0].confidence == 0.7
    assert inferred[0].derivation_operation == "temporal_arithmetic"
    assert inferred[0].evidence_modality == "inference"
    assert inferred[0].facets["basis_claim_ids"] == [
        "claim-started", "claim-finished"
    ]
    assert all(provenance.evidence_type == "inferred" for provenance in inferred[0].provenance)
    insights = wiki.get("person-ava-insights").content
    assert "Ava completed the project in four months." in insights
    assert "based on 2 facts" in insights


@pytest.mark.asyncio
async def test_claim_compaction_rejects_mention_counts_and_unsupported_trends(tmp_path):
    config = Config.defaults()
    config.dream.evidence_mode = "claims"
    wiki = WikiStore(tmp_path / "wiki")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki.save(WikiPage(
        slug="person-ava", title="Ava", content="Old memory",
        created=datetime.now(), last_updated=datetime.now(),
        version=1, confidence=0.8, importance=0.8,
    ))
    artifacts.save_source(SourceDocument(
        source_id="source-1", source_type="meeting_transcript",
        session_id="session-1", recorded_at="2024-05-01T12:00:00",
        occurred_at="2024-05-01T12:00:00", participants=["Ava"],
        segments=[], raw_log_entry_id="source-log-1",
    ))
    first = claim("claim-first", "Ava shared a photo of a tattoo.", "visual detail")
    second = claim("claim-second", "Ava discussed a tattoo design.", "fact")
    for item in (first, second):
        item.page_slugs = ["person-ava"]
        artifacts.save_claim(item)

    llm = AsyncMock()
    llm.call_structured.side_effect = [
        {"claims": [
            {
                "text": "Ava got tattoos on at least two distinct dates.",
                "kind": "derived count",
                "derivation_operation": "event_count",
                "basis_claim_ids": ["claim-first", "claim-second"],
                "about": [{"entity": "Ava"}],
                "inference_basis": "Two claims refer to tattoos.",
                "confidence": 0.6,
            },
            {
                "text": "Ava has shown increasing interest in tattoos.",
                "kind": "derived pattern",
                "derivation_operation": "recurring_pattern",
                "basis_claim_ids": ["claim-first", "claim-second"],
                "about": [{"entity": "Ava"}],
                "inference_basis": "Two claims refer to tattoos.",
                "confidence": 0.6,
            },
        ]},
        {
            "title": "Ava", "content": "A compact overview.",
            "confidence": 0.9, "importance": 0.8, "tags": ["person"],
        },
    ]
    dream = DreamProcess(llm, wiki, MagicMock(), config, artifacts)

    await dream.compact()

    assert not [item for item in artifacts.list_claims() if item.inferred]
    with pytest.raises(FileNotFoundError):
        wiki.get("person-ava-insights")
