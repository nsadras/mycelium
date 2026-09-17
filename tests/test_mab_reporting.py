import json
import time

import pytest

from benchmarks.suites.mab import MyceliumMABAgent, write_mab_results
from tests.test_benchmarks import FakeMemorySystem


@pytest.mark.asyncio
async def test_mab_reports_retrieval_in_seconds_and_accuracy_as_percent(tmp_path):
    answer = await MyceliumMABAgent(FakeMemorySystem()).answer("Question", 1, 1)
    assert answer["retrieval_seconds"] == 0.01
    assert "memory_construction_time" not in answer
    output = tmp_path / "results.json"
    summary = write_mab_results(
        output, {}, {"retrieval_seconds": [0.01, 0.03], "accuracy": [0.5, 1.0]},
        [answer], time.perf_counter(),
    )
    assert summary["averaged_metrics"] == {
        "retrieval_seconds": pytest.approx(0.02), "accuracy": 75.0,
    }
    assert json.loads(output.read_text())["data"] == [answer]
