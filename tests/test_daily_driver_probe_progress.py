import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from benchmarks.suites.daily_driver import run as daily
from benchmarks.suites.daily_driver.eval import evaluate_run
from benchmarks.suites.daily_driver.fixture import load_fixture
from mycelium.config import Config
from mycelium.operations import MemoryEvidence, RetrievalResult
from tests.test_daily_driver_fixture import FIXTURE_DIR


def fixture():
    value = load_fixture(FIXTURE_DIR)
    value["probes"]["probes"] = [
        {"id": key, "checkpoint": "cp", "question": key, "required_facts": [], "forbidden_facts": [],
         "expected_answer": "Reference only", "evaluation_mode": "artifact" if key == "artifact" else "qa"}
        for key in ["first", "second", "artifact"]
    ]
    return value


def memory(tmp_path):
    return SimpleNamespace(config=Config.defaults(), store_path=tmp_path / "store",
        retrieve_context=AsyncMock(return_value=RetrievalResult((), MemoryEvidence(), "")), llm=object())


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", ["retrieval", "answer", "judgment"])
async def test_each_probe_retains_partial_results_and_later_probes_continue(tmp_path, monkeypatch, failed_stage):
    mem, data, result_path = memory(tmp_path), fixture(), tmp_path / "probes.json"

    async def retrieve(request):
        if request.query == "first" and failed_stage == "retrieval":
            raise RuntimeError("injected retrieval failure")
        return RetrievalResult((), MemoryEvidence(), "")

    async def answer(_self, question, context):
        if question == "first" and failed_stage == "answer":
            raise RuntimeError("injected answer failure")
        return SimpleNamespace(output="Observed answer", metadata={}, query_time_len=0.1)

    async def judge(**kwargs):
        saved = json.loads(result_path.read_text())[-1]
        assert saved["stage"] == "judgment" and saved["answer"] == "Observed answer"
        if kwargs["probe"]["id"] == "first" and failed_stage == "judgment":
            raise RuntimeError("injected judgment failure")
        return {"passed": True}

    mem.retrieve_context.side_effect = retrieve
    monkeypatch.setattr(daily.OllamaQaClient, "answer", answer)
    monkeypatch.setattr(daily, "judge_probe_answer", judge)
    rows = await daily._run_checkpoint_probes(data, mem, "cp", {"counts": {"pages": 1}, "pages": []},
                                             run_answers=True, result_path=result_path)
    assert json.loads(result_path.read_text()) == rows
    assert rows[0]["status"] == "failed" and rows[0]["failure_stage"] == failed_stage
    assert rows[1]["status"] == "complete" and rows[1]["judgment"]["passed"]
    assert rows[2]["artifact_observation"]["counts"] == {"pages": 1}
    assert rows[2]["answer"] is None and rows[2]["judgment"] is None
    assert mem.retrieve_context.await_count == 2
    if failed_stage == "judgment":
        assert rows[0]["answer"] == "Observed answer" and rows[0]["retrieval_status"] == "complete"


@pytest.mark.asyncio
async def test_probe_cancellation_is_recorded_and_propagated(tmp_path, monkeypatch):
    mem, result_path = memory(tmp_path), tmp_path / "probes.json"
    mem.retrieve_context.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await daily._run_checkpoint_probes(fixture(), mem, "cp", {"counts": {}},
                                           run_answers=True, result_path=result_path)
    rows = json.loads(result_path.read_text())
    assert len(rows) == 1 and rows[0]["status"] == "failed"
    assert rows[0]["failure_stage"] == "retrieval"
    assert rows[0]["error"].startswith("CancelledError:")


def test_artifact_references_do_not_inflate_qa_and_failed_reads_do_not_pass_retraction():
    data = fixture()
    data["probes"]["probes"][0]["forbidden_facts"] = ["f-northstar-acquisition"]
    rows = [
        {"probe_id": "first", "retrieval_status": "failed", "status": "failed", "judgment": None},
        {"probe_id": "second", "retrieval_status": "complete", "status": "complete", "judgment": {"passed": True}},
        {"probe_id": "artifact", "status": "complete", "judgment": {"passed": True}},
    ]
    result = evaluate_run(data, {}, rows)
    metrics = {row["id"]: row for row in result["dimensions"]}
    assert metrics["semantic_answer_quality"]["denominator"] == 2
    assert metrics["semantic_answer_quality"]["numerator"] == 1
    assert not metrics["semantic_answer_quality"]["evaluated"]
    assert not metrics["retrieval_fact_recall"]["evaluated"]
    assert not metrics["retraction_completeness"]["evaluated"]


@pytest.mark.asyncio
async def test_failed_probe_makes_run_incomplete_without_counting_artifact_as_qa(tmp_path, monkeypatch):
    data = fixture()
    data["scenario"]["episodes"] = [{"id": "episode", "actions_after": ["checkpoint:cp"]}]
    results = [
        {"probe_id": "first", "evaluation_mode": "qa", "status": "failed", "failure_stage": "retrieval",
         "error": "Injected failure", "judgment": None},
        {"probe_id": "second", "evaluation_mode": "qa", "status": "complete", "judgment": {"passed": True}},
        {"probe_id": "artifact", "evaluation_mode": "artifact", "status": "complete", "judgment": None},
    ]
    original = daily.Mycelium

    def create_memory(*args, **kwargs):
        mem = original(*args, **kwargs)
        mem.llm.client.list = AsyncMock(return_value=SimpleNamespace(model_dump=lambda: {"models": []}))
        return mem

    monkeypatch.setattr(daily, "Mycelium", create_memory)
    monkeypatch.setattr(daily, "load_fixture", lambda _: copy.deepcopy(data))
    monkeypatch.setattr(daily, "validate_fixture", lambda _: None)
    monkeypatch.setattr(daily, "_ingest_episode", AsyncMock())
    monkeypatch.setattr(daily, "_run_checkpoint_probes", AsyncMock(return_value=results))
    monkeypatch.setattr(daily, "compare_final", lambda *_: {})
    monkeypatch.setattr(daily, "evaluate_run", lambda *_: {})
    monkeypatch.setattr(daily, "_report_markdown", lambda *_: "")
    output = tmp_path / "run"
    await daily.run_daily_driver(tmp_path, output)
    manifest = json.loads((output / "run_manifest.json").read_text())
    frozen = json.loads((output / "fixture.json").read_text())
    assert manifest["fixture_sha256"] == daily.digest(frozen) == daily.digest(data)
    assert manifest["probe_judgment"] == daily.probe_judgment_specification()
    assert manifest["qa_status"] == "incomplete"
    assert manifest["execution_status"] == "complete_with_errors"
    assert manifest["encoding_status"] == "complete"
    assert manifest["qa_expected_probes"] == 2 and manifest["qa_completed_probes"] == 1
    assert manifest["action_errors"][0]["probe_errors"][0]["probe_id"] == "first"
