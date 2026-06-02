from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Literal

from mycelium.models import WikiPage

MemoryEvent = Literal[
    "retrieved",
    "used",
    "dream_created",
    "dream_updated",
    "contradicted",
    "manually_edited",
]


MIN_STABILITY_DAYS = 1.0
MAX_STABILITY_DAYS = 3650.0
MIN_DIFFICULTY = 0.0
MAX_DIFFICULTY = 1.0


def _aware(dt: datetime | None, fallback: datetime) -> datetime:
    value = dt or fallback
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_retrievability(
    stability_days: float,
    last_reviewed: datetime | None,
    created: datetime,
    now: datetime | None = None,
) -> float:
    """MemoryBank-style retrievability: R = exp(-elapsed_days / stability)."""
    now = _aware(now, datetime.now(timezone.utc))
    anchor = _aware(last_reviewed or created, now)
    elapsed_days = max(0.0, (now - anchor).total_seconds() / 86400.0)
    stability = max(MIN_STABILITY_DAYS, stability_days)
    return _clamp(math.exp(-elapsed_days / stability), 0.0, 1.0)


def refresh_retrievability(page: WikiPage, now: datetime | None = None) -> float:
    page.retrievability = compute_retrievability(
        page.stability_days,
        page.last_reviewed,
        page.created,
        now=now,
    )
    return page.retrievability


def initialize_memory_state(
    page: WikiPage,
    event_type: Literal["dream_created", "manual_created"] = "dream_created",
    now: datetime | None = None,
) -> WikiPage:
    now = _aware(now, datetime.now(timezone.utc))
    page.stability_days = 30.0 if event_type == "dream_created" else 45.0
    page.difficulty = 0.30 if event_type == "dream_created" else 0.25
    page.retrievability = 1.0
    page.last_accessed = now
    page.last_reviewed = now
    page.review_count = 0
    page.reinforced_count = 1
    page.conflict_count = 0
    return page


def record_memory_event(
    page: WikiPage,
    event_type: MemoryEvent,
    now: datetime | None = None,
) -> WikiPage:
    now = _aware(now, datetime.now(timezone.utc))
    refresh_retrievability(page, now=now)
    difficulty_factor = 1.0 - _clamp(page.difficulty, MIN_DIFFICULTY, MAX_DIFFICULTY)
    importance_factor = 0.5 + _clamp(page.importance, 0.0, 1.0)

    if event_type == "retrieved":
        page.last_accessed = now
        page.review_count += 1
        page.stability_days += 0.25 * importance_factor * (0.5 + difficulty_factor)
    elif event_type == "used":
        page.last_accessed = now
        page.last_reviewed = now
        page.review_count += 1
        page.reinforced_count += 1
        page.stability_days *= 1.10 + (0.20 * importance_factor * (0.5 + difficulty_factor))
        page.difficulty -= 0.03
    elif event_type == "dream_created":
        initialize_memory_state(page, "dream_created", now=now)
    elif event_type == "dream_updated":
        page.last_reviewed = now
        page.reinforced_count += 1
        page.stability_days *= 1.15 + (0.15 * importance_factor * (0.5 + difficulty_factor))
        page.difficulty -= 0.04
    elif event_type == "contradicted":
        page.last_accessed = now
        page.conflict_count += 1
        page.difficulty += 0.15
        page.stability_days *= 0.85
    elif event_type == "manually_edited":
        page.last_reviewed = now
        page.last_accessed = now
        page.reinforced_count += 1
        page.stability_days = max(page.stability_days, 45.0)
        page.difficulty -= 0.10

    page.stability_days = _clamp(page.stability_days, MIN_STABILITY_DAYS, MAX_STABILITY_DAYS)
    page.difficulty = _clamp(page.difficulty, MIN_DIFFICULTY, MAX_DIFFICULTY)
    refresh_retrievability(page, now=now)
    return page


def should_archive(page: WikiPage, now: datetime | None = None) -> bool:
    if page.pinned:
        return False

    now = _aware(now, datetime.now(timezone.utc))
    last_accessed = _aware(page.last_accessed, page.created)
    recently_accessed = now - last_accessed < timedelta(days=30)
    return (
        page.retrievability < 0.15
        and page.importance < 0.4
        and page.confidence < 0.6
        and not recently_accessed
    )


class DecayEngine:
    def __init__(self, wiki, logs, config):
        self.wiki = wiki
        self.logs = logs
        self.config = config

    async def run_pass(self, now: datetime | None = None) -> dict[str, float]:
        now = _aware(now, datetime.now(timezone.utc))
        changed_scores = {}

        for page in self.wiki.list_all():
            old_retrievability = page.retrievability
            new_retrievability = refresh_retrievability(page, now=now)
            if new_retrievability != old_retrievability:
                changed_scores[page.slug] = new_retrievability

            if should_archive(page, now=now):
                self.wiki.archive(page.slug)
            else:
                self.wiki.save(page)

        return changed_scores
