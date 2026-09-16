from tests.extraction_support import time_details
from tests.extraction_support import extraction_response
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
    temporal_intervals_overlap,
)
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.store import LogStore
from mycelium.structured_outputs import extraction_output_model, extraction_records


async def capture_and_extract(encoder, *args, **kwargs):
    """Exercise capture followed by explicit extraction in extractor contract tests."""
    entries = await encoder.capture_session(*args, **kwargs)
    await encoder.extract_pending()
    return entries


def test_combined_extraction_enforces_exact_accounting_and_citations():
    schema = extraction_output_model(["a", "b"], ["prior"])
    claim = {
        "temporal_status": "unknown",
        "text": "Ava prefers tea.",
        "about": [{"entity": "Ava", "role": "subject"}],
        "segment_ids": ["a"],
        "context_segment_ids": ["prior"],
        "claim_type": "unknown",
        "evidence_modality": "unknown",
        "facets": {"times": [], "inference_basis": None},
    }
    valid = extraction_response([claim], ["b"])
    assert extraction_records(schema.model_validate(valid).model_dump())["claims"][0][
        "context_segment_ids"
    ] == ["prior"]
    import copy

    invalid = []
    missing = copy.deepcopy(valid)
    del missing["segments"]["b"]
    invalid.append(missing)
    invalid.append({"segments": {"a": {"claims": []}, "b": None}})
    invalid.append({"segments": {**valid["segments"], "unknown": None}})
    wrong_context = copy.deepcopy(valid)
    wrong_context["segments"]["a"]["claims"][0]["context_segment_ids"] = ["unknown"]
    invalid.append(wrong_context)
    for response in invalid:
        with pytest.raises(ValidationError):
            schema.model_validate(response)
    empty = extraction_response([], ["a", "b"])
    assert extraction_records(schema.model_validate(empty).model_dump())["claims"] == []


