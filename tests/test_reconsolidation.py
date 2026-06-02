import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from mycelium.reconsolidation import ReconsolidationEngine
from mycelium.models import WikiPage, PredictionError
from mycelium.config import Config

@pytest.fixture
def mock_llm():
    return AsyncMock()

@pytest.fixture
def mock_wiki():
    return MagicMock()

@pytest.fixture
def engine(mock_llm, mock_wiki):
    return ReconsolidationEngine(mock_llm, mock_wiki, Config.defaults())

@pytest.fixture
def sample_page():
    return WikiPage(
        slug="test-page",
        title="Test Page",
        content="Old belief",
        created=datetime.now(),
        last_updated=datetime.now(),
        version=1,
        confidence=0.9,
        importance=0.5
    )

@pytest.mark.asyncio
async def test_check(engine, mock_llm, sample_page):
    mock_llm.call_structured.return_value = {
        "conflict_type": "partial",
        "discrepancy_score": 0.45,
        "explanation": "Context says something new.",
        "suggested_update": "Add new thing."
    }
    
    error = await engine.check(sample_page, "New context")
    
    assert error.conflict_type == "partial"
    assert error.discrepancy_score == 0.45
    assert error.explanation == "Context says something new."
    assert error.suggested_update == "Add new thing."
    mock_llm.call_structured.assert_called_once()

@pytest.mark.asyncio
async def test_flag_and_accumulate(engine, mock_wiki, sample_page):
    await engine.flag_labile(sample_page, "ses-123")
    mock_wiki.mark_labile.assert_called_once_with("test-page", "ses-123")
    
    error = PredictionError("partial", 0.45, "expl", "sugg")
    await engine.accumulate_signal("test-page", "ses-123", error)
    
    assert engine._signals[("test-page", "ses-123")] == [error]

@pytest.mark.asyncio
async def test_resolve_labile_pages(engine, mock_llm, mock_wiki, sample_page):
    # Setup state
    error = PredictionError("partial", 0.45, "expl", "sugg")
    engine._signals[("test-page", "ses-123")] = [error]
    mock_wiki.exists.return_value = True
    mock_wiki.get.return_value = sample_page
    
    mock_llm.call_structured.return_value = {
        "title": "New Title",
        "content": "New belief",
        "tags": ["new"],
        "confidence": 0.95,
        "importance": 0.6,
        "update_reason": "Updated due to new context"
    }
    
    resolved = await engine.resolve_labile_pages("ses-123")
    
    assert resolved == ["test-page"]
    assert sample_page.title == "New Title"
    assert sample_page.content == "New belief"
    assert sample_page.version == 2
    assert len(sample_page.update_log) == 1
    assert sample_page.update_log[0].reason == "Updated due to new context"
    
    mock_wiki.save.assert_called_once_with(sample_page)
    mock_wiki.resolve_labile.assert_called_once_with("test-page", "ses-123")
    assert ("test-page", "ses-123") not in engine._signals
