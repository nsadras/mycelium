import asyncio
import json

import pytest

from benchmarks.shared import run_tracking


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
@pytest.mark.parametrize("encoding", ["running", "complete"])
async def test_terminal_invocation_closes_running_stages_without_erasing_progress(
    tmp_path, monkeypatch, failure, encoding
):
    monkeypatch.setattr(run_tracking, "environment_manifest", lambda: {"test": True})
    before = {
        "status": "running",
        "execution_status": "running",
        "encoding_status": encoding,
        "qa_status": "running",
        "scoring_status": "disabled",
        "assessment_status": "running",
        "encoded_sessions": 3,
        "completed_questions": 7,
    }

    @run_tracking.recorded_run
    async def run():
        (tmp_path / "run_manifest.json").write_text(json.dumps(before))
        run_tracking.begin_invocation(tmp_path)
        raise failure("Interrupted stage")

    with pytest.raises(failure):
        await run()
    actual = json.loads((tmp_path / "run_manifest.json").read_text())
    assert actual["status"] == actual["execution_status"] == "failed"
    assert actual["encoding_status"] == (
        "complete" if encoding == "complete" else "incomplete"
    )
    assert actual["qa_status"] == actual["assessment_status"] == "incomplete"
    assert actual["scoring_status"] == "disabled"
    assert actual["encoded_sessions"] == 3 and actual["completed_questions"] == 7
    assert actual["execution_error"] == f"{failure.__name__}: Interrupted stage"
    events = [
        json.loads(line)
        for line in (tmp_path / "invocations.jsonl").read_text().splitlines()
    ]
    assert events[-1]["status"] == "failed" and events[-1]["elapsed_seconds"] > 0
    assert events[0]["invocation_id"] == events[-1]["invocation_id"]
    assert set(p.name for p in tmp_path.iterdir()) == {
        "invocations.jsonl",
        "run_manifest.json",
    }
