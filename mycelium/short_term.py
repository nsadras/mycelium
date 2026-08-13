"""Policy and inspection for durable, unconsolidated memory claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from mycelium.artifacts import ArtifactStore, MemoryClaim
from mycelium.config import DreamConfig
from mycelium.lexical import terms


@dataclass(frozen=True)
class ShortTermMemoryStatus:
    pending_claims: int
    deferred_claims: int
    retryable_failures: int
    total_claims: int
    oldest_pending_at: str | None
    oldest_deferred_at: str | None
    ready: bool
    reasons: list[str] = field(default_factory=list)
    include_deferred: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


class ShortTermMemoryQueue:
    """Expose queue state and decide when the single Dream pipeline is due."""

    def __init__(self, artifacts: ArtifactStore, config: DreamConfig):
        self.artifacts = artifacts
        self.config = config

    def status(self, *, now: datetime | None = None) -> ShortTermMemoryStatus:
        current = _aware(now or datetime.now().astimezone())
        claims = self.artifacts.list_short_term_claims(include_deferred=True)
        pending = [claim for claim in claims if claim.dream_disposition == "pending"]
        deferred = [claim for claim in claims if claim.dream_disposition == "deferred"]
        failed = [claim for claim in claims if claim.dream_disposition == "routing_failed"]
        ready_claims = [*pending, *failed]

        oldest_pending = _oldest_recorded(ready_claims)
        oldest_deferred = _oldest_decision(deferred)
        reasons: list[str] = []
        if len(ready_claims) >= self.config.queue_claim_threshold:
            reasons.append("claim_threshold")
        if (
            oldest_pending is not None
            and current - oldest_pending >= timedelta(hours=self.config.max_pending_hours)
        ):
            reasons.append("max_pending_age")
        deferred_due = bool(
            oldest_deferred is not None
            and current - oldest_deferred
            >= timedelta(hours=self.config.deferred_revisit_hours)
        )
        if deferred_due:
            reasons.append("deferred_review_due")

        return ShortTermMemoryStatus(
            pending_claims=len(pending),
            deferred_claims=len(deferred),
            retryable_failures=len(failed),
            total_claims=len(claims),
            oldest_pending_at=oldest_pending.isoformat() if oldest_pending else None,
            oldest_deferred_at=oldest_deferred.isoformat() if oldest_deferred else None,
            ready=bool(reasons),
            reasons=reasons,
            include_deferred=deferred_due,
        )

    def claims_for_dream(self, *, include_deferred: bool) -> list[MemoryClaim]:
        claims = self.artifacts.list_short_term_claims(include_deferred=True)
        if include_deferred:
            return claims
        ready = [
            claim for claim in claims
            if claim.dream_disposition in {"pending", "routing_failed"}
        ]
        deferred = [
            claim for claim in claims if claim.dream_disposition == "deferred"
        ]
        ranked = sorted(
            (
                (max((_neighbor_score(claim, seed) for seed in ready), default=0), claim)
                for claim in deferred
            ),
            key=lambda item: (-item[0], item[1].recorded_at, item[1].claim_id),
        )
        related = [claim for score, claim in ranked if score > 0][:24]
        return [*ready, *related]


def _oldest_recorded(claims: list[MemoryClaim]) -> datetime | None:
    values = [_parse(claim.recorded_at) for claim in claims]
    return min((value for value in values if value is not None), default=None)


def _oldest_decision(claims: list[MemoryClaim]) -> datetime | None:
    values = [
        _parse(claim.dream_disposition_at) or _parse(claim.recorded_at)
        for claim in claims
    ]
    return min((value for value in values if value is not None), default=None)


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _aware(datetime.fromisoformat(value))
    except ValueError:
        return None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.astimezone()


def _neighbor_score(left: MemoryClaim, right: MemoryClaim) -> int:
    """Conservatively reopen deferred claims when new context is specific.

    A one-token subject such as a person's name is intentionally insufficient;
    otherwise every new fact about a person would reopen their entire backlog.
    """
    left_about = {
        frozenset(terms(str(value.get("entity") or "")))
        for value in left.about
        if value.get("entity")
    }
    right_about = {
        frozenset(terms(str(value.get("entity") or "")))
        for value in right.about
        if value.get("entity")
    }
    qualified_about = {
        value for value in left_about & right_about if len(value) >= 2
    }
    score = 4 if qualified_about else 0
    if left.slot and right.slot and left.slot == right.slot:
        score += 4
    if left.predicate and right.predicate and left.predicate == right.predicate:
        score += 3
    overlap = terms(left.text) & terms(right.text)
    if len(overlap) >= 2:
        score += min(3, len(overlap))
    return score
