import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from mycelium.config import Config
from mycelium.decay import (
    DecayEngine,
    compute_retrievability,
    record_memory_event,
    should_archive,
)
from mycelium.models import WikiPage


def make_page(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "slug": "test-page",
        "title": "Test Page",
        "content": "",
        "created": now,
        "last_updated": now,
        "version": 1,
        "confidence": 0.8,
        "importance": 0.5,
    }
    values.update(overrides)
    return WikiPage(**values)


def test_compute_retrievability_uses_elapsed_days_and_stability():
    now = datetime.now(timezone.utc)
    reviewed = now - timedelta(days=14)

    normal = compute_retrievability(14.0, reviewed, reviewed, now=now)
    stable = compute_retrievability(28.0, reviewed, reviewed, now=now)

    assert normal == pytest.approx(0.367879, rel=1e-4)
    assert stable > normal


def test_record_memory_event_retrieved_updates_access_state():
    now = datetime.now(timezone.utc)
    page = make_page(created=now - timedelta(days=10), last_reviewed=now - timedelta(days=10))

    record_memory_event(page, "retrieved", now=now)

    assert page.last_accessed == now
    assert page.review_count == 1
    assert page.retrievability <= 1.0


def test_record_memory_event_used_reinforces_memory():
    now = datetime.now(timezone.utc)
    page = make_page(
        created=now - timedelta(days=10),
        last_reviewed=now - timedelta(days=10),
        stability_days=10.0,
        difficulty=0.5,
    )

    record_memory_event(page, "used", now=now)

    assert page.last_accessed == now
    assert page.last_reviewed == now
    assert page.reinforced_count == 1
    assert page.stability_days > 10.0
    assert page.difficulty < 0.5
    assert page.retrievability == 1.0


def test_record_memory_event_contradicted_increases_volatility():
    now = datetime.now(timezone.utc)
    page = make_page(stability_days=20.0, difficulty=0.4)

    record_memory_event(page, "contradicted", now=now)

    assert page.conflict_count == 1
    assert page.stability_days < 20.0
    assert page.difficulty > 0.4


def test_should_archive_requires_multiple_low_signals():
    now = datetime.now(timezone.utc)
    stale = make_page(
        created=now - timedelta(days=120),
        confidence=0.4,
        importance=0.1,
        retrievability=0.05,
        last_accessed=now - timedelta(days=60),
    )
    pinned = make_page(
        created=now - timedelta(days=120),
        confidence=0.4,
        importance=0.1,
        retrievability=0.05,
        pinned=True,
    )
    important = make_page(
        created=now - timedelta(days=120),
        confidence=0.4,
        importance=0.9,
        retrievability=0.05,
        last_accessed=now - timedelta(days=60),
    )

    assert should_archive(stale, now=now)
    assert not should_archive(pinned, now=now)
    assert not should_archive(important, now=now)


@pytest.mark.asyncio
async def test_decay_engine_run_pass_refreshes_or_archives():
    now = datetime.now(timezone.utc)
    mock_wiki = MagicMock()
    mock_logs = MagicMock()

    keep = make_page(slug="keep", created=now, last_reviewed=now, importance=1.0, confidence=1.0)
    archive = make_page(
        slug="archive",
        created=now - timedelta(days=365),
        last_reviewed=now - timedelta(days=365),
        last_accessed=now - timedelta(days=90),
        stability_days=1.0,
        importance=0.0,
        confidence=0.3,
    )

    mock_wiki.list_all.return_value = [keep, archive]

    engine = DecayEngine(mock_wiki, mock_logs, Config.defaults())
    changed = await engine.run_pass(now=now)

    assert set(changed) == {"archive"}
    mock_wiki.save.assert_called_once_with(keep)
    mock_wiki.archive.assert_called_once_with("archive")