@pytest.mark.asyncio
async def test_encoder_persists_source_episode_and_atomic_claims(tmp_path):
    llm = AsyncMock()
    llm.call_structured.return_value = extraction_response(
        [
            {
                "text": "Ava prefers tea.",
                "claim_type": "preference",
                "predicate": None,
                "evidence_modality": "speech",
                "temporal_status": "atemporal",
                "about": [{"entity": "Ava", "role": "subject"}],
                "segment_ids": ["source-fixed-later"],
                "facets": {"times": [], "inference_basis": None},
            }
        ]
    )
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        claim = dict(extraction_records(llm.call_structured.return_value)["claims"][0])
        claim["segment_ids"] = [segment_id]
        return extraction_response([claim])

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: I prefer tea.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    source = artifacts.list_sources()[0]
    episode = artifacts.list_episodes()[0]
    claim = artifacts.list_claims()[0]
    assert source.segments[0].content == "I prefer tea."
    assert episode.extraction_status == "complete"
    assert claim.provenance[0].segment_ids == [source.segments[0].segment_id]
    assert claim.claim_type == "preference"
    assert claim.predicate is None
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
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "Ava prefers tea.",
                    "claim_type": "preference",
                    "predicate": None,
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "evidence_modality": "unknown",
                    "facets": {"times": [], "inference_basis": None},
                }
            ]
        )

    llm.call_structured.side_effect = response
    for session_id in ("session-1", "session-2"):
        await capture_and_extract(
            encoder,
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
            "agent_conversation",
            "USER: Please avoid meetings before 10am.",
            "Nitin prefers meetings at or after 10am.",
            "preference",
            None,
            "recurring",
        ),
        (
            "meeting_transcript",
            "[M1] (2024-01-10) Ava: I will send the report Friday.",
            "Ava committed to sending the report Friday.",
            "commitment",
            None,
            "future",
        ),
    ],
)
async def test_encoder_persists_general_semantics_across_source_types(
    tmp_path, source_type, transcript, text, claim_type, predicate, temporal_status
):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = next(
            (
                part.split("]", 1)[0]
                for part in user.split("[")[1:]
                if part.startswith("source-")
            )
        )
        return extraction_response(
            [
                {
                    "text": text,
                    "claim_type": claim_type,
                    "predicate": predicate,
                    "evidence_modality": "speech",
                    "temporal_status": temporal_status,
                    "about": [{"entity": text.split()[0], "role": "subject"}],
                    "segment_ids": [segment_id],
                    "facets": {"times": [], "inference_basis": None},
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        transcript,
        "session-1",
        source_type=source_type,
        occurred_at="2024-01-10",
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
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = next(
            (
                part.split("]", 1)[0]
                for part in user.split("[")[1:]
                if part.startswith("source-")
            )
        )
        return extraction_response(
            [
                {
                    "text": "Ava committed to sending the report by Friday.",
                    "claim_type": "commitment",
                    "temporal_status": "future",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "facets": time_details(segment_id, "Friday", {"kind":"day_offset", "days":2}, role="deadline"),
                    "evidence_modality": "unknown",
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[M1] Ava: I will send the report by Friday.",
        "meeting-1",
        source_type="meeting_transcript",
        occurred_at="2024-01-10T14:00:00-08:00",
    )
    temporal = artifacts.list_claims()[0].facets["temporal"][0]
    assert temporal["anchor"] == "2024-01-10T14:00:00-08:00"
    assert temporal["role"] == "deadline"
    assert temporal["start"] == "2024-01-12"


@pytest.mark.asyncio
async def test_chat_claim_uses_its_cited_message_as_temporal_anchor(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)
    original_ids = []

    async def response(system, user, output_type, **kwargs):
        segment_ids = [
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if part.startswith("source-")
        ]
        original_ids[:] = segment_ids
        return extraction_response(
            [
                {
                    "text": "Ava will finish the report tomorrow.",
                    "claim_type": "commitment",
                    "temporal_status": "future",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [original_ids[1]],
                                        "facets": time_details(original_ids[1], "tomorrow", {"kind":"day_offset", "days":1}, role="deadline"),
                    "evidence_modality": "unknown",
                }
            ],
            [original_ids[0]],
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "A multi-day chat",
        "chat-1-ep-1",
        source_type="agent_conversation",
        occurred_at="2026-08-26T23:00:00+00:00",
        segments=[
            SourceSegment(
                "",
                0,
                "Earlier context.",
                speaker="user",
                role="user",
                timestamp="2026-08-26T23:00:00+00:00",
            ),
            SourceSegment(
                "",
                1,
                "I will finish the report tomorrow.",
                speaker="Ava",
                role="user",
                timestamp="2026-08-27T08:00:00+00:00",
            ),
        ],
    )
    temporal = artifacts.list_claims()[0].facets["temporal"][0]
    assert temporal["anchor"] == "2026-08-27T08:00:00+00:00"
    assert temporal["start"] == "2026-08-28"


@pytest.mark.asyncio
async def test_relative_phrase_uses_explicit_time_evidence(
    tmp_path,
):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = next(
            (
                part.split("]", 1)[0]
                for part in user.split("[")[1:]
                if part.startswith("source-")
            )
        )
        return extraction_response(
            [
                {
                    "text": "Ava will finish the report tomorrow.",
                    "claim_type": "commitment",
                    "temporal_status": "future",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "facets": time_details(segment_id, "tomorrow", {"kind":"day_offset", "days":1}, role="deadline"),
                    "evidence_modality": "unknown",
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "A multi-day chat",
        "chat-1-ep-1",
        source_type="agent_conversation",
        occurred_at="2026-08-26T23:00:00+00:00",
        segments=[
            SourceSegment(
                "",
                0,
                "I will finish the report tomorrow.",
                speaker="Ava",
                role="user",
                timestamp="2026-08-27T08:00:00+00:00",
            )
        ],
    )
    temporal = artifacts.list_claims()[0].facets["temporal"][0]
    assert temporal["anchor"] == "2026-08-27T08:00:00+00:00"
    assert temporal["start"] == "2026-08-28"


@pytest.mark.asyncio
async def test_chat_rejects_time_anchor_outside_claim_citations(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)
    original_ids = []

    async def response(system, user, output_type, **kwargs):
        segment_ids = [
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if part.startswith("source-")
        ]
        original_ids[:] = segment_ids
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "The conversation includes earlier context.",
                    "about": [{"entity": "conversation", "role": "subject"}],
                    "segment_ids": [original_ids[0]],
                    "claim_type": "unknown",
                    "evidence_modality": "unknown",
                    "facets": {"times": [], "inference_basis": None},
                },
                {
                    "text": "Ava will finish the report tomorrow.",
                    "claim_type": "commitment",
                    "temporal_status": "future",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [original_ids[1]],
                                        "facets": time_details(original_ids[0], "tomorrow", {"kind":"day_offset", "days":1}, role="deadline"),
                    "evidence_modality": "unknown",
                },
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "A multi-day chat",
        "chat-1-ep-1",
        source_type="agent_conversation",
        occurred_at="2026-08-26T23:00:00+00:00",
        segments=[
            SourceSegment(
                "",
                0,
                "Earlier context.",
                speaker="user",
                role="user",
                timestamp="2026-08-26T23:00:00+00:00",
            ),
            SourceSegment(
                "",
                1,
                "I will finish the report tomorrow.",
                speaker="Ava",
                role="user",
                timestamp="2026-08-27T08:00:00+00:00",
            ),
        ],
    )
    assert artifacts.list_claims() == []
    episode = artifacts.list_episodes()[0]
    assert episode.extraction_status != "complete"
    assert "time anchor" in episode.extraction_batches[0].last_error


@pytest.mark.asyncio
async def test_encoder_rejects_claim_without_explicit_about_entity(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_ids = [
            part.split("]", 1)[0]
            for part in user.split("[")[1:]
            if not part.startswith(("TARGET ", "CONTEXT "))
        ]
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "Ava enjoys teaching dance.",
                    "about": [],
                    "segment_ids": segment_ids,
                    "facets": {"times": [], "inference_basis": None},
                    "claim_type": "unknown",
                    "evidence_modality": "unknown",
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: Teaching dance is something I enjoy.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    assert artifacts.list_claims() == []
    assert artifacts.list_episodes()[0].extraction_status == "partial"


@pytest.mark.asyncio
async def test_encoder_retries_failed_combined_batch(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)
    claim_attempts = 0

    async def response(system, user, output_type, **kwargs):
        nonlocal claim_attempts
        segment_id = next(
            (
                part.split("]", 1)[0]
                for part in user.split("[")[1:]
                if part.startswith("source-")
            )
        )
        claim_attempts += 1
        if claim_attempts == 1:
            raise ValueError("temporary malformed claim response")
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "Ava prefers tea.",
                    "claim_type": "preference",
                    "predicate": None,
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "evidence_modality": "unknown",
                    "facets": {"times": [], "inference_basis": None},
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "Ava: I prefer tea.",
        "session-1",
        source_type="multi_party_conversation",
    )
    partial = artifacts.list_episodes()[0]
    assert partial.extraction_status == "partial"
    assert artifacts.list_ingestion_operations()[0].status == "failed"
    assert partial.extraction_batches[0].status == "failed"
    assert partial.segment_dispositions == []
    report = artifacts.coverage_report()
    assert report["unaccounted_segment_ids"] == []
    assert len(report["pending_extraction_segment_ids"]) == 1
    completed = await encoder.extract_pending()
    assert completed == [partial.episode_id]
    episode = artifacts.list_episodes()[0]
    assert episode.extraction_status == "complete"
    operation = artifacts.list_ingestion_operations()[0]
    assert operation.status == "complete"
    assert operation.error is None
    assert episode.extraction_batches[0].attempt_count == 2
    assert episode.segment_dispositions[0].disposition == "claimed"
    assert len(artifacts.list_claims()) == 1
    assert llm.call_structured.call_count == 2


@pytest.mark.asyncio
async def test_encoder_records_inference_only_on_provenance(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "Ava is Clara's grandmother.",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "evidence_modality": "speech",
                    "facets": {
                        "times": [],
                        "inference_basis": "Ava's son Ben has a daughter named Clara.",
                    },
                    "claim_type": "unknown",
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "Ava: My son Ben has a daughter named Clara.",
        "session-1",
        source_type="agent_conversation",
    )
    stored = artifacts.list_claims()[0]
    assert stored.provenance[0].evidence_type == "inferred"
    assert stored.evidence_modality == "speech"


@pytest.mark.asyncio
async def test_encoder_records_uncovered_segments_without_repair(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_ids = [part.split("]", 1)[0] for part in user.split("[")[1:]]
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "Ava likes tea.",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_ids[0]],
                    "facets": {"times": [], "inference_basis": None},
                    "claim_type": "unknown",
                    "evidence_modality": "unknown",
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: I like tea.\n[D1:2] (2024-01-10) Ava: I visited Paris yesterday.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    report = artifacts.coverage_report()
    assert llm.call_structured.call_count == 1
    assert report["segment_coverage"] == 0.0
    assert len(report["pending_extraction_segment_ids"]) == 2
    assert artifacts.list_claims() == []
    assert artifacts.list_episodes()[0].extraction_status == "partial"


@pytest.mark.asyncio
async def test_encoder_rejects_undeclared_segment_decisions(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        value = extraction_response([], [segment_id])
        value["segments"]["unknown"] = None
        return value

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: I prefer tea.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    episode = artifacts.list_episodes()[0]
    assert episode.extraction_status == "partial"
    assert "unknown" in str(episode.extraction_error)
    assert artifacts.list_claims() == []


def test_labeled_multi_party_turns_are_split_for_atomic_coverage(tmp_path):
    encoder = Encoder(
        AsyncMock(),
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        ArtifactStore(tmp_path / "artifacts"),
    )
    segments = encoder._normalize_segments(
        None,
        "[D1:1] (2023-01-29) Jon: I found a studio. I visited Paris yesterday!\nImage caption: a bright room",
        "source-1",
        "multi_party_conversation",
    )
    assert [segment.content for segment in segments] == [
        "I found a studio.",
        "I visited Paris yesterday!",
        "Image caption: a bright room",
    ]
    assert all((segment.speaker == "Jon" for segment in segments))
    assert all((segment.timestamp == "2023-01-29" for segment in segments))
    assert all((segment.metadata["source_label"] == "D1:1" for segment in segments))
    assert [segment.index for segment in segments] == [0, 1, 2]


@pytest.mark.asyncio
async def test_encoder_does_not_lexically_reject_model_valid_claim_text(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "I prefer tea.",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "facets": {"times": [], "inference_basis": None},
                    "claim_type": "unknown",
                    "evidence_modality": "unknown",
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: I prefer tea.",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    assert llm.call_structured.call_count == 1
    assert artifacts.list_claims()[0].text == "I prefer tea."
    assert artifacts.list_episodes()[0].extraction_status == "complete"


@pytest.mark.asyncio
async def test_encoder_persists_contract_output_without_final_normalization(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "My store is doing great!",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "facets": {"times": [], "inference_basis": None},
                    "claim_type": "unknown",
                    "evidence_modality": "unknown",
                }
            ]
        )

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: My store is doing great!",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    assert llm.call_structured.call_count == 1
    assert artifacts.list_claims()[0].text == "My store is doing great!"
    assert artifacts.list_episodes()[0].extraction_status == "complete"


@pytest.mark.asyncio
async def test_encoder_honors_explicit_source_only_scaffolding(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return extraction_response([], [segment_id])

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: Thanks for the encouragement!",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    assert llm.call_structured.call_count == 1
    episode = artifacts.list_episodes()[0]
    assert episode.extraction_status == "complete"
    assert len(episode.segment_dispositions) == 1
    assert episode.segment_dispositions[0].disposition == "source_only"
    assert artifacts.coverage_report()["accounted_coverage"] == 1.0


@pytest.mark.asyncio
async def test_encoder_routes_image_urls_through_semantic_coverage(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    async def response(system, user, output_type, **kwargs):
        source_ids = [
            segment.segment_id for segment in artifacts.list_sources()[0].segments
        ]
        target_ids = (
            source_ids if "segments" in output_type.model_fields else source_ids[:1]
        )
        claim = {
            "temporal_status": "unknown",
            "text": "Ava shared a painting.",
            "about": [{"entity": "Ava", "role": "subject"}],
            "segment_ids": [target_ids[0]],
            "facets": {"times": [], "inference_basis": None},
            "claim_type": "unknown",
            "evidence_modality": "unknown",
        }
        return extraction_response([claim], target_ids[1:])

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "[D1:1] (2024-01-10) Ava: Ava shared a painting.\nImage URL: ['https://example.test/painting.jpg']",
        "session-1",
        source_type="multi_party_conversation",
        occurred_at="2024-01-10",
    )
    source = artifacts.list_sources()[0]
    episode = artifacts.list_episodes()[0]
    url_id = next(
        (
            segment.segment_id
            for segment in source.segments
            if segment.content.startswith("Image URL:")
        )
    )
    disposition = next(
        (item for item in episode.segment_dispositions if item.segment_id == url_id)
    )
    assert disposition.disposition == "source_only"
    assert all(
        (
            url_id not in provenance.segment_ids
            for claim in artifacts.list_claims()
            for provenance in claim.provenance
        )
    )


@pytest.mark.asyncio
async def test_encoder_batches_large_initial_extractions(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)
    supplied = [
        SourceSegment("", index, f"Routine acknowledgement {index}.", speaker="Ava")
        for index in range(49)
    ]

    async def response(system, user, output_type, **kwargs):
        segment_ids = list(output_type.model_fields["segments"].annotation.model_fields)
        assert len(segment_ids) <= 48
        return extraction_response([], segment_ids)

    llm.call_structured.side_effect = response
    await capture_and_extract(
        encoder,
        "A large meeting transcript.",
        "session-1",
        source_type="meeting_transcript",
        occurred_at="2024-01-10",
        segments=supplied,
    )
    assert llm.call_structured.call_count == 2
    assert [call.kwargs["think"] for call in llm.call_structured.await_args_list] == [
        False,
        True,
    ]
    assert artifacts.list_episodes()[0].extraction_status == "complete"


def test_semantic_envelope_does_not_infer_from_kind_or_prose():
    provenance = [ClaimProvenance("source-1", ["source-1#seg-0001"])]
    unknown = MemoryClaim(
        claim_id="unknown",
        text="Ava bought a book.",
        about=[{"entity": "Ava"}],
        provenance=provenance,
        recorded_at="2024-01-01",
    )
    assert unknown.claim_type == "unknown"
    assert unknown.evidence_modality == "unknown"
    assert unknown.temporal_status == "unknown"


def test_human_readable_source_timestamp_anchors_declared_offset():
    facets = normalize_temporal_facets(time_details('s1', 'yesterday', {'kind':'day_offset','days':-1}),
                                      {'s1': '4:24 pm on 16 March, 2023'})
    assert facets['temporal'][0]['start'] == '2023-03-15'
    assert facets['temporal'][0]['anchor'] == '4:24 pm on 16 March, 2023'


def test_temporal_interval_overlap_is_inclusive():
    query = {"start": "2026-08-17", "end": "2026-08-23"}
    assert temporal_intervals_overlap(
        query, {"start": "2026-08-23", "end": "2026-08-23"}
    )
    assert not temporal_intervals_overlap(
        query, {"start": "2026-08-24", "end": "2026-08-24"}
    )


def test_artifact_store_clear_removes_all_derived_artifacts(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    store.save_source(
        SourceDocument(
            source_id="source-1",
            source_type="agent_conversation",
            session_id="session-1",
            recorded_at="2024-01-01",
            occurred_at=None,
            participants=["user"],
            segments=[SourceSegment("source-1#seg-0001", 0, "Hello")],
        )
    )
    store.save_episode(
        EpisodeManifest(
            episode_id="episode-1",
            source_id="source-1",
            source_type="agent_conversation",
            occurred_at=None,
            participants=["user"],
            segment_ids=["source-1#seg-0001"],
        )
    )
    store.save_claim(
        MemoryClaim(
            claim_id="claim-1",
            text="The user greeted the assistant.",
            about=[{"entity": "user"}],
            provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
            recorded_at="2024-01-01",
            claim_type="interaction",
            evidence_modality="speech",
            temporal_status="past",
        )
    )
    store.save_reconsolidation_proposal(
        ReconsolidationProposal(
            proposal_id="recon-1",
            incoming_claim_ids=["claim-1"],
            target_claim_ids=["claim-2"],
            proposed_relation="contradicts",
            explanation="Test proposal",
            confidence=0.8,
            dream_run_id="dream-1",
            created_at="2024-01-01",
        )
    )
    counts = store.clear()
    assert counts["sources"] == counts["episodes"] == counts["claims"] == 1
    assert store.list_sources() == []
    assert store.list_episodes() == []
    assert store.list_claims() == []
    assert store.list_reconsolidation_proposals() == []


@pytest.mark.asyncio
async def test_ingestion_idempotency_key_reuses_one_source_episode_claim_and_log(
    tmp_path,
):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    logs = LogStore(tmp_path / "logs")
    encoder = Encoder(llm, logs, Config.defaults(), artifacts)

    async def response(_system, user, output_type, **_kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "Ava prefers tea.",
                    "claim_type": "preference",
                    "predicate": None,
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "evidence_modality": "unknown",
                    "facets": {"times": [], "inference_basis": None},
                }
            ]
        )

    llm.call_structured.side_effect = response
    first = await capture_and_extract(
        encoder,
        "Ava: I prefer tea.",
        "session-1",
        idempotency_key="chat-episode:session-1-ep-1",
    )
    second = await capture_and_extract(
        encoder,
        "Ava: I prefer tea.",
        "session-1",
        idempotency_key="chat-episode:session-1-ep-1",
    )
    assert first[0].entry_id == second[0].entry_id
    assert len(logs.list_entries(days=None)) == 1
    assert len(artifacts.list_sources()) == 1
    assert len(artifacts.list_episodes()) == 1
    assert len(artifacts.list_claims()) == 1
    assert artifacts.list_ingestion_operations()[0].status == "complete"
    assert llm.call_structured.await_count == 1


@pytest.mark.asyncio
async def test_ingestion_retry_repairs_claim_saved_before_episode_checkpoint(
    tmp_path, monkeypatch
):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    logs = LogStore(tmp_path / "logs")
    encoder = Encoder(llm, logs, Config.defaults(), artifacts)

    async def response(_system, user, output_type, **_kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return extraction_response(
            [
                {
                    "temporal_status": "unknown",
                    "text": "Ava prefers tea.",
                    "claim_type": "preference",
                    "about": [{"entity": "Ava", "role": "subject"}],
                    "segment_ids": [segment_id],
                    "evidence_modality": "unknown",
                    "facets": {"times": [], "inference_basis": None},
                }
            ]
        )

    llm.call_structured.side_effect = response
    original_save_claim = artifacts.save_claim
    interrupted = False

    def interrupt_after_claim_write(claim):
        nonlocal interrupted
        original_save_claim(claim)
        if not interrupted:
            interrupted = True
            raise OSError("simulated interruption after claim write")

    monkeypatch.setattr(artifacts, "save_claim", interrupt_after_claim_write)
    await capture_and_extract(
        encoder,
        "Ava: I prefer tea.",
        "session-1",
        idempotency_key="chat-episode:session-1-ep-1",
    )
    assert artifacts.list_ingestion_operations()[0].status == "failed"
    assert len(artifacts.list_claims()) == 1
    monkeypatch.setattr(artifacts, "save_claim", original_save_claim)
    await capture_and_extract(
        encoder,
        "Ava: I prefer tea.",
        "session-1",
        idempotency_key="chat-episode:session-1-ep-1",
    )
    episode = artifacts.list_episodes()[0]
    assert artifacts.list_ingestion_operations()[0].status == "complete"
    assert episode.extraction_status == "complete"
    assert episode.claim_ids == [artifacts.list_claims()[0].claim_id]
    assert len(artifacts.list_claims()) == 1
    assert len(logs.list_entries(days=None)) == 1


@pytest.mark.asyncio
async def test_ingestion_key_rejects_different_input(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, LogStore(tmp_path / "logs"), Config.defaults(), artifacts)
    llm.call_structured.side_effect = [{"segments": {"unused": None}}]
    await capture_and_extract(
        encoder, "First transcript", "session-1", idempotency_key="stable-key"
    )
    with pytest.raises(ValueError, match="different input"):
        await capture_and_extract(
            encoder, "Different transcript", "session-1", idempotency_key="stable-key"
        )


def test_repository_values_are_independent_and_observe_committed_edits(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    store.db.put("claims", "a", {"text": "Original"})
    first = store.db.get("claims", "a")
    first["text"] = "Caller edit"
    assert store.db.get("claims", "a")["text"] == "Original"
    revision = store.db.revision("claims")
    store.db.put("claims", "a", {"text": "Committed"})
    assert store.db.revision("claims") > revision
    assert store.db.get("claims", "a")["text"] == "Committed"
