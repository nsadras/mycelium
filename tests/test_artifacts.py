from datetime import datetime

import pytest
from unittest.mock import AsyncMock

from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    ClaimReconciler,
    MemoryClaim,
    SourceSegment,
    normalize_temporal_facets,
)
from mycelium.config import Config
from mycelium.encoder import Encoder
from mycelium.store import LogStore, WikiStore


@pytest.mark.asyncio
async def test_encoder_persists_source_episode_and_atomic_claims(tmp_path):
    llm = AsyncMock()
    llm.call_structured.return_value = {
        "summary": "Ava described a preference and a plan.",
        "claims": [
            {
                "text": "Ava prefers tea.", "kind": "preference",
                "about": [{"entity": "Ava", "role": "person"}],
                "segment_ids": ["source-fixed-later"],
                "confidence": 0.9, "facets": {"object": "tea"},
            }
        ],
    }
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(llm, WikiStore(tmp_path / "wiki"), LogStore(tmp_path / "logs"), Config.defaults(), artifacts)

    # Make the mock use the generated segment id returned in the extraction prompt.
    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        value = dict(llm.call_structured.return_value)
        value["claims"] = [dict(value["claims"][0], segment_ids=[segment_id])]
        return value
    llm.call_structured.side_effect = response

    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: I prefer tea.", "session-1",
        source_type="benchmark_conversation", occurred_at="2024-01-10",
    )

    source = artifacts.list_sources()[0]
    episode = artifacts.list_episodes()[0]
    claim = artifacts.list_claims()[0]
    assert source.segments[0].content == "I prefer tea."
    assert episode.extraction_status == "complete"
    assert claim.provenance[0].segment_ids == [source.segments[0].segment_id]
    assert artifacts.coverage_report()["segment_coverage"] == 1.0


@pytest.mark.asyncio
async def test_encoder_fills_missing_about_and_requires_inference_basis(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        WikiStore(tmp_path / "wiki"),
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
            "summary": "",
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
        source_type="benchmark_conversation",
        occurred_at="2024-01-10",
    )

    stored = artifacts.list_claims()[0]
    assert stored.about == [{"entity": "Ava", "role": "speaker"}]
    assert stored.inferred is False
    assert stored.provenance[0].evidence_type == "explicit"


