from datetime import datetime

import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock

from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    MemoryClaim,
    ReconsolidationProposal,
    SourceDocument,
    SourceSegment,
    normalize_temporal_facets,
    query_temporal_record,
    temporal_intervals_overlap,
)
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.store import LogStore
from mycelium.structured_outputs import extraction_output_model


def test_extraction_schema_requires_batch_constrained_claim_evidence():
    first = "source-test#seg-0001"
    second = "source-test#seg-0002"
    output_model = extraction_output_model({first, second})
    valid = {
        "claims": [{"text": "Ava prefers tea.", "segment_ids": [first]}],
        "ignored_segment_ids": [second],
    }

    assert output_model.model_validate(valid).claims[0].segment_ids == [first]
    for invalid in (
        {"claims": [{"text": "Ava prefers tea."}], "ignored_segment_ids": []},
        {"claims": [{"text": "Ava prefers tea.", "segment_ids": []}], "ignored_segment_ids": []},
        {
            "claims": [{"text": "Ava prefers tea.", "segment_ids": ["source-other#seg-1"]}],
            "ignored_segment_ids": [],
        },
        {"claims": []},
    ):
        with pytest.raises(ValidationError):
            output_model.model_validate(invalid)


@pytest.mark.asyncio
async def test_encoder_persists_source_episode_and_atomic_claims(tmp_path):
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "claims": [
            {
                "text": "Ava prefers tea.", "kind": "preference",
                "claim_type": "preference", "predicate": "prefers",
                "evidence_modality": "speech", "temporal_status": "atemporal",
                "about": [{"entity": "Ava", "role": "person"}],
                "segment_ids": ["source-fixed-later"],
                "confidence": 0.9, "facets": {"object": "tea"},
            }
        ],
        "ignored_segment_ids": [],
    }
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    # Make the mock use the generated segment id returned in the extraction prompt.
    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        value = dict(llm.call_structured.return_value)
        value["claims"] = [dict(value["claims"][0], segment_ids=[segment_id])]
        return value
    llm.call_structured.side_effect = response

    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: I prefer tea.", "session-1",
        source_type="multi_party_conversation", occurred_at="2024-01-10",
    )

    source = artifacts.list_sources()[0]
    episode = artifacts.list_episodes()[0]
    claim = artifacts.list_claims()[0]
    assert source.segments[0].content == "I prefer tea."
    assert episode.extraction_status == "complete"
    assert claim.provenance[0].segment_ids == [source.segments[0].segment_id]
    assert claim.claim_type == "preference"
    assert claim.predicate == "prefers"
    assert claim.evidence_modality == "speech"
    assert claim.temporal_status == "atemporal"
    assert artifacts.coverage_report()["segment_coverage"] == 1.0


