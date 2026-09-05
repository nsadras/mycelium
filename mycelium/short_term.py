"""Policy and inspection for durable, unconsolidated memory claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from mycelium.artifacts import ArtifactStore, MemoryClaim


@dataclass(frozen=True)
class ShortTermMemoryStatus:
    pending_claims: int
    deferred_claims: int
    retryable_failures: int
    total_claims: int
    pending_sources: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


class ShortTermMemoryQueue:
    """Expose queue state and decide when the single Dream pipeline is due."""

    def __init__(self, artifacts: ArtifactStore):
        self.artifacts = artifacts

    def status(self) -> ShortTermMemoryStatus:
        claims = self.artifacts.list_short_term_claims(include_deferred=True)
        return ShortTermMemoryStatus(
            pending_claims=sum(c.dream_disposition == "pending" for c in claims),
            deferred_claims=sum(c.dream_disposition == "deferred" for c in claims),
            retryable_failures=sum(
                c.dream_disposition == "routing_failed" for c in claims
            ),
            total_claims=len(claims),
            pending_sources=sum(
                e.extraction_status != "complete"
                for e in self.artifacts.list_episodes()
            ),
        )

    def claims_for_dream(self, *, include_deferred: bool) -> list[MemoryClaim]:
        claims = self.artifacts.list_short_term_claims(include_deferred=True)
        if include_deferred:
            return claims
        return [
            claim
            for claim in claims
            if claim.dream_disposition in {"pending", "routing_failed"}
        ]
