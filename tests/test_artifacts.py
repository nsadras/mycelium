from datetime import datetime

import pytest
from unittest.mock import AsyncMock

from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    ClaimReconciler,
    EpisodeManifest,
    MemoryClaim,
    ReconsolidationProposal,
    SourceDocument,
    SourceSegment,
    normalize_temporal_facets,
)
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.store import LogStore


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


def test_reconciler_merges_duplicates_but_leaves_slot_changes_for_review(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    reconcile = ClaimReconciler(store).reconcile
    common = dict(
        kind="preference", about=[{"entity": "Ava"}], recorded_at=datetime.now().isoformat(),
        provenance=[ClaimProvenance("source-1", ["source-1#seg-0001"])],
    )
    first = reconcile(MemoryClaim(claim_id="claim-1", text="Ava prefers tea.", slot="favorite_drink", **common))
    duplicate = reconcile(MemoryClaim(claim_id="claim-2", text="Ava prefers tea.", slot="favorite_drink", **common))
    replacement = reconcile(MemoryClaim(claim_id="claim-3", text="Ava now prefers coffee.", slot="favorite_drink", **common))

    assert duplicate.claim_id == first.claim_id
    assert store.get_claim("claim-1").status == "active"
    assert replacement.links == []


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
    assert facets["normalized_date"] == "2023-03-15"


def test_temporal_facets_recover_relative_phrase_from_claim_text():
    facets = normalize_temporal_facets(
        {}, "4:24 pm on 16 March, 2023", "Ava visited Paris yesterday."
    )

    assert facets["when"] == "yesterday"
    assert facets["normalized_date"] == "2023-03-15"
    assert facets["date_precision"] == "day"


def test_month_relative_time_preserves_month_precision():
    facets = normalize_temporal_facets(
        {"when": "this month"}, "4:24 pm on 16 March, 2023"
    )

    assert facets["normalized_date"] == "2023-03"
    assert facets["date_precision"] == "month"


def test_year_relative_time_preserves_year_precision():
    facets = normalize_temporal_facets(
        {"when": "three years ago"}, "4:24 pm on 16 March, 2023"
    )

    assert facets["normalized_date"] == "2020"
    assert facets["date_precision"] == "year"


def test_reconciler_merges_identical_text_despite_kind_label_drift(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    first = MemoryClaim(
        "first", "Ava prefers tea.", "preference", [{"entity": "Ava"}],
        [ClaimProvenance("source-1", ["segment-1"])], "2024-01-01",
    )
    second = MemoryClaim(
        "second", "Ava prefers tea.", "personal fact", [{"entity": "Ava"}],
        [ClaimProvenance("source-2", ["segment-2"])], "2024-01-02",
    )

    reconciler = ClaimReconciler(store)
    reconciler.reconcile(first)
    merged = reconciler.reconcile(second)

    assert merged.claim_id == "first"
    assert {item.source_id for item in merged.provenance} == {"source-1", "source-2"}


def test_reconciler_upgrades_unknown_semantics_from_structured_duplicate(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    unknown = MemoryClaim(
        "unknown", "Ava will send the report.", "action_item", [{"entity": "Ava"}],
        [ClaimProvenance("source-1", ["segment-1"])], "2024-01-01",
    )
    structured = MemoryClaim(
        "structured", "Ava will send the report.", "open subtype", [{"entity": "Ava"}],
        [ClaimProvenance("source-2", ["segment-2"])], "2024-01-02",
        claim_type="commitment", predicate="send_report", evidence_modality="speech",
        temporal_status="future",
    )

    reconciler = ClaimReconciler(store)
    reconciler.reconcile(unknown)
    merged = reconciler.reconcile(structured)

    assert merged.claim_id == "unknown"
    assert merged.claim_type == "commitment"
    assert merged.predicate == "send_report"
    assert merged.temporal_status == "future"


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
    }
    assert store.list_sources() == []
    assert store.list_episodes() == []
    assert store.list_claims() == []
    assert store.list_reconsolidation_proposals() == []


def test_reconciler_uses_structured_relation_across_open_kind_drift(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    first = MemoryClaim(
        "first", "Ava prefers quiet morning meetings.", "personal preference",
        [{"entity": "Ava"}], [ClaimProvenance("source-1", ["segment-1"])],
        "2024-01-01", claim_type="preference", predicate="prefers_meeting_time",
        evidence_modality="speech", temporal_status="recurring",
    )
    second = MemoryClaim(
        "second", "Ava prefers quiet morning work meetings.", "schedule constraint",
        [{"entity": "Ava"}], [ClaimProvenance("source-2", ["segment-2"])],
        "2024-01-02", claim_type="preference", predicate="prefers_meeting_time",
        evidence_modality="speech", temporal_status="recurring",
    )

    reconciler = ClaimReconciler(store)
    reconciler.reconcile(first)
    merged = reconciler.reconcile(second)

    assert merged.claim_id == "first"
    assert {item.source_id for item in merged.provenance} == {"source-1", "source-2"}