@pytest.mark.asyncio
async def test_encoder_preserves_repeated_claims_as_separate_source_events(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return {
            "claims": [{
                "text": "Ava prefers tea.",
                "claim_type": "preference",
                "predicate": "prefers",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_id],
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    for session_id in ("session-1", "session-2"):
        await encoder.encode_session(
            "Ava: I prefer tea.",
            session_id,
            source_type="multi_party_conversation",
            occurred_at="2024-01-10",
        )

    claims = artifacts.list_claims()
    assert len(claims) == 2
    assert len({claim.claim_id for claim in claims}) == 2
    assert len({claim.provenance[0].source_id for claim in claims}) == 2
    assert {claim.text for claim in claims} == {"Ava prefers tea."}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_type", "transcript", "text", "claim_type", "predicate", "temporal_status"),
    [
        (
            "agent_conversation", "USER: Please avoid meetings before 10am.",
            "Nitin prefers meetings at or after 10am.", "preference", "prefers_meeting_time",
            "recurring",
        ),
        (
            "meeting_transcript", "[M1] (2024-01-10) Ava: I will send the report Friday.",
            "Ava committed to sending the report Friday.", "commitment", "send_report",
            "future",
        ),
    ],
)
async def test_encoder_persists_general_semantics_across_source_types(
    tmp_path, source_type, transcript, text, claim_type, predicate, temporal_status
):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_id = next(
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if part.startswith("source-")
        )
        return {
            "claims": [{
                "text": text,
                "kind": "open subtype",
                "claim_type": claim_type,
                "predicate": predicate,
                "evidence_modality": "speech",
                "temporal_status": temporal_status,
                "about": [{"entity": text.split()[0]}],
                "segment_ids": [segment_id],
                "confidence": 0.9,
                "facets": {},
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        transcript, "session-1", source_type=source_type, occurred_at="2024-01-10"
    )

    stored = artifacts.list_claims()[0]
    assert stored.claim_type == claim_type
    assert stored.predicate == predicate
    assert stored.evidence_modality == "speech"
    assert stored.temporal_status == temporal_status


@pytest.mark.asyncio
async def test_meeting_encoder_anchors_deadline_to_meeting_time(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_id = next(
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if part.startswith("source-")
        )
        return {
            "claims": [{
                "text": "Ava committed to sending the report by Friday.",
                "claim_type": "commitment",
                "temporal_status": "future",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_id],
                "facets": {"deadline": "Friday"},
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[M1] Ava: I will send the report by Friday.",
        "meeting-1",
        source_type="meeting_transcript",
        occurred_at="2024-01-10T14:00:00-08:00",
    )

    temporal = artifacts.list_claims()[0].facets["temporal"]
    assert temporal["anchor"] == "2024-01-10T14:00:00-08:00"
    assert temporal["role"] == "deadline"
    assert temporal["start"] == "2024-01-12"


@pytest.mark.asyncio
async def test_chat_claim_uses_its_cited_message_as_temporal_anchor(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_ids = [
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if part.startswith("source-")
        ]
        return {
            "claims": [{
                "text": "Ava will finish the report tomorrow.",
                "claim_type": "commitment",
                "temporal_status": "future",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_ids[1]],
                "temporal_anchor_segment_id": segment_ids[1],
                "facets": {"deadline": "tomorrow"},
            }],
            "ignored_segment_ids": [segment_ids[0]],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "A multi-day chat",
        "chat-1-ep-1",
        source_type="agent_conversation",
        occurred_at="2026-08-26T23:00:00+00:00",
        segments=[
            SourceSegment(
                "", 0, "Earlier context.", speaker="user", role="user",
                timestamp="2026-08-26T23:00:00+00:00",
            ),
            SourceSegment(
                "", 1, "I will finish the report tomorrow.",
                speaker="Ava", role="user",
                timestamp="2026-08-27T08:00:00+00:00",
            ),
        ],
    )

    temporal = artifacts.list_claims()[0].facets["temporal"]
    assert temporal["anchor"] == "2026-08-27T08:00:00+00:00"
    assert temporal["start"] == "2026-08-28"


@pytest.mark.asyncio
async def test_chat_relative_time_stays_unresolved_with_wrong_anchor_segment(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_ids = [
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if part.startswith("source-")
        ]
        return {
            "claims": [{
                "text": "Ava will finish the report tomorrow.",
                "claim_type": "commitment",
                "temporal_status": "future",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_ids[1]],
                "temporal_anchor_segment_id": segment_ids[0],
                "facets": {"deadline": "tomorrow"},
            }],
            "ignored_segment_ids": [segment_ids[0]],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "A multi-day chat",
        "chat-1-ep-1",
        source_type="agent_conversation",
        occurred_at="2026-08-26T23:00:00+00:00",
        segments=[
            SourceSegment(
                "", 0, "Earlier context.", speaker="user", role="user",
                timestamp="2026-08-26T23:00:00+00:00",
            ),
            SourceSegment(
                "", 1, "I will finish the report tomorrow.",
                speaker="Ava", role="user",
                timestamp="2026-08-27T08:00:00+00:00",
            ),
        ],
    )

    temporal = artifacts.list_claims()[0].facets["temporal"]
    assert temporal["status"] == "unresolved"
    assert temporal["anchor"] is None


@pytest.mark.asyncio
async def test_encoder_fills_missing_about_and_requires_inference_basis(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_ids = [
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if not part.startswith(("TARGET ", "CONTEXT "))
        ]
        return {
            "claims": [{
                "text": "Ava enjoys teaching dance.",
                "kind": "preference",
                "about": [],
                "segment_ids": segment_ids,
                "evidence_type": "inferred",
                "confidence": 0.9,
                "facets": {},
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: Teaching dance is something I enjoy.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )

    stored = artifacts.list_claims()[0]
    assert stored.about == [{"entity": "Ava", "role": "speaker"}]
    assert stored.inferred is False
    assert stored.provenance[0].evidence_type == "explicit"


@pytest.mark.asyncio
async def test_encoder_records_uncovered_segments_without_repair(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_ids = [part.split("]", 1)[0] for part in user.split("[")[1:]]
        return {
            "claims": [{
                "text": "Ava likes tea.",
                "kind": "preference",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_ids[0]],
                "facets": {"object": "tea"},
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: I like tea.\n"
        "[D1:2] (2024-01-10) Ava: I visited Paris yesterday.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )

    report = artifacts.coverage_report()
    assert llm.call_structured.call_count == 1
    assert report["segment_coverage"] == 0.5
    assert len(report["unaccounted_segment_ids"]) == 1
    assert artifacts.list_episodes()[0].extraction_status == "partial"


@pytest.mark.asyncio
async def test_encoder_rejects_batch_that_claims_and_ignores_same_segment(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return {
            "claims": [{
                "text": "Ava prefers tea.",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_id],
            }],
            "ignored_segment_ids": [segment_id],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: I prefer tea.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )

    episode = artifacts.list_episodes()[0]
    assert episode.extraction_status == "partial"
    assert "both claimed and ignored" in str(episode.extraction_error)
    assert artifacts.list_claims() == []


def test_dialogue_shaped_claims_are_rejected_without_repair():
    assert Encoder._is_direct_atomic_claim("It's Shia LaBeouf.") is False
    assert Encoder._is_direct_atomic_claim("The phrase is attributed to Shia LaBeouf.") is True


def test_atomic_claim_requires_an_explicit_about_entity():
    about = [{"entity": "Ava"}]

    assert Encoder._has_explicit_subject("Ava shared a photo showing a blue room.", about)
    assert not Encoder._has_explicit_subject("A photo shows a blue room.", about)
    assert not Encoder._has_explicit_subject("Getting moments of joy is incredible.", about)


def test_subjectless_model_paraphrase_is_attributed_to_its_single_source_speaker():
    result = Encoder._attribute_subjectless_claim(
        "A photo shows a blue room.", ["Ava"], [{"entity": "Ava"}], "visual"
    )

    assert result is not None
    text, about = result
    assert text == "Ava shared a photo showing a blue room."
    assert Encoder._has_explicit_subject(text, about)


def test_subjectless_visual_attribution_repairs_description_grammar_and_ids():
    result = Encoder._attribute_subjectless_claim(
        "A photo of a bookshelf contains many books, according to the image caption "
        "for source-a12#seg-0027.",
        ["Ava"],
        [{"entity": "Ava"}],
        "visual",
    )

    assert result is not None
    text, _ = result
    assert text == "Ava shared a photo of a bookshelf containing many books."
    assert "source-" not in text


def test_labeled_multi_party_turns_are_split_for_atomic_coverage(tmp_path):
    encoder = Encoder(
        AsyncMock(),
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        ArtifactStore(tmp_path / "artifacts"),
    )
    segments = encoder._normalize_segments(
        None,
        "[D1:1] (2023-01-29) Jon: I found a studio. I visited Paris yesterday!\n"
        "Image caption: a bright room",
        "source-1",
        "multi_party_conversation",
    )

    assert [segment.content for segment in segments] == [
        "I found a studio.",
        "I visited Paris yesterday!",
        "Image caption: a bright room",
    ]
    assert all(segment.speaker == "Jon" for segment in segments)
    assert all(segment.timestamp == "2023-01-29" for segment in segments)
    assert all(segment.metadata["source_label"] == "D1:1" for segment in segments)
    assert [segment.index for segment in segments] == [0, 1, 2]


@pytest.mark.asyncio
async def test_encoder_does_not_retry_dialogue_shaped_claim(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return {
            "claims": [{
                "text": "I prefer tea.",
                "kind": "preference",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_id],
                "facets": {"object": "tea"},
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: I prefer tea.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )

    assert llm.call_structured.call_count == 1
    assert artifacts.list_claims() == []
    assert artifacts.list_episodes()[0].extraction_status == "partial"


@pytest.mark.asyncio
async def test_encoder_never_runs_final_normalization_pass(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return {
            "claims": [{
                "text": "My store is doing great!",
                "kind": "state",
                "about": [{"entity": "Ava"}],
                "segment_ids": [segment_id],
                "facets": {},
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: My store is doing great!",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )

    assert llm.call_structured.call_count == 1
    assert artifacts.list_claims() == []
    assert artifacts.list_episodes()[0].extraction_status == "partial"


@pytest.mark.asyncio
async def test_encoder_honors_explicitly_ignored_scaffolding(tmp_path):
    llm = AsyncMock(return_value={
        "claims": [],
        "ignored_segment_ids": [],
    })
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return {"claims": [], "ignored_segment_ids": [segment_id]}

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: Thanks for the encouragement!",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )

    assert llm.call_structured.call_count == 1
    episode = artifacts.list_episodes()[0]
    assert episode.extraction_status == "complete"
    assert len(episode.ignored_segment_ids) == 1
    assert artifacts.coverage_report()["accounted_coverage"] == 1.0


@pytest.mark.asyncio
async def test_encoder_programmatically_ignores_image_urls(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        assert "Image URL:" not in user
        target_ids = [
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if not part.startswith(("TARGET ", "CONTEXT "))
        ]
        return {
            "claims": [{
                "text": "Ava shared a painting.",
                "kind": "event",
                "about": [{"entity": "Ava"}],
                "segment_ids": target_ids,
                "facets": {},
            }],
            "ignored_segment_ids": [],
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: Ava shared a painting.\n"
        "Image URL: ['https://example.test/painting.jpg']",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )

    source = artifacts.list_sources()[0]
    episode = artifacts.list_episodes()[0]
    url_id = next(
        segment.segment_id for segment in source.segments
        if segment.content.startswith("Image URL:")
    )
    assert url_id in episode.ignored_segment_ids
    assert all(
        url_id not in provenance.segment_ids
        for claim in artifacts.list_claims()
        for provenance in claim.provenance
    )


@pytest.mark.asyncio
async def test_encoder_batches_large_initial_extractions(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )
    supplied = [
        SourceSegment("", index, f"Routine acknowledgement {index}.", speaker="Ava")
        for index in range(49)
    ]

    async def response(system, user, output_type, **kwargs):
        segment_ids = [part.split("]", 1)[0] for part in user.split("[")[1:]]
        assert len(segment_ids) <= 48
        return {
            "claims": [],
            "ignored_segment_ids": segment_ids,
        }

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "A large meeting transcript.",
        "session-1",
        source_type="meeting_transcript",
        occurred_at="2024-01-10",
        segments=supplied,
    )

    assert llm.call_structured.call_count == 2
    assert artifacts.list_episodes()[0].extraction_status == "complete"


def test_semantic_envelope_does_not_infer_from_kind_or_prose():
    provenance = [ClaimProvenance("source-1", ["source-1#seg-0001"])]
    unknown = MemoryClaim(
        "unknown", "Ava bought a book.", "event", [{"entity": "Ava"}],
        provenance, "2024-01-01",
    )

    assert unknown.claim_type == "unknown"
    assert unknown.evidence_modality == "unknown"
    assert unknown.temporal_status == "unknown"


def test_human_readable_timestamp_anchors_relative_dates():
    facets = normalize_temporal_facets(
        {"when": "yesterday"}, "4:24 pm on 16 March, 2023"
    )
    assert facets["observed_at"] == "4:24 pm on 16 March, 2023"
    assert facets["temporal"] == {
        "expression": "yesterday",
        "anchor": "4:24 pm on 16 March, 2023",
        "anchor_date": "2023-03-16",
        "role": "event_time",
        "start": "2023-03-15",
        "end": "2023-03-15",
        "precision": "day",
        "status": "resolved",
        "certainty": "exact",
    }


def test_temporal_facets_recover_relative_phrase_from_claim_text():
    facets = normalize_temporal_facets(
        {}, "4:24 pm on 16 March, 2023", "Ava visited Paris yesterday."
    )

    assert facets["temporal"]["expression"] == "yesterday"
    assert facets["temporal"]["start"] == "2023-03-15"
    assert facets["temporal"]["precision"] == "day"


def test_month_relative_time_preserves_month_precision():
    facets = normalize_temporal_facets(
        {"when": "this month"}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["start"] == "2023-03-01"
    assert facets["temporal"]["end"] == "2023-03-31"
    assert facets["temporal"]["precision"] == "month"


@pytest.mark.parametrize(
    ("expression", "start", "end"),
    [
        ("last week", "2023-03-06", "2023-03-12"),
        ("this week", "2023-03-13", "2023-03-19"),
        ("next week", "2023-03-20", "2023-03-26"),
        ("last month", "2023-02-01", "2023-02-28"),
        ("next month", "2023-04-01", "2023-04-30"),
    ],
)
def test_calendar_relative_periods_preserve_full_bounds(expression, start, end):
    facets = normalize_temporal_facets(
        {"when": expression}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["start"] == start
    assert facets["temporal"]["end"] == end


def test_next_month_crosses_year_boundary():
    facets = normalize_temporal_facets(
        {"when": "next month"}, "10:00 am on 20 December, 2023"
    )

    assert facets["temporal"]["start"] == "2024-01-01"
    assert facets["temporal"]["end"] == "2024-01-31"


def test_this_weekday_resolves_within_anchor_calendar_week():
    facets = normalize_temporal_facets(
        {"when": "this Friday"}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["start"] == "2023-03-17"
    assert facets["temporal"]["precision"] == "day"


def test_last_and_next_weekdays_use_adjacent_calendar_weeks():
    last = normalize_temporal_facets(
        {"when": "last Monday"}, "4:24 pm on 16 March, 2023"
    )
    next_ = normalize_temporal_facets(
        {"when": "next Friday"}, "4:24 pm on 16 March, 2023"
    )

    assert last["temporal"]["start"] == "2023-03-06"
    assert next_["temporal"]["start"] == "2023-03-24"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("Friday", "2023-03-17"),
        ("by Friday", "2023-03-17"),
        ("end of this week", "2023-03-19"),
        ("end of next week", "2023-03-26"),
        ("end of next month", "2023-04-30"),
        ("in three days", "2023-03-19"),
    ],
)
def test_meeting_deadlines_resolve_as_due_dates(expression, expected):
    facets = normalize_temporal_facets(
        {"deadline": expression}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["role"] == "deadline"
    assert facets["temporal"]["start"] == expected
    assert facets["temporal"]["end"] == expected


def test_deadline_can_be_recovered_from_claim_text():
    facets = normalize_temporal_facets(
        {},
        "4:24 pm on 16 March, 2023",
        "Ava committed to sending the report by Friday.",
    )

    assert facets["temporal"]["expression"] == "Friday"
    assert facets["temporal"]["role"] == "deadline"
    assert facets["temporal"]["start"] == "2023-03-17"


def test_year_relative_time_preserves_year_precision():
    facets = normalize_temporal_facets(
        {"when": "three years ago"}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["start"] == "2020-01-01"
    assert facets["temporal"]["end"] == "2020-12-31"
    assert facets["temporal"]["precision"] == "year"


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("in three days from now", "2023-03-19"),
        ("two weeks ago", "2023-03-02"),
        ("the day after tomorrow", "2023-03-18"),
        ("the day before yesterday", "2023-03-14"),
    ],
)
def test_exact_relative_offsets_resolve_against_source_time(expression, expected):
    facets = normalize_temporal_facets(
        {"when": expression}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["start"] == expected
    assert facets["temporal"]["end"] == expected
    assert facets["temporal"]["certainty"] == "exact"


@pytest.mark.parametrize(
    ("expression", "start", "end"),
    [
        ("a few days ago", "2023-03-11", "2023-03-14"),
        ("in several weeks from now", "2023-04-06", "2023-05-04"),
        ("early next week", "2023-03-20", "2023-03-22"),
        ("late next week", "2023-03-24", "2023-03-26"),
        ("later this week", "2023-03-17", "2023-03-19"),
    ],
)
def test_vague_but_bounded_time_is_marked_approximate(expression, start, end):
    facets = normalize_temporal_facets(
        {"when": expression}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["start"] == start
    assert facets["temporal"]["end"] == end
    assert facets["temporal"]["status"] == "bounded"
    assert facets["temporal"]["certainty"] == "approximate"


@pytest.mark.parametrize(("expression", "direction"), [("soon", "future"), ("recently", "past")])
def test_unbounded_vague_time_remains_unresolved(expression, direction):
    facets = normalize_temporal_facets(
        {"when": expression}, "4:24 pm on 16 March, 2023"
    )

    assert facets["temporal"]["status"] == "unresolved"
    assert facets["temporal"]["certainty"] == "vague"
    assert facets["temporal"]["direction"] == direction
    assert "start" not in facets["temporal"]


def test_temporal_query_resolves_deadline_range_at_query_time():
    temporal = query_temporal_record(
        "What deadlines are due next week?",
        datetime.fromisoformat("2026-08-11T10:00:00-07:00"),
    )

    assert temporal is not None
    assert temporal["role"] == "deadline"
    assert temporal["start"] == "2026-08-17"
    assert temporal["end"] == "2026-08-23"


def test_temporal_interval_overlap_is_inclusive():
    query = {"start": "2026-08-17", "end": "2026-08-23"}

    assert temporal_intervals_overlap(query, {"start": "2026-08-23", "end": "2026-08-23"})
    assert not temporal_intervals_overlap(
        query, {"start": "2026-08-24", "end": "2026-08-24"}
    )


def test_artifact_store_clear_removes_all_derived_artifacts(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    store.save_source(SourceDocument(
        source_id="source-1", source_type="agent_conversation",
        session_id="session-1", recorded_at="2024-01-01", occurred_at=None,
        participants=["user"],
        segments=[SourceSegment("source-1#seg-0001", 0, "Hello")],
    ))
    store.save_episode(EpisodeManifest(
        episode_id="episode-1", source_id="source-1",
        source_type="agent_conversation", occurred_at=None,
        participants=["user"], segment_ids=["source-1#seg-0001"],
    ))
    store.save_claim(MemoryClaim(
        "claim-1", "The user greeted the assistant.", "interaction",
        [{"entity": "user"}],
        [ClaimProvenance("source-1", ["source-1#seg-0001"])],
        "2024-01-01", claim_type="interaction", evidence_modality="speech",
        temporal_status="past",
    ))
    store.save_reconsolidation_proposal(ReconsolidationProposal(
        proposal_id="recon-1",
        incoming_claim_id="claim-1",
        target_claim_id="claim-2",
        proposed_relation="contradicts",
        explanation="Test proposal",
        confidence=0.8,
        dream_run_id="dream-1",
        created_at="2024-01-01",
    ))

    assert store.clear() == {
        "sources": 1,
        "episodes": 1,
        "claims": 1,
        "dream_runs": 0,
        "reconsolidation_proposals": 1,
        "entities": 0,
        "placements": 0,
        "organization_proposals": 0,
        "scope_decisions": 0,
        "retention_records": 0,
        "entity_references": 0,
        "entity_resolution_decisions": 0,
        "scope_cohorts": 0,
        "encounters": 0,
        "consolidated_facts": 0,
    }
    assert store.list_sources() == []
    assert store.list_episodes() == []
    assert store.list_claims() == []
    assert store.list_reconsolidation_proposals() == []
