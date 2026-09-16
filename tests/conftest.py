from pathlib import Path

from dotenv import load_dotenv
import pytest
from unittest.mock import AsyncMock

from mycelium.truth_review import TruthReviewResult


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


@pytest.fixture
def no_truth_changes(monkeypatch):
    """Isolate routing/presentation tests from separately tested truth decisions."""
    monkeypatch.setattr("mycelium.facts.TruthReviewer.review", AsyncMock(return_value=TruthReviewResult()))
