import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from benchmarks import __main__ as cli
from benchmarks.shared.semantic_scoring import ReferenceJudgment, SemanticScorer, summarize_judgments
from benchmarks.suites.locomo import run_locomo
from mycelium.config import LLMConfig
from tests.test_benchmarks import FakeMemorySystem


def test_reference_judgment_contract_is_scoped():
    ReferenceJudgment(verdict="partial", reason="Only one requested fact is present.")
    for payload in ({"verdict": "yes", "reason": "Match"},
                    {"verdict": "correct", "reason": ""},
                    {"verdict": "correct", "reason": "Match", "score": 1}):
        with pytest.raises(ValidationError):
            ReferenceJudgment.model_validate(payload)


def test_semantic_summary_does_not_treat_failed_or_ungradable_as_wrong():
    rows = [{"semantic_judgment": {"status": "complete", "judgment": {"verdict": verdict, "reason": "Test"}}}
            for verdict in ("correct", "partial", "incorrect", "ungradable")]
    rows += [{"semantic_judgment": {"status": "failed", "error": "timeout"}}, {}]
    result = summarize_judgments(rows, enabled=True)
    assert result["strict_accuracy"] == pytest.approx(1 / 3)
    assert result["grading_coverage"] == 0.5
    assert result["failed_questions"] == 1
    assert result["pending_questions"] == 1
    assert result["status"] == "incomplete"
    assert summarize_judgments(rows, enabled=False) == {"status": "disabled"}
    assert summarize_judgments([{}], enabled=True)["strict_accuracy"] is None
    assert summarize_judgments([], enabled=True)["status"] == "not_run"


@pytest.mark.asyncio
async def test_semantic_scorer_validates_model_output_and_preserves_input(tmp_path):
    scorer = SemanticScorer(LLMConfig(reasoning_enabled=False), tmp_path / "calls.jsonl")
    scorer.llm.call_structured = AsyncMock(return_value={"verdict": "correct", "reason": "Equivalent meaning."})
    result = await scorer.judge(question="Question", reference="Reference; explanation",
                                prediction="Prediction", answerable=True)
    assert result["verdict"] == "correct"
    call = scorer.llm.call_structured.call_args
    assert json.loads(call.args[1])["reference_answer"] == "Reference; explanation"
    assert call.kwargs["num_predict"] == 512
    scorer.llm.call_structured.return_value = {"verdict": "invalid", "reason": "Unsupported"}
    with pytest.raises(ValidationError):
        await scorer.judge(question="Q", reference="R", prediction="P", answerable=True)


class FakeScorer:
    specification = {"version": "test-v1", "digest": "test"}

    def __init__(self):
        self.judge = AsyncMock(return_value={"verdict": "correct", "reason": "Test judgment"})


@pytest.mark.asyncio
async def test_scoring_failure_preserves_answers_and_resumes_only_missing_judgments(tmp_path):
    output = tmp_path / "run"
    scorer = FakeScorer()
    scorer.judge.side_effect = TimeoutError("scorer unavailable")
    system = FakeMemorySystem()
    system.answer = AsyncMock(wraps=system.answer)
    args = dict(data_path=Path("tests/fixtures/locomo_tiny.json"), output_dir=output,
                system=system, prediction_key="test", semantic_scorer=scorer)
    first = await run_locomo(**args)
    manifest = json.loads((output / "run_manifest.json").read_text())
    assert manifest["execution_status"] == "complete"
    assert manifest["qa_status"] == "complete"
    assert manifest["scoring_status"] == "incomplete"
    assert first["semantic_scoring"]["strict_accuracy"] is None
    answered = system.answer.await_count
    rows = [json.loads(p.read_text()) for p in (output / "questions").glob("*.json")]
    assert all(row["prediction"] and row["semantic_judgment"]["status"] == "failed" for row in rows)
    scorer.judge.side_effect = None
    second = await run_locomo(**args)
    assert system.answer.await_count == answered
    assert second["semantic_scoring"]["strict_accuracy"] == 1
    assert second["semantic_scoring"]["status"] == "complete"
    scored = scorer.judge.await_count
    third = await run_locomo(**args)
    assert third["semantic_scoring"] == second["semantic_scoring"]
    assert scorer.judge.await_count == scored
    assert first["mean_score"] == second["mean_score"]
    requests = [call.kwargs for call in scorer.judge.call_args_list]
    assert all("answerable" in request and "reference" in request for request in requests)
    scorer.specification = {"version": "changed", "digest": "changed"}
    before = (output / "invocations.jsonl").read_bytes()
    with pytest.raises(ValueError, match="settings differ"):
        await run_locomo(**args)
    assert (output / "invocations.jsonl").read_bytes() == before


