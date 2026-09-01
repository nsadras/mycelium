"""Shared value objects for consolidation decisions."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mycelium.artifacts import (
    ClaimEntityReference,
    EntityEncounter,
    EntityRecord,
    EntityResolutionDecision,
    IdentityMaturityAssessment,
    MemoryClaim,
    SourceDocument,
)


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


@dataclass(frozen=True)
class ClaimEvidence:
    claim: MemoryClaim
    source: SourceDocument

    @property
    def raw_log_entry_id(self) -> str:
        return self.source.raw_log_entry_id or self.source.source_id


@dataclass(frozen=True)
class ClaimRoute:
    claim_id: str
    owner_entity_id: str | None
    section_key: str | None
    linked_entity_ids: tuple[str, ...]
    raw_log_entry_id: str
    reason: str
    disposition: str = "canonical"
    supporting_claim_ids: tuple[str, ...] = ()
    confidence: float = 0.8
    subject_entity_id: str | None = None
    object_entity_ids: tuple[str, ...] = ()
    contextual_entity_ids: tuple[str, ...] = ()
    relationship_kind: str | None = None
    identity_blocker_ids: tuple[str, ...] = ()

    @property
    def placed(self) -> bool:
        return self.disposition == "canonical" and bool(
            self.owner_entity_id
        )


@dataclass(frozen=True)
class RoutingFailure:
    claim_id: str
    raw_log_entry_id: str
    reason: str


@dataclass
class RoutingResult:
    routes: list[ClaimRoute] = field(default_factory=list)
    new_entities: list[EntityRecord] = field(default_factory=list)
    failures: list[RoutingFailure] = field(default_factory=list)
    encounters: list[EntityEncounter] = field(default_factory=list)
    entity_decisions: list[EntityResolutionDecision] = field(default_factory=list)
    maturity_assessments: list[IdentityMaturityAssessment] = field(default_factory=list)
    entity_references: list[ClaimEntityReference] = field(default_factory=list)
