from copy import deepcopy
import json

import pytest

from benchmarks.suites.daily_driver.eval import evaluate_run
from benchmarks.suites.daily_driver.fixture import load_fixture
from benchmarks.suites.daily_driver.source_review import (
    checkpoint_review,
    export_source_review,
)
from tests.test_daily_driver_assessment_inputs import claim, fixture, source
from tests.test_daily_driver_fixture import FIXTURE_DIR


def snapshot():
    return {
        "checkpoint_id": "cp1",
        "sources": [source("s1", "first")],
        "claims": [claim("c1", "s1", "first")],
        "entities": [],
        "pages": [],
    }


def test_review_pack_keeps_all_candidates_and_detects_prose_and_state_changes():
    first = snapshot()
    second = deepcopy(first)
    second["claims"].append({**claim("c2", "s1", "first"), "text": "Opposite meaning"})
    second["claims"][0]["status"] = "superseded"
    second["pages"] = [{"slug": "page", "content": "Current prose"}]
    pack = checkpoint_review(fixture(), second, first)
    assert pack["assessment_status"] == "requires_source_review"
    assert pack["claim_inputs"]["requests"][0]["payload"]["references"]["gold"][
        "candidate_claim_ids"
    ] == ["c1", "c2"]
    assert pack["changes"]["claims"]["changed"][0]["before"]["status"] == "active"
    assert pack["changes"]["claims"]["changed"][0]["after"]["status"] == "superseded"
    changed = deepcopy(second)
    changed["pages"][0]["content"] = "Different prose"
    updated = checkpoint_review(fixture(), changed, second)
    assert updated["snapshot_digest"] != pack["snapshot_digest"]
    assert updated["changes"]["pages"]["changed"][0]["id"] == "page"
    assert first["claims"][0]["status"] == "active"


def test_review_pack_rejects_ambiguous_artifact_ids():
    state = snapshot()
    state["entities"] = [{"entity_id": "e"}, {"entity_id": "e"}]
    with pytest.raises(ValueError, match="Duplicate entity_id"):
        checkpoint_review(fixture(), state)


def test_export_preserves_original_files_and_reports_incomplete_checkpoint_set(
    tmp_path,
):
    run = tmp_path / "run"
    cp = run / "checkpoints" / "cp1_pre_dream"
    cp.mkdir(parents=True)
    state = {"checkpoint_id": cp.name, "sources": [], "claims": []}
    path = cp / "snapshot.json"
    original = json.dumps(state)
    path.write_text(original)
    output = tmp_path / "review"
    result = export_source_review(FIXTURE_DIR, run, output)
    assert result["available_checkpoints"] == [cp.name]
    assert result["missing_checkpoints"]
    assert path.read_text() == original
    with pytest.raises(FileExistsError):
        export_source_review(FIXTURE_DIR, run, output)
    assert json.loads((output / "manifest.json").read_text()) == result


def test_unreviewed_lexical_scores_never_assert_release_readiness():
    result = evaluate_run(load_fixture(FIXTURE_DIR), {}, [])
    assert result["assessment_status"] == "requires_source_review"
    assert result["summary"]["assessment_status"] == "requires_source_review"
    assert "release_ready" not in result["summary"]
    assert isinstance(result["summary"]["diagnostic_thresholds_pass"], bool)
