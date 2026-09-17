import copy
from pathlib import Path
import shutil
from unittest.mock import AsyncMock

import pytest
import yaml

from benchmarks.suites.daily_driver.eval import _capture_checks, _checkpoint_results
from benchmarks.suites.daily_driver.fixture import load_fixture, validate_fixture
from benchmarks.suites.daily_driver.run import _ingest_episode, _snapshot
from mycelium import Mycelium


ROOT = Path("benchmarks/suites/daily_driver/fixtures")
FIXTURES = [
    ROOT / name
    for name in (
        "daily_driver_v2",
        "daily_driver_paraphrased_v2",
        "daily_driver_unrelated_v2",
    )
]


@pytest.mark.parametrize("path", FIXTURES)
def test_v2_preserves_later_gold_and_applies_the_two_user_decisions(path):
    assert validate_fixture(path)["valid"]
    fixture = load_fixture(path)
    original = load_fixture(path.with_name(path.name[:-1] + "1"))
    assert (
        fixture["gold_checkpoints"]["checkpoints"][2:]
        == original["gold_checkpoints"]["checkpoints"][2:]
    )
    assert fixture["gold_claims"]["claims"] == original["gold_claims"]["claims"]
    assert fixture["gold_wiki"]["entities"] == original["gold_wiki"]["entities"]
    assert fixture["gold_wiki"]["facts"] == original["gold_wiki"]["facts"]
    cp1, cp2 = fixture["gold_checkpoints"]["checkpoints"][:2]
    assert cp1["claim_count"] == 0
    assert not cp1["queue"]["pending"]
    assert cp1["captured_sources"]
    assert (
        cp2["searchable_claims"]
        == original["gold_checkpoints"]["checkpoints"][0]["queue"]["pending"]
    )
    assert not cp2.get("forbidden_pages") and not cp2["queue"]["deferred"]
    before, after = fixture["probes"]["probes"][:2]
    assert not before["answerable"] and not before["required_facts"]
    assert before["forbidden_evidence"]
    assert after["answerable"] and after["required_facts"]
    assert after["checkpoint"] == cp2["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", FIXTURES)
async def test_capture_before_build_retains_exact_source_without_model_calls(
    tmp_path, path
):
    fixture = load_fixture(path)
    episode = fixture["scenario"]["episodes"][0]
    cp1 = fixture["gold_checkpoints"]["checkpoints"][0]
    with Mycelium(tmp_path / "store") as memory:
        memory.llm.call_structured = AsyncMock(
            side_effect=AssertionError("Extraction must wait for Build")
        )
        await _ingest_episode(
            memory,
            episode,
            user_speaker_label=fixture["scenario"]["user"]["speaker_label"],
        )
        snapshot = _snapshot(memory, cp1["id"])
        checks = _capture_checks(fixture, snapshot, cp1)
        assert checks and all(row["passed"] for row in checks), checks
        memory.llm.call_structured.assert_not_called()
    with Mycelium(tmp_path / "store") as reopened:
        assert all(
            row["passed"]
            for row in _capture_checks(fixture, _snapshot(reopened, cp1["id"]), cp1)
        )


@pytest.mark.asyncio
async def test_capture_check_rejects_missing_changed_duplicated_and_reordered_evidence(
    tmp_path,
):
    fixture = load_fixture(FIXTURES[0])
    episode = fixture["scenario"]["episodes"][0]
    cp1 = fixture["gold_checkpoints"]["checkpoints"][0]
    with Mycelium(tmp_path / "store") as memory:
        await _ingest_episode(memory, episode, user_speaker_label="User")
        snapshot = _snapshot(memory, cp1["id"])
    for mutation in (
        lambda s: s["sources"].clear(),
        lambda s: s["sources"].append(copy.deepcopy(s["sources"][0])),
        lambda s: s["sources"][0]["segments"].pop(),
        lambda s: s["sources"][0]["segments"].reverse(),
        lambda s: s["sources"][0]["segments"][0].update(content="Truncated source"),
        lambda s: s["sources"][0]["segments"][0].update(role="assistant"),
        lambda s: s["sources"][0].update(occurred_at="2032-01-01T00:00:00Z"),
        lambda s: s["sources"][0]["segments"][0].update(
            segment_id=s["sources"][0]["segments"][1]["segment_id"]
        ),
    ):
        changed = copy.deepcopy(snapshot)
        mutation(changed)
        assert not _capture_checks(fixture, changed, cp1)[0]["passed"]
    for mutation, kind in (
        (lambda s: s["claims"].append({"claim_id": "premature"}), "claim_count"),
        (
            lambda s: s["episodes"][0].update(extraction_status="complete"),
            "source_extraction",
        ),
        (
            lambda s: s["episodes"].append(copy.deepcopy(s["episodes"][0])),
            "source_extraction",
        ),
    ):
        changed = copy.deepcopy(snapshot)
        mutation(changed)
        assert not next(
            c for c in _capture_checks(fixture, changed, cp1) if c["kind"] == kind
        )["passed"]


@pytest.mark.parametrize(
    "disposition,passed",
    [
        ("routed", True),
        ("deferred", True),
        ("pending", False),
        ("routing_failed", False),
        ("excluded_source_policy", False),
    ],
)
def test_first_build_claim_check_allows_useful_evidence_without_a_page(
    monkeypatch, disposition, passed
):
    from benchmarks.suites.daily_driver import eval as daily_eval

    fixture = {
        "gold_checkpoints": {
            "checkpoints": [{"id": "first", "searchable_claims": ["gold"]}]
        }
    }
    matched = {
        "claim_rows": [
            {
                "gold_claim_id": "gold",
                "generated_status": "active",
                "lexical_candidate": True,
                "generated_disposition": disposition,
                "generated_owner": None,
            }
        ],
        "fact_rows": [],
        "entity_map": {},
    }
    monkeypatch.setattr(daily_eval, "match_snapshot", lambda *_: matched)
    assert (
        _checkpoint_results(fixture, {"first": {"claims": []}})[0]["passed"] == passed
    )


def test_v2_rejects_unquoted_yaml_that_truncates_a_source_sentence(tmp_path):
    path = tmp_path / "fixture"
    shutil.copytree(FIXTURES[1], path)
    scenario = load_fixture(path)["scenario"]
    text = scenario["episodes"][0]["segments"][2]["text"]
    assert (
        text
        == "It must stay on my computer, and every summary needs to link back to the exact quotation. I have not named the effort."
    )
    scenario["episodes"][0]["segments"][2]["unexpected trailing sentence"] = None
    (path / "scenario.yaml").write_text(yaml.safe_dump(scenario))
    with pytest.raises(ValueError, match="unexpected fields"):
        validate_fixture(path)