def test_semantic_scoring_cli_uses_captured_qa_configuration(tmp_path, monkeypatch):
    runner = AsyncMock(return_value={})
    monkeypatch.setattr(cli, "run_locomo", runner)
    cli.main(["locomo", "--system", "null", "--semantic-scoring", "--qa-model", "judge-model",
              "--output-root", str(tmp_path)])
    scorer = runner.call_args.kwargs["semantic_scorer"]
    assert scorer.specification["config"]["model"] == "judge-model"
    assert scorer.llm.model == "judge-model"


@pytest.mark.asyncio
async def test_interrupted_scoring_resumes_without_repeating_successful_work(tmp_path):
    samples = json.loads(Path("tests/fixtures/locomo_tiny.json").read_text())
    samples[0]["qa"] *= 2
    dataset = tmp_path / "input.json"
    dataset.write_text(json.dumps(samples))
    output = tmp_path / "run"
    scorer = FakeScorer()
    scorer.judge.side_effect = [
        {"verdict": "correct", "reason": "Test judgment"}, asyncio.CancelledError(),
    ]
    system = FakeMemorySystem()
    system.answer = AsyncMock(wraps=system.answer)
    args = dict(data_path=dataset, output_dir=output, system=system,
                prediction_key="test", semantic_scorer=scorer)
    with pytest.raises(asyncio.CancelledError):
        await run_locomo(**args)
    rows = [json.loads(p.read_text()) for p in (output / "questions").glob("*.json")]
    assert sorted(row["semantic_judgment"]["status"] for row in rows) == ["complete", "running"]
    assert all(row["prediction"] == "Pixel" for row in rows)
    scorer.judge.side_effect = None
    result = await run_locomo(**args)
    assert system.answer.await_count == 2
    assert scorer.judge.await_count == 3
    assert result["semantic_scoring"]["status"] == "complete"


@pytest.mark.asyncio
async def test_scorer_trace_and_model_provenance_are_separate_from_qa(tmp_path, monkeypatch):
    import httpx
    from types import SimpleNamespace
    from benchmarks.shared.adapters import OllamaQaClient
    from benchmarks.shared.provenance import model_inventory
    from mycelium.telemetry import trace_metadata

    async def get(self, url):
        return httpx.Response(200, request=httpx.Request("GET", url), json={"models": [
            {"name": "qa:latest", "digest": "qa-digest"}, {"name": "judge:latest", "digest": "judge-digest"},
        ]})
    monkeypatch.setattr(httpx.AsyncClient, "get", get)
    scorer = SemanticScorer(LLMConfig(model="judge"), tmp_path / "scoring.jsonl")
    qa = OllamaQaClient(model="qa", url="http://localhost:11434")
    inventory = await model_inventory(SimpleNamespace(qa_client=qa), semantic_scorer=scorer)
    assert inventory["qa"]["digest"] == "qa-digest"
    assert inventory["scoring"]["digest"] == "judge-digest"
    traces = []

    async def structured(*args, **kwargs):
        traces.append(trace_metadata())
        return {"verdict": "correct", "reason": "Test judgment"}

    scorer.llm.call_structured = structured
    output = tmp_path / "run"
    await run_locomo(data_path=Path("tests/fixtures/locomo_tiny.json"), output_dir=output,
                     system=FakeMemorySystem(), prediction_key="test", semantic_scorer=scorer)
    row = json.loads(next((output / "questions").glob("*.json")).read_text())
    assert traces == [row["semantic_judgment"]["trace"]]
    assert traces[0]["query_id"] == "tiny-1-q0"
    assert traces[0]["invocation_id"] == row["metadata"]["trace"]["invocation_id"]
    assert traces[0]["operation_id"] != row["metadata"]["trace"]["operation_id"]