@pytest.mark.asyncio
async def test_encoder_repairs_substantive_unclaimed_segments(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        WikiStore(tmp_path / "wiki"),
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        repairing = kwargs.get("debug_label", "").startswith("claim-coverage-repair")
        if repairing:
            segment_ids = [
                part.split("]", 1)[0].removeprefix("TARGET ")
                for part in user.split("[")[1:]
                if part.startswith("TARGET ")
            ]
        else:
            segment_ids = [part.split("]", 1)[0] for part in user.split("[")[1:]]
        if repairing:
            return {
                "summary": "",
                "claims": [{
                    "text": "Ava visited Paris yesterday.",
                    "kind": "event",
                    "about": [{"entity": "Ava"}],
                    "segment_ids": segment_ids,
                    "facets": {"when": "yesterday", "location": "Paris"},
                }],
                "ignored_segment_ids": [],
            }
        return {
            "summary": "Ava likes tea.",
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
        source_type="benchmark_conversation",
        occurred_at="2024-01-10",
    )

    report = artifacts.coverage_report()
    assert llm.call_structured.call_count == 2
    assert report["segment_coverage"] == 1.0
    assert artifacts.list_episodes()[0].extraction_status == "complete"


def test_repair_rendering_includes_neighbor_context_but_marks_only_gap_as_target():
    segments = [
        SourceSegment("source-1#seg-0001", 0, "Who said it?", speaker="Jon"),
        SourceSegment("source-1#seg-0002", 1, "It's Shia LaBeouf.", speaker="Gina"),
        SourceSegment("source-1#seg-0003", 2, "Really?", speaker="Jon"),
    ]

    rendered = Encoder._render_repair_segments(
        segments, {"source-1#seg-0002"}
    )

    assert "[CONTEXT source-1#seg-0001]" in rendered
    assert "[TARGET source-1#seg-0002]" in rendered
    assert "[CONTEXT source-1#seg-0003]" in rendered
    assert Encoder._is_direct_atomic_claim("It's Shia LaBeouf.") is False
    assert Encoder._is_direct_atomic_claim("The phrase is attributed to Shia LaBeouf.") is True


def test_benchmark_turns_are_split_for_atomic_coverage(tmp_path):
    encoder = Encoder(
        AsyncMock(),
        WikiStore(tmp_path / "wiki"),
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        ArtifactStore(tmp_path / "artifacts"),
    )
    segments = encoder._normalize_segments(
        None,
        "[D1:1] (2023-01-29) Jon: I found a studio. I visited Paris yesterday!\n"
        "Image caption: a bright room",
        "source-1",
        "benchmark_conversation",
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
async def test_encoder_repairs_dialogue_shaped_claim_as_atomic_fact(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        WikiStore(tmp_path / "wiki"),
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        repairing = kwargs.get("debug_label", "").startswith("claim-coverage-repair")
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        if repairing:
            segment_id = segment_id.removeprefix("TARGET ")
            text = "Ava prefers tea."
        else:
            text = "I prefer tea."
        return {
            "summary": "",
            "claims": [{
                "text": text,
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
        source_type="benchmark_conversation",
        occurred_at="2024-01-10",
    )

    assert llm.call_structured.call_count == 2
    assert [claim.text for claim in artifacts.list_claims()] == ["Ava prefers tea."]
    assert artifacts.list_episodes()[0].extraction_status == "complete"


@pytest.mark.asyncio
async def test_encoder_runs_bounded_final_normalization_for_rejected_repair(tmp_path):
    llm = AsyncMock()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        WikiStore(tmp_path / "wiki"),
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        label = kwargs.get("debug_label", "")
        raw_id = user.split("[", 1)[1].split("]", 1)[0]
        segment_id = raw_id.removeprefix("TARGET ")
        text = (
            "Ava's store is doing well."
            if label.startswith("claim-final-repair")
            else "My store is doing great!"
        )
        return {
            "summary": "",
            "claims": [{
                "text": text,
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
        source_type="benchmark_conversation",
        occurred_at="2024-01-10",
    )

    assert llm.call_structured.call_count == 3
    assert [claim.text for claim in artifacts.list_claims()] == [
        "Ava's store is doing well."
    ]
    assert artifacts.list_episodes()[0].extraction_status == "complete"


@pytest.mark.asyncio
async def test_encoder_honors_explicitly_ignored_scaffolding(tmp_path):
    llm = AsyncMock(return_value={
        "summary": "",
        "claims": [],
        "ignored_segment_ids": [],
    })
    artifacts = ArtifactStore(tmp_path / "artifacts")
    encoder = Encoder(
        llm,
        WikiStore(tmp_path / "wiki"),
        LogStore(tmp_path / "logs"),
        Config.defaults(),
        artifacts,
    )

    async def response(system, user, output_type, **kwargs):
        segment_id = user.split("[", 1)[1].split("]", 1)[0]
        return {"summary": "", "claims": [], "ignored_segment_ids": [segment_id]}

    llm.call_structured.side_effect = response
    await encoder.encode_session(
        "[D1:1] (2024-01-10) Ava: Thanks for the encouragement!",
        "session-1",
        source_type="benchmark_conversation",
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
        WikiStore(tmp_path / "wiki"),
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
            "summary": "",
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
        source_type="benchmark_conversation",
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
        WikiStore(tmp_path / "wiki"),
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
            "summary": "",
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


def test_reconciler_merges_duplicates_and_supersedes_slots(tmp_path):
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
    assert store.get_claim("claim-1").status == "superseded"
    assert replacement.links[0]["relation"] == "supersedes"


def test_locomo_style_timestamp_anchors_relative_dates():
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
