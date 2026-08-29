import shutil
from pathlib import Path

import pytest

from benchmarks.mycelium_bench.daily_driver import load_fixture, validate_fixture
from benchmarks.mycelium_bench.daily_driver_eval import _entity_map, proposition_completeness
from benchmarks.mycelium_bench.daily_driver_run import _replay_extracted_episode
from mycelium.artifacts import (
    ArtifactStore,
    ClaimProvenance,
    EpisodeManifest,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.core import Mycelium


FIXTURE_DIR = Path("benchmarks/fixtures/daily_driver_v1")
TRANSFER_FIXTURES = (
    Path("benchmarks/fixtures/daily_driver_paraphrased_v1"),
    Path("benchmarks/fixtures/daily_driver_unrelated_v1"),
)


def test_daily_driver_fixture_is_internally_consistent():
    summary = validate_fixture(FIXTURE_DIR)

    assert summary == {
        "valid": True,
        "scenario_id": "daily-driver-v1",
        "episodes": 16,
        "sources": 16,
        "segments": 51,
        "claims": 45,
        "consolidated_facts": 29,
        "active_entities": 6,
        "checkpoints": 9,
        "probes": 19,
        "rubric_dimensions": 18,
        "acceptance_dimensions": 7,
        "rubric_gates": 3,
        "deferred_rubric_gates": 2,
        "errors": [],
    }


def test_daily_driver_fixture_has_all_three_source_modalities():
    fixture = load_fixture(FIXTURE_DIR)

    assert {episode["source_type"] for episode in fixture["scenario"]["episodes"]} == {
        "agent_conversation",
        "meeting_transcript",
        "tool_observation",
    }


def test_daily_driver_uses_structural_user_identity_in_sources():
    fixture = load_fixture(FIXTURE_DIR)
    scenario = fixture["scenario"]
    user = scenario["user"]
    user_segments = [
        segment
        for episode in scenario["episodes"]
        for segment in episode["segments"]
        if segment.get("speaker") == user["speaker_label"]
    ]

    assert user == {
        "id": "you",
        "name": "Maya Chen",
        "speaker_label": "User",
        "identity_authority": "configured_profile",
    }
    assert user_segments
    assert all(
        segment["speaker"] != user["name"]
        for episode in scenario["episodes"]
        for segment in episode["segments"]
    )


def test_daily_driver_assistant_dialogue_does_not_leak_memory_operations():
    fixture = load_fixture(FIXTURE_DIR)
    assistant_text = " ".join(
        segment["text"].lower()
        for episode in fixture["scenario"]["episodes"]
        for segment in episode["segments"]
        if segment.get("role") == "assistant"
    )

    assert all(
        term not in assistant_text
        for term in ("wiki", "page", "claim", "memory system")
    )


def test_family_oral_history_is_inferred_instead_of_source_named():
    fixture = load_fixture(FIXTURE_DIR)
    source_text = " ".join(
        segment["text"]
        for episode in fixture["scenario"]["episodes"]
        for segment in episode["segments"]
    )

    assert "Beacon" not in source_text
    assert "Family Oral History" not in source_text
    assert any(
        entity["title"] == "Family Oral History"
        for entity in fixture["gold_wiki"]["entities"]
    )


def test_daily_driver_validator_rejects_unknown_gold_evidence(tmp_path):
    target = tmp_path / "fixture"
    target.mkdir()
    for name in (
        "scenario.yaml",
        "gold_checkpoints.yaml",
        "gold_wiki.yaml",
        "probes.yaml",
        "rubric.yaml",
    ):
        (target / name).write_text(
            (FIXTURE_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    text = (FIXTURE_DIR / "gold_claims.yaml").read_text(encoding="utf-8")
    (target / "gold_claims.yaml").write_text(
        text.replace("evidence: [chat-01-s01]", "evidence: [missing-segment]", 1),
        encoding="utf-8",
    )
    (target / "wiki").mkdir()
    for path in (FIXTURE_DIR / "wiki").glob("*.md"):
        (target / "wiki" / path.name).write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    with pytest.raises(ValueError, match="unknown evidence segment missing-segment"):
        validate_fixture(target)


def test_daily_driver_validator_rejects_undeclared_cross_page_fact_copy(tmp_path):
    target = tmp_path / "fixture"
    shutil.copytree(FIXTURE_DIR, target)
    path = target / "gold_wiki.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "    render_on: [person-priya-raman, project-lantern]\n",
            "",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ordinary facts must render once"):
        validate_fixture(target)


@pytest.mark.parametrize("fixture_dir", TRANSFER_FIXTURES)
def test_daily_driver_transfer_fixtures_are_valid(fixture_dir):
    summary = validate_fixture(fixture_dir)

    assert summary["valid"] is True
    assert summary["checkpoints"] >= 3
    assert summary["probes"] >= 3
    assert summary["rubric_gates"] >= 2


def test_transfer_fixture_vocabulary_does_not_enter_production_code():
    production = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in Path("mycelium").rglob("*.py")
    )

    assert all(
        term not in production
        for term in (
            "hearth",
            "tariq bell",
            "rosa alvarez",
            "kitchen renovation",
        )
    )


def test_proposition_completeness_requires_distinct_generated_claims():
    fixture = {
        "gold_claims": {
            "claims": [
                {"id": "c-one", "evidence": ["segment-1"]},
                {"id": "c-two", "evidence": ["segment-1"]},
            ]
        }
    }
    snapshot_match = {
        "claim_rows": [
            {
                "gold_claim_id": "c-one",
                "semantic_candidate": True,
                "generated_claim_id": "claim-broad",
            },
            {
                "gold_claim_id": "c-two",
                "semantic_candidate": True,
                "generated_claim_id": "claim-broad",
            },
        ]
    }

    result = proposition_completeness(fixture, snapshot_match)

    assert result["propositions_total"] == 2
    assert result["propositions_represented"] == 1
    assert result["complete_multi_assertion_segments"] == 0
    assert result["rows"][0]["complete"] is False


def test_page_entity_score_ignores_provisional_identities():
    fixture = {
        "gold_wiki": {
            "entities": [
                {"id": "project-atlas", "type": "project", "title": "Atlas"}
            ],
            "retracted_entities": [],
        }
    }
    snapshot = {
        "entities": [
            {
                "entity_id": "project-atlas",
                "entity_type": "project",
                "title": "Atlas",
                "aliases": [],
                "status": "active",
                "materialization_state": "materialized",
            },
            {
                "entity_id": "topic-notes",
                "entity_type": "topic",
                "title": "Notes",
                "aliases": [],
                "status": "active",
                "materialization_state": "provisional",
            },
        ]
    }

    _, rows, extras = _entity_map(fixture, snapshot)

    assert rows[0]["generated_entity_id"] == "project-atlas"
    assert extras == []


def test_page_entity_score_defers_entities_supported_only_by_retracted_evidence():
    fixture = {
        "gold_wiki": {"entities": [], "retracted_entities": []},
        "gold_claims": {"claims": [{
            "id": "c-withdrawn",
            "state": "retracted",
            "evidence": ["meeting-wrong-s01"],
        }]},
    }
    snapshot = {
        "entities": [{
            "entity_id": "project-wrong-import",
            "entity_type": "project",
            "title": "Wrong import",
            "aliases": [],
            "status": "active",
            "materialization_state": "materialized",
        }],
        "claims": [{
            "claim_id": "claim-wrong",
            "fixture_evidence": ["meeting-wrong-s01"],
        }],
        "pages": [{
            "entity_id": "project-wrong-import",
            "sections": [{"items": [{"claim_ids": ["claim-wrong"]}]}],
        }],
    }

    _, _, extras = _entity_map(fixture, snapshot)

    assert extras == []


def test_extraction_replay_resets_downstream_claim_state(tmp_path):
    replay = ArtifactStore(tmp_path / "baseline" / "artifacts")
    segment = SourceSegment(
        segment_id="source-1#seg-0001",
        index=0,
        content="A durable statement.",
        metadata={"fixture_segment_id": "chat-01-s01"},
    )
    replay.save_source(
        SourceDocument(
            source_id="source-1",
            source_type="agent_conversation",
            session_id="chat-01",
            recorded_at="2026-01-01T00:00:00+00:00",
            occurred_at="2026-01-01T00:00:00+00:00",
            participants=["User"],
            segments=[segment],
            metadata={"fixture_episode_id": "chat-01"},
        )
    )
    replay.save_claim(
        MemoryClaim(
            claim_id="claim-1",
            text="A durable statement.",
            about=[],
            provenance=[
                ClaimProvenance(source_id="source-1", segment_ids=[segment.segment_id])
            ],
            recorded_at="2026-01-01T00:00:00+00:00",
            status="superseded",
            dream_disposition="routed",
            dream_run_id="old-run",
        )
    )
    replay.save_episode(
        EpisodeManifest(
            episode_id="episode-1",
            source_id="source-1",
            source_type="agent_conversation",
            occurred_at="2026-01-01T00:00:00+00:00",
            participants=["User"],
            segment_ids=[segment.segment_id],
            claim_ids=["claim-1"],
            extraction_status="complete",
        )
    )
    memory = Mycelium(tmp_path / "run" / "store", memory_profile="user")

    _replay_extracted_episode(
        memory,
        replay,
        {"id": "chat-01", "segments": [{"id": "chat-01-s01"}]},
    )

    claim = memory.artifacts.get_claim("claim-1")
    assert claim.status == "active"
    assert claim.dream_disposition == "pending"
    assert claim.dream_run_id is None
    assert memory.artifacts.get_episode("episode-1").claim_ids == ["claim-1"]
