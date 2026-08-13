import shutil
from pathlib import Path

import pytest

from benchmarks.mycelium_bench.daily_driver import load_fixture, validate_fixture


FIXTURE_DIR = Path("benchmarks/fixtures/daily_driver_v1")


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
        "rubric_dimensions": 17,
        "rubric_gates": 5,
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
        (target / name).write_text((FIXTURE_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    text = (FIXTURE_DIR / "gold_claims.yaml").read_text(encoding="utf-8")
    (target / "gold_claims.yaml").write_text(
        text.replace("evidence: [chat-01-s01]", "evidence: [missing-segment]", 1),
        encoding="utf-8",
    )
    (target / "wiki").mkdir()
    for path in (FIXTURE_DIR / "wiki").glob("*.md"):
        (target / "wiki" / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

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
