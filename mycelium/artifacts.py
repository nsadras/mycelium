"""Durable source, episode, and claim artifacts for the memory pipeline.

The JSON representation is intentionally boring and inspectable.  Raw source text is
never replaced by an LLM summary; claims point back to exact source segment ids.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, cast


CLAIM_TYPES = {
    "identity", "state", "event", "preference", "plan", "belief",
    "relationship", "decision", "commitment", "interaction", "observation",
    "unknown",
}
NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
EVIDENCE_MODALITIES = {"speech", "visual", "tool", "inference", "mixed", "unknown"}
TEMPORAL_STATUSES = {"past", "current", "future", "recurring", "atemporal", "unknown"}
DREAM_DISPOSITIONS = {
    "pending",
    "deferred",
    "routed",
    "excluded_source_policy",
    "routing_failed",
}
SHORT_TERM_DISPOSITIONS = {"pending", "deferred", "routing_failed"}
NON_WIKI_RETENTION_REASONS = {
    "assistant_unadopted",
    "system_control",
    "extractor_rejected",
}
ENTITY_REFERENCE_ROLES = {"subject", "object", "context", "canonical_owner"}
RECONSOLIDATION_RELATIONS = {"contradicts", "supersedes"}
RECONSOLIDATION_STATUSES = {"pending", "approved", "rejected", "applied", "stale"}

def _normalized_label(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


@dataclass
class SourceSegment:
    segment_id: str
    index: int
    content: str
    speaker: str | None = None
    role: str | None = None
    timestamp: str | None = None
    start_seconds: float | None = None
    end_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceDocument:
    source_id: str
    source_type: str
    session_id: str
    recorded_at: str
    occurred_at: str | None
    participants: list[str]
    segments: list[SourceSegment]
    raw_log_entry_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClaimProvenance:
    source_id: str
    segment_ids: list[str]
    raw_log_entry_id: str | None = None
    speaker: str | None = None
    evidence_type: str = "explicit"


@dataclass
class MemoryClaim:
    claim_id: str
    text: str
    kind: str
    about: list[dict[str, str]]
    provenance: list[ClaimProvenance]
    recorded_at: str
    status: str = "active"
    confidence: float = 0.8
    inferred: bool = False
    slot: str | None = None
    facets: dict[str, Any] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)
    salience: float = 0.5
    claim_type: str = "unknown"
    predicate: str | None = None
    evidence_modality: str = "unknown"
    temporal_status: str = "unknown"
    dream_disposition: str = "pending"
    dream_disposition_reason: str | None = None
    dream_run_id: str | None = None
    dream_disposition_at: str | None = None

    def __post_init__(self) -> None:
        """Normalize the compact semantic envelope without inferring it from prose or labels."""
        normalized_type = _normalized_label(self.claim_type)
        if normalized_type not in CLAIM_TYPES:
            normalized_type = "unknown"
        self.claim_type = normalized_type

        modality = _normalized_label(self.evidence_modality)
        if self.inferred:
            modality = "inference"
        elif modality not in EVIDENCE_MODALITIES:
            modality = "unknown"
        self.evidence_modality = modality

        temporal = _normalized_label(self.temporal_status)
        if temporal not in TEMPORAL_STATUSES:
            temporal = "unknown"
        self.temporal_status = temporal

        if self.predicate is not None:
            self.predicate = " ".join(str(self.predicate).split()).strip() or None

        disposition = str(self.dream_disposition or "pending").strip().lower()
        self.dream_disposition = (
            disposition if disposition in DREAM_DISPOSITIONS else "pending"
        )


@dataclass
class DreamClaimDecision:
    claim_id: str
    evidence_id: str
    source_id: str
    raw_log_entry_id: str | None
    disposition: str
    reason: str
    page_slugs: list[str] = field(default_factory=list)


@dataclass
class EntityRecord:
    entity_id: str
    entity_type: str
    title: str
    slug: str
    aliases: list[str]
    status: str
    created_at: str
    updated_at: str
    materialization_state: str = "materialized"
    merged_into_entity_id: str | None = None

    def __post_init__(self) -> None:
        from mycelium.models import PAGE_TYPES

        if self.entity_type not in PAGE_TYPES:
            raise ValueError(f"Unsupported entity type: {self.entity_type}")
        if self.status not in {"active", "archived", "merged"}:
            raise ValueError(f"Unsupported entity status: {self.status}")
        if self.materialization_state not in {"provisional", "materialized"}:
            raise ValueError(
                f"Unsupported entity materialization state: {self.materialization_state}"
            )
        if self.entity_id == "you" and self.entity_type != "you":
            raise ValueError("The singleton you entity must have type 'you'")
        if self.entity_type == "you" and self.entity_id != "you":
            raise ValueError("Only the singleton entity ID 'you' may use type 'you'")
        if self.status == "merged" and not self.merged_into_entity_id:
            raise ValueError("Merged entities require merged_into_entity_id")
        if self.status != "merged" and self.merged_into_entity_id:
            raise ValueError("Only merged entities may redirect")
        self.title = " ".join(self.title.split()).strip()
        self.slug = _slugify(self.slug)
        if not self.title or not self.slug:
            raise ValueError("Entity title and slug are required")
        self.aliases = sorted({" ".join(value.split()).strip() for value in self.aliases if value.strip()})


@dataclass
class NonWikiRetentionRecord:
    """Typed evidence retention outside short-term and canonical wiki memory."""

    retention_id: str
    target_type: str
    source_id: str
    segment_ids: list[str]
    reason: str
    policy_origin: str
    created_at: str
    claim_id: str | None = None

    def __post_init__(self) -> None:
        if self.target_type not in {"claim", "segment"}:
            raise ValueError(f"Unsupported retention target: {self.target_type}")
        if self.reason not in NON_WIKI_RETENTION_REASONS:
            raise ValueError(f"Unsupported non-wiki retention reason: {self.reason}")
        if self.policy_origin not in {"source_structure", "extraction"}:
            raise ValueError(f"Unsupported retention policy origin: {self.policy_origin}")
        if self.target_type == "claim" and not self.claim_id:
            raise ValueError("Claim retention records require claim_id")
        if self.target_type == "segment" and self.claim_id:
            raise ValueError("Segment retention records cannot name a claim")
        self.segment_ids = sorted(set(self.segment_ids))
        if not self.segment_ids:
            raise ValueError("Non-wiki retention records require source segments")


@dataclass
class ClaimEntityReference:
    """A structured claim mention or canonical scope endpoint."""

    reference_id: str
    claim_id: str
    role: str
    surface: str | None
    entity_id: str | None
    confidence: float
    reason: str
    origin: str
    dream_run_id: str
    status: str
    created_at: str
    superseded_by_reference_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ENTITY_REFERENCE_ROLES:
            raise ValueError(f"Unsupported entity-reference role: {self.role}")
        if self.origin not in {"extraction", "scope", "manual"}:
            raise ValueError(f"Unsupported entity-reference origin: {self.origin}")
        if self.status not in {"active", "superseded"}:
            raise ValueError(f"Unsupported entity-reference status: {self.status}")
        if self.status == "superseded" and not self.superseded_by_reference_id:
            raise ValueError("Superseded references require a successor")
        self.surface = " ".join(str(self.surface or "").split()).strip() or None
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class EntityResolutionDecision:
    """Append-only identity scope or participant-resolution evidence."""

    decision_id: str
    decision_type: str
    entity_id: str | None
    proposed_entity_type: str
    proposed_title: str
    source_ids: list[str]
    supporting_claim_ids: list[str]
    supporting_segment_ids: list[str]
    confidence: float
    reason: str
    review_state: str
    dream_run_id: str
    created_at: str
    participant_surface: str | None = None

    def __post_init__(self) -> None:
        if self.decision_type not in {"entity_creation", "participant_resolution"}:
            raise ValueError(f"Unsupported entity-resolution decision: {self.decision_type}")
        if self.review_state not in {"accepted", "review_required", "rejected"}:
            raise ValueError(f"Unsupported identity review state: {self.review_state}")
        self.source_ids = sorted(set(self.source_ids))
        self.supporting_claim_ids = sorted(set(self.supporting_claim_ids))
        self.supporting_segment_ids = sorted(set(self.supporting_segment_ids))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class ScopeCohort:
    """Persisted, non-lexical evidence neighborhood used for scope revision."""

    cohort_id: str
    dream_run_id: str
    claim_ids: list[str]
    source_ids: list[str]
    revision_entity_ids: list[str]
    created_at: str

    def __post_init__(self) -> None:
        self.claim_ids = sorted(set(self.claim_ids))
        self.source_ids = sorted(set(self.source_ids))
        self.revision_entity_ids = sorted(set(self.revision_entity_ids))


@dataclass
class ClaimPlacement:
    claim_id: str
    owner_entity_id: str | None
    section_key: str | None
    linked_entity_ids: list[str]
    status: str
    reason: str
    created_at: str
    updated_at: str
    relationship_kind: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"placed", "deferred"}:
            raise ValueError(f"Unsupported placement status: {self.status}")
        if self.status == "placed" and (not self.owner_entity_id or not self.section_key):
            raise ValueError("Placed claims require an owner and section")
        if self.status == "deferred" and (self.owner_entity_id or self.section_key):
            raise ValueError("Deferred claims cannot name an owner or section")
        if self.relationship_kind not in {None, "project_role", "other"}:
            raise ValueError(
                f"Unsupported placement relationship: {self.relationship_kind}"
            )
        self.linked_entity_ids = sorted({
            value for value in self.linked_entity_ids
            if value and value != self.owner_entity_id
        })


@dataclass
class ClaimScopeDecision:
    """Append-only explanation for one claim's current or proposed wiki scope."""

    decision_id: str
    claim_id: str
    owner_entity_id: str | None
    section_key: str | None
    linked_entity_ids: list[str]
    supporting_claim_ids: list[str]
    confidence: float
    reason: str
    origin: str
    dream_run_id: str | None
    status: str
    created_at: str
    superseded_by_decision_id: str | None = None

    def __post_init__(self) -> None:
        if self.origin not in {"automatic", "manual", "review"}:
            raise ValueError(f"Unsupported scope-decision origin: {self.origin}")
        if self.status not in {"active", "superseded", "proposed", "rejected"}:
            raise ValueError(f"Unsupported scope-decision status: {self.status}")
        if self.status == "superseded" and not self.superseded_by_decision_id:
            raise ValueError("Superseded scope decisions require a successor")
        self.linked_entity_ids = sorted(set(self.linked_entity_ids))
        self.supporting_claim_ids = sorted(set(self.supporting_claim_ids))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class EntityEncounter:
    """Source-grounded evidence that a Person participated in an episode."""

    encounter_id: str
    entity_id: str
    source_id: str
    raw_log_entry_id: str | None
    occurred_at: str | None
    title: str | None
    created_at: str


@dataclass
class ConsolidatedFact:
    """A stable, editable wiki statement grounded in one or more source claims."""

    fact_id: str
    text: str
    member_claim_ids: list[str]
    owner_entity_id: str
    section_key: str
    linked_entity_ids: list[str]
    synthesis_origin: str
    confidence: float
    reason: str
    created_at: str
    updated_at: str
    manual_text: bool = False

    def __post_init__(self) -> None:
        if self.synthesis_origin not in {"claim", "model", "manual"}:
            raise ValueError(
                f"Unsupported consolidated-fact origin: {self.synthesis_origin}"
            )
        self.text = " ".join(self.text.split()).strip()
        if not self.text:
            raise ValueError("Consolidated facts require display text")
        self.member_claim_ids = sorted(set(self.member_claim_ids))
        if not self.member_claim_ids:
            raise ValueError("Consolidated facts require at least one member claim")
        self.linked_entity_ids = sorted({
            value for value in self.linked_entity_ids
            if value and value != self.owner_entity_id
        })
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class OrganizationProposal:
    proposal_id: str
    proposal_type: str
    explanation: str
    confidence: float
    created_at: str
    claim_id: str | None = None
    proposed_owner_entity_id: str | None = None
    proposed_section_key: str | None = None
    proposed_new_entity_type: str | None = None
    proposed_new_entity_title: str | None = None
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    status: str = "pending"
    reviewer_note: str | None = None
    reviewed_at: str | None = None
    applied_at: str | None = None

    def __post_init__(self) -> None:
        if self.proposal_type not in {"assign_claim", "merge_entities"}:
            raise ValueError(f"Unsupported organization proposal: {self.proposal_type}")
        if self.status not in {"pending", "rejected", "applied", "stale"}:
            raise ValueError(f"Unsupported organization proposal status: {self.status}")
        if self.proposal_type == "assign_claim":
            has_existing = bool(self.proposed_owner_entity_id)
            has_new = bool(self.proposed_new_entity_type and self.proposed_new_entity_title)
            if not self.claim_id or not self.proposed_section_key or has_existing == has_new:
                raise ValueError(
                    "Claim assignment proposals require one existing or new owner and a section"
                )
        if self.proposal_type == "merge_entities" and not (
            self.source_entity_id and self.target_entity_id
        ):
            raise ValueError("Merge proposals require source and target entities")
        if self.source_entity_id and self.source_entity_id == self.target_entity_id:
            raise ValueError("An entity cannot be merged into itself")
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class DreamRunAudit:
    run_id: str
    started_at: str
    completed_at: str
    status: str
    source_ids: list[str]
    completed_source_ids: list[str]
    pending_source_ids: list[str]
    pages_created: int
    pages_updated: int
    claim_decisions: list[DreamClaimDecision] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    reconsolidation_proposal_ids: list[str] = field(default_factory=list)


@dataclass
class ReconsolidationProposal:
    proposal_id: str
    incoming_claim_id: str
    target_claim_id: str
    proposed_relation: str
    explanation: str
    confidence: float
    dream_run_id: str
    created_at: str
    affected_entity_ids: list[str] = field(default_factory=list)
    status: str = "pending"
    reviewer_note: str | None = None
    reviewed_at: str | None = None
    applied_at: str | None = None
    application_error: str | None = None

    def __post_init__(self) -> None:
        if self.incoming_claim_id == self.target_claim_id:
            raise ValueError("A reconsolidation proposal must reference two distinct claims")
        relation = str(self.proposed_relation).strip().lower()
        if relation not in RECONSOLIDATION_RELATIONS:
            raise ValueError(f"Unsupported reconsolidation relation: {relation}")
        self.proposed_relation = relation
        status = str(self.status).strip().lower()
        if status not in RECONSOLIDATION_STATUSES:
            raise ValueError(f"Unsupported reconsolidation status: {status}")
        self.status = status
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.affected_entity_ids = sorted(set(self.affected_entity_ids))


@dataclass
class EpisodeManifest:
    episode_id: str
    source_id: str
    source_type: str
    occurred_at: str | None
    participants: list[str]
    segment_ids: list[str]
    claim_ids: list[str] = field(default_factory=list)
    ignored_segment_ids: list[str] = field(default_factory=list)
    extraction_status: str = "pending"
    extraction_error: str | None = None


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or str(uuid.uuid4())


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.sources_dir = root / "sources"
        self.episodes_dir = root / "episodes"
        self.claims_dir = root / "claims"
        self.dream_runs_dir = root / "dream-runs"
        self.reconsolidation_proposals_dir = root / "reconsolidation-proposals"
        self.entities_dir = root / "entities"
        self.placements_dir = root / "placements"
        self.scope_decisions_dir = root / "scope-decisions"
        self.retention_records_dir = root / "retention-records"
        self.entity_references_dir = root / "entity-references"
        self.entity_resolution_decisions_dir = root / "entity-resolution-decisions"
        self.scope_cohorts_dir = root / "scope-cohorts"
        self.encounters_dir = root / "encounters"
        self.consolidated_facts_dir = root / "consolidated-facts"
        self.organization_proposals_dir = root / "organization-proposals"
        for directory in (
            self.sources_dir,
            self.episodes_dir,
            self.claims_dir,
            self.dream_runs_dir,
            self.reconsolidation_proposals_dir,
            self.entities_dir,
            self.placements_dir,
            self.scope_decisions_dir,
            self.retention_records_dir,
            self.entity_references_dir,
            self.entity_resolution_decisions_dir,
            self.scope_cohorts_dir,
            self.encounters_dir,
            self.consolidated_facts_dir,
            self.organization_proposals_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def save_source(self, source: SourceDocument) -> None:
        _atomic_json(self.sources_dir / f"{_safe_id(source.source_id)}.json", asdict(source))

    def get_source(self, source_id: str) -> SourceDocument:
        data = self._read(self.sources_dir / f"{_safe_id(source_id)}.json")
        data["segments"] = [SourceSegment(**item) for item in data.get("segments", [])]
        return SourceDocument(**data)

    def list_sources(self) -> list[SourceDocument]:
        return [self.get_source(path.stem) for path in sorted(self.sources_dir.glob("*.json"))]

    def save_episode(self, episode: EpisodeManifest) -> None:
        _atomic_json(self.episodes_dir / f"{_safe_id(episode.episode_id)}.json", asdict(episode))

    def get_episode(self, episode_id: str) -> EpisodeManifest:
        return EpisodeManifest(**self._read(self.episodes_dir / f"{_safe_id(episode_id)}.json"))

    def list_episodes(self) -> list[EpisodeManifest]:
        return [self.get_episode(path.stem) for path in sorted(self.episodes_dir.glob("*.json"))]

    def save_claim(self, claim: MemoryClaim) -> None:
        _atomic_json(self.claims_dir / f"{_safe_id(claim.claim_id)}.json", asdict(claim))

    def save_entity(self, entity: EntityRecord) -> None:
        for existing in self.list_entities():
            if existing.entity_id != entity.entity_id and existing.slug == entity.slug:
                raise ValueError(f"Entity slug already exists: {entity.slug}")
        _atomic_json(self.entities_dir / f"{_safe_id(entity.entity_id)}.json", asdict(entity))

    def get_entity(self, entity_id: str) -> EntityRecord:
        return EntityRecord(**self._read(self.entities_dir / f"{_safe_id(entity_id)}.json"))

    def list_entities(self, *, status: str | None = None) -> list[EntityRecord]:
        entities = [self.get_entity(path.stem) for path in sorted(self.entities_dir.glob("*.json"))]
        return [entity for entity in entities if status is None or entity.status == status]

    def entity_for_slug(self, slug: str) -> EntityRecord | None:
        wanted = _slugify(slug)
        return next((entity for entity in self.list_entities() if entity.slug == wanted), None)

    def create_entity(
        self,
        entity_type: str,
        title: str,
        *,
        aliases: list[str] | None = None,
        materialization_state: str = "materialized",
    ) -> EntityRecord:
        now = datetime.now().astimezone().isoformat()
        slug = _slugify(title)
        if entity_type == "you":
            entity_id = "you"
            slug = "you"
        else:
            base = f"{entity_type}-{slug}"
            entity_id = base
            suffix = 2
            existing_ids = {entity.entity_id for entity in self.list_entities()}
            while entity_id in existing_ids:
                entity_id = f"{base}-{suffix}"
                suffix += 1
            used_slugs = {entity.slug for entity in self.list_entities()}
            base_slug = slug
            suffix = 2
            while slug in used_slugs:
                slug = f"{base_slug}-{suffix}"
                suffix += 1
        entity = EntityRecord(
            entity_id=entity_id,
            entity_type=entity_type,
            title=title,
            slug=slug,
            aliases=list(aliases or []),
            status="active",
            created_at=now,
            updated_at=now,
            materialization_state=materialization_state,
        )
        self.save_entity(entity)
        return entity

    def save_placement(self, placement: ClaimPlacement) -> None:
        self.get_claim(placement.claim_id)
        if placement.owner_entity_id:
            entity = self.get_entity(placement.owner_entity_id)
            from mycelium.models import PAGE_SECTION_KEYS, PageType
            allowed = {
                key for key, _ in PAGE_SECTION_KEYS[cast(PageType, entity.entity_type)]
            }
            if placement.section_key not in allowed:
                raise ValueError(
                    f"Section {placement.section_key!r} is invalid for {entity.entity_type}"
                )
            if placement.relationship_kind == "project_role":
                project_links = [
                    linked_id
                    for linked_id in placement.linked_entity_ids
                    if self.get_entity(linked_id).entity_type == "project"
                ]
                if entity.entity_type not in {"you", "person"} or len(project_links) != 1:
                    raise ValueError(
                        "Project-role placements require a Person or You owner and "
                        "exactly one linked Project"
                    )
        for linked_id in placement.linked_entity_ids:
            self.get_entity(linked_id)
        _atomic_json(
            self.placements_dir / f"{_safe_id(placement.claim_id)}.json", asdict(placement)
        )

    def get_placement(self, claim_id: str) -> ClaimPlacement:
        return ClaimPlacement(**self._read(
            self.placements_dir / f"{_safe_id(claim_id)}.json"
        ))

    def list_placements(self, *, status: str | None = None) -> list[ClaimPlacement]:
        placements = [
            self.get_placement(path.stem) for path in sorted(self.placements_dir.glob("*.json"))
        ]
        return [item for item in placements if status is None or item.status == status]

    def placement_for_claim(self, claim_id: str) -> ClaimPlacement | None:
        try:
            return self.get_placement(claim_id)
        except FileNotFoundError:
            return None

    def save_scope_decision(self, decision: ClaimScopeDecision) -> None:
        if decision.status == "active":
            for current in self.list_scope_decisions(
                claim_id=decision.claim_id, status="active"
            ):
                if current.decision_id == decision.decision_id:
                    continue
                current.status = "superseded"
                current.superseded_by_decision_id = decision.decision_id
                _atomic_json(
                    self.scope_decisions_dir / f"{_safe_id(current.decision_id)}.json",
                    asdict(current),
                )
        _atomic_json(
            self.scope_decisions_dir / f"{_safe_id(decision.decision_id)}.json",
            asdict(decision),
        )

    def get_scope_decision(self, decision_id: str) -> ClaimScopeDecision:
        return ClaimScopeDecision(**self._read(
            self.scope_decisions_dir / f"{_safe_id(decision_id)}.json"
        ))

    def list_scope_decisions(
        self, *, claim_id: str | None = None, status: str | None = None
    ) -> list[ClaimScopeDecision]:
        values = [
            self.get_scope_decision(path.stem)
            for path in sorted(self.scope_decisions_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (status is None or item.status == status)
        ]

    def active_scope_decision(self, claim_id: str) -> ClaimScopeDecision | None:
        values = self.list_scope_decisions(claim_id=claim_id, status="active")
        return values[-1] if values else None

    def save_retention_record(self, record: NonWikiRetentionRecord) -> None:
        if record.claim_id:
            self.get_claim(record.claim_id)
        self.get_source(record.source_id)
        _atomic_json(
            self.retention_records_dir / f"{_safe_id(record.retention_id)}.json",
            asdict(record),
        )

    def get_retention_record(self, retention_id: str) -> NonWikiRetentionRecord:
        return NonWikiRetentionRecord(**self._read(
            self.retention_records_dir / f"{_safe_id(retention_id)}.json"
        ))

    def list_retention_records(
        self, *, claim_id: str | None = None, source_id: str | None = None
    ) -> list[NonWikiRetentionRecord]:
        values = [
            self.get_retention_record(path.stem)
            for path in sorted(self.retention_records_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (source_id is None or item.source_id == source_id)
        ]

    def save_entity_reference(self, reference: ClaimEntityReference) -> None:
        self.get_claim(reference.claim_id)
        if reference.entity_id:
            self.get_entity(reference.entity_id)
        if reference.status == "active":
            for current in self.list_entity_references(
                claim_id=reference.claim_id, status="active"
            ):
                if current.role != reference.role or current.surface != reference.surface:
                    continue
                current.status = "superseded"
                current.superseded_by_reference_id = reference.reference_id
                _atomic_json(
                    self.entity_references_dir
                    / f"{_safe_id(current.reference_id)}.json",
                    asdict(current),
                )
        _atomic_json(
            self.entity_references_dir / f"{_safe_id(reference.reference_id)}.json",
            asdict(reference),
        )

    def get_entity_reference(self, reference_id: str) -> ClaimEntityReference:
        return ClaimEntityReference(**self._read(
            self.entity_references_dir / f"{_safe_id(reference_id)}.json"
        ))

    def list_entity_references(
        self,
        *,
        claim_id: str | None = None,
        entity_id: str | None = None,
        status: str | None = None,
    ) -> list[ClaimEntityReference]:
        values = [
            self.get_entity_reference(path.stem)
            for path in sorted(self.entity_references_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (claim_id is None or item.claim_id == claim_id)
            and (entity_id is None or item.entity_id == entity_id)
            and (status is None or item.status == status)
        ]

    def save_entity_resolution_decision(
        self, decision: EntityResolutionDecision
    ) -> None:
        if decision.entity_id:
            self.get_entity(decision.entity_id)
        for claim_id in decision.supporting_claim_ids:
            self.get_claim(claim_id)
        _atomic_json(
            self.entity_resolution_decisions_dir
            / f"{_safe_id(decision.decision_id)}.json",
            asdict(decision),
        )

    def get_entity_resolution_decision(
        self, decision_id: str
    ) -> EntityResolutionDecision:
        return EntityResolutionDecision(**self._read(
            self.entity_resolution_decisions_dir / f"{_safe_id(decision_id)}.json"
        ))

    def list_entity_resolution_decisions(
        self, *, entity_id: str | None = None, review_state: str | None = None
    ) -> list[EntityResolutionDecision]:
        values = [
            self.get_entity_resolution_decision(path.stem)
            for path in sorted(self.entity_resolution_decisions_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (entity_id is None or item.entity_id == entity_id)
            and (review_state is None or item.review_state == review_state)
        ]

    def save_scope_cohort(self, cohort: ScopeCohort) -> None:
        for claim_id in cohort.claim_ids:
            self.get_claim(claim_id)
        _atomic_json(
            self.scope_cohorts_dir / f"{_safe_id(cohort.cohort_id)}.json",
            asdict(cohort),
        )

    def get_scope_cohort(self, cohort_id: str) -> ScopeCohort:
        return ScopeCohort(**self._read(
            self.scope_cohorts_dir / f"{_safe_id(cohort_id)}.json"
        ))

    def list_scope_cohorts(self) -> list[ScopeCohort]:
        values = [
            self.get_scope_cohort(path.stem)
            for path in sorted(self.scope_cohorts_dir.glob("*.json"))
        ]
        return sorted(values, key=lambda item: (item.created_at, item.cohort_id))

    def save_encounter(self, encounter: EntityEncounter) -> None:
        self.get_entity(encounter.entity_id)
        _atomic_json(
            self.encounters_dir / f"{_safe_id(encounter.encounter_id)}.json",
            asdict(encounter),
        )

    def get_encounter(self, encounter_id: str) -> EntityEncounter:
        return EntityEncounter(**self._read(
            self.encounters_dir / f"{_safe_id(encounter_id)}.json"
        ))

    def list_encounters(self, *, entity_id: str | None = None) -> list[EntityEncounter]:
        values = [
            self.get_encounter(path.stem)
            for path in sorted(self.encounters_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if entity_id is None or item.entity_id == entity_id
        ]

    def save_consolidated_fact(self, fact: ConsolidatedFact) -> None:
        self.get_entity(fact.owner_entity_id)
        from mycelium.models import PAGE_SECTION_KEYS, PageType
        allowed = {
            key for key, _ in PAGE_SECTION_KEYS[
                cast(PageType, self.get_entity(fact.owner_entity_id).entity_type)
            ]
        }
        if fact.section_key not in allowed:
            raise ValueError(
                f"Section {fact.section_key!r} is invalid for consolidated fact owner"
            )
        for claim_id in fact.member_claim_ids:
            self.get_claim(claim_id)
        for linked_id in fact.linked_entity_ids:
            self.get_entity(linked_id)
        _atomic_json(
            self.consolidated_facts_dir / f"{_safe_id(fact.fact_id)}.json",
            asdict(fact),
        )

    def get_consolidated_fact(self, fact_id: str) -> ConsolidatedFact:
        return ConsolidatedFact(**self._read(
            self.consolidated_facts_dir / f"{_safe_id(fact_id)}.json"
        ))

    def list_consolidated_facts(
        self, *, owner_entity_id: str | None = None
    ) -> list[ConsolidatedFact]:
        values = [
            self.get_consolidated_fact(path.stem)
            for path in sorted(self.consolidated_facts_dir.glob("*.json"))
        ]
        return [
            item for item in values
            if (owner_entity_id is None or item.owner_entity_id == owner_entity_id)
        ]

    def facts_for_claim(self, claim_id: str) -> list[ConsolidatedFact]:
        return [
            fact for fact in self.list_consolidated_facts()
            if claim_id in fact.member_claim_ids
        ]

    def delete_consolidated_fact(self, fact_id: str) -> None:
        path = self.consolidated_facts_dir / f"{_safe_id(fact_id)}.json"
        if path.exists():
            path.unlink()

    def placements_for_entity(self, entity_id: str) -> list[ClaimPlacement]:
        return [
            placement for placement in self.list_placements(status="placed")
            if placement.owner_entity_id == entity_id
        ]

    def save_organization_proposal(self, proposal: OrganizationProposal) -> None:
        _atomic_json(
            self.organization_proposals_dir / f"{_safe_id(proposal.proposal_id)}.json",
            asdict(proposal),
        )

    def get_organization_proposal(self, proposal_id: str) -> OrganizationProposal:
        return OrganizationProposal(**self._read(
            self.organization_proposals_dir / f"{_safe_id(proposal_id)}.json"
        ))

    def list_organization_proposals(self, *, status: str | None = None) -> list[OrganizationProposal]:
        proposals = [
            self.get_organization_proposal(path.stem)
            for path in sorted(self.organization_proposals_dir.glob("*.json"), reverse=True)
        ]
        return [item for item in proposals if status is None or item.status == status]

    def get_claim(self, claim_id: str) -> MemoryClaim:
        data = self._read(self.claims_dir / f"{_safe_id(claim_id)}.json")
        data["provenance"] = [ClaimProvenance(**item) for item in data.get("provenance", [])]
        return MemoryClaim(**data)

    def save_dream_run(self, run: DreamRunAudit) -> None:
        _atomic_json(self.dream_runs_dir / f"{_safe_id(run.run_id)}.json", asdict(run))

    def get_dream_run(self, run_id: str) -> DreamRunAudit:
        data = self._read(self.dream_runs_dir / f"{_safe_id(run_id)}.json")
        data["claim_decisions"] = [
            DreamClaimDecision(**item) for item in data.get("claim_decisions", [])
        ]
        return DreamRunAudit(**data)

    def list_dream_runs(self) -> list[DreamRunAudit]:
        return [
            self.get_dream_run(path.stem)
            for path in sorted(self.dream_runs_dir.glob("*.json"), reverse=True)
        ]

    def save_reconsolidation_proposal(self, proposal: ReconsolidationProposal) -> None:
        _atomic_json(
            self.reconsolidation_proposals_dir / f"{_safe_id(proposal.proposal_id)}.json",
            asdict(proposal),
        )

    def get_reconsolidation_proposal(self, proposal_id: str) -> ReconsolidationProposal:
        return ReconsolidationProposal(**self._read(
            self.reconsolidation_proposals_dir / f"{_safe_id(proposal_id)}.json"
        ))

    def list_reconsolidation_proposals(
        self, *, status: str | None = None
    ) -> list[ReconsolidationProposal]:
        proposals = [
            self.get_reconsolidation_proposal(path.stem)
            for path in sorted(
                self.reconsolidation_proposals_dir.glob("*.json"), reverse=True
            )
        ]
        return [
            proposal for proposal in proposals
            if status is None or proposal.status == status
        ]

    def find_reconsolidation_proposal(
        self, incoming_claim_id: str, target_claim_id: str, relation: str
    ) -> ReconsolidationProposal | None:
        return next((
            proposal for proposal in self.list_reconsolidation_proposals()
            if proposal.incoming_claim_id == incoming_claim_id
            and proposal.target_claim_id == target_claim_id
            and proposal.proposed_relation == relation
        ), None)

    def pending_reconsolidation_claim_ids(self) -> set[str]:
        return {
            claim_id
            for proposal in self.list_reconsolidation_proposals(status="pending")
            for claim_id in (proposal.incoming_claim_id, proposal.target_claim_id)
        }

    def persist_dream_audit(self, run: DreamRunAudit) -> None:
        """Commit current claim dispositions, then write the immutable run record."""
        decided_at = run.completed_at
        for decision in run.claim_decisions:
            try:
                claim = self.get_claim(decision.claim_id)
            except FileNotFoundError:
                continue
            claim.dream_disposition = decision.disposition
            claim.dream_disposition_reason = decision.reason
            claim.dream_run_id = run.run_id
            claim.dream_disposition_at = decided_at
            self.save_claim(claim)
        self.save_dream_run(run)

    def clear(self) -> dict[str, int]:
        """Delete all derived artifacts while leaving canonical UI conversations untouched."""
        counts = {
            "sources": 0,
            "episodes": 0,
            "claims": 0,
            "dream_runs": 0,
            "reconsolidation_proposals": 0,
            "entities": 0,
            "placements": 0,
            "organization_proposals": 0,
            "scope_decisions": 0,
            "retention_records": 0,
            "entity_references": 0,
            "entity_resolution_decisions": 0,
            "scope_cohorts": 0,
            "encounters": 0,
            "consolidated_facts": 0,
        }
        for label, directory in (
            ("sources", self.sources_dir),
            ("episodes", self.episodes_dir),
            ("claims", self.claims_dir),
            ("dream_runs", self.dream_runs_dir),
            ("reconsolidation_proposals", self.reconsolidation_proposals_dir),
            ("entities", self.entities_dir),
            ("placements", self.placements_dir),
            ("organization_proposals", self.organization_proposals_dir),
            ("scope_decisions", self.scope_decisions_dir),
            ("retention_records", self.retention_records_dir),
            ("entity_references", self.entity_references_dir),
            ("entity_resolution_decisions", self.entity_resolution_decisions_dir),
            ("scope_cohorts", self.scope_cohorts_dir),
            ("encounters", self.encounters_dir),
            ("consolidated_facts", self.consolidated_facts_dir),
        ):
            for path in directory.glob("*.json"):
                path.unlink()
                counts[label] += 1
        return counts

    def clear_projection(self) -> dict[str, int]:
        """Delete entity-owned derived artifacts while preserving sources and claims."""
        counts = {
            "entities": 0,
            "placements": 0,
            "organization_proposals": 0,
            "scope_decisions": 0,
            "retention_records": 0,
            "entity_references": 0,
            "entity_resolution_decisions": 0,
            "scope_cohorts": 0,
            "encounters": 0,
            "consolidated_facts": 0,
            "claims_requeued": 0,
        }
        for label, directory in (
            ("entities", self.entities_dir),
            ("placements", self.placements_dir),
            ("organization_proposals", self.organization_proposals_dir),
            ("scope_decisions", self.scope_decisions_dir),
            ("retention_records", self.retention_records_dir),
            ("entity_references", self.entity_references_dir),
            ("entity_resolution_decisions", self.entity_resolution_decisions_dir),
            ("scope_cohorts", self.scope_cohorts_dir),
            ("encounters", self.encounters_dir),
            ("consolidated_facts", self.consolidated_facts_dir),
        ):
            for path in directory.glob("*.json"):
                path.unlink()
                counts[label] += 1
        for path in self.claims_dir.glob("*.json"):
            data = self._read(path)
            changed = False
            if data.get("status", "active") == "active" and data.get(
                "dream_disposition"
            ) != "excluded_source_policy":
                data["dream_disposition"] = "pending"
                data["dream_disposition_reason"] = "Canonical projection was cleared."
                data["dream_run_id"] = None
                data["dream_disposition_at"] = None
                counts["claims_requeued"] += 1
                changed = True
            if not changed:
                continue
            _atomic_json(path, data)
        return counts

    def list_claims(self, *, status: str | None = None) -> list[MemoryClaim]:
        claims = [self.get_claim(path.stem) for path in sorted(self.claims_dir.glob("*.json"))]
        return [claim for claim in claims if status is None or claim.status == status]

    def list_short_term_claims(
        self, *, include_deferred: bool = True
    ) -> list[MemoryClaim]:
        """Return active claims that have not entered canonical wiki memory.

        Claim disposition is the durable queue state. A placement is consulted as
        an integrity guard so a stale disposition cannot make an already placed
        claim appear in short-term memory.
        """
        allowed = {"pending", "routing_failed"}
        if include_deferred:
            allowed.add("deferred")
        queued = []
        for claim in self.list_claims(status="active"):
            if claim.dream_disposition not in allowed:
                continue
            placement = self.placement_for_claim(claim.claim_id)
            if placement and placement.status == "placed":
                continue
            queued.append(claim)
        return queued

    def memory_tier(self, claim_id: str) -> str:
        claim = self.get_claim(claim_id)
        placement = self.placement_for_claim(claim_id)
        if claim.dream_disposition == "excluded_source_policy":
            return "source"
        if (
            claim.dream_disposition in SHORT_TERM_DISPOSITIONS
            and not (placement and placement.status == "placed")
        ):
            return "short_term"
        return "canonical"

    def claims_for_sources(self, source_ids: Iterable[str], *, active_only: bool = True) -> list[MemoryClaim]:
        wanted = set(source_ids)
        return [
            claim for claim in self.list_claims(status="active" if active_only else None)
            if any(prov.source_id in wanted for prov in claim.provenance)
        ]

    def claims_for_entity(self, entity_id: str) -> list[MemoryClaim]:
        claim_ids = {
            placement.claim_id for placement in self.placements_for_entity(entity_id)
        }
        return [
            claim for claim in self.list_claims(status="active")
            if claim.claim_id in claim_ids
        ]

    def coverage_report(self) -> dict[str, Any]:
        sources = self.list_sources()
        claims = self.list_claims()
        episodes = self.list_episodes()
        all_segments = {segment.segment_id for source in sources for segment in source.segments}
        claimed_segments = {
            segment_id for claim in claims for provenance in claim.provenance
            for segment_id in provenance.segment_ids
        }
        ignored_segments = {
            segment_id for episode in episodes for segment_id in episode.ignored_segment_ids
        }
        unresolved = claimed_segments - all_segments
        accounted_segments = (claimed_segments | ignored_segments) & all_segments
        return {
            "sources": len(sources),
            "episodes": len(episodes),
            "claims": len(claims),
            "active_claims": sum(claim.status == "active" for claim in claims),
            "segments": len(all_segments),
            "claimed_segments": len(all_segments & claimed_segments),
            "segment_coverage": (len(all_segments & claimed_segments) / len(all_segments)) if all_segments else 1.0,
            "ignored_segments": len(all_segments & ignored_segments),
            "accounted_segments": len(accounted_segments),
            "accounted_coverage": (len(accounted_segments) / len(all_segments)) if all_segments else 1.0,
            "unassigned_segment_ids": sorted(all_segments - claimed_segments),
            "unaccounted_segment_ids": sorted(all_segments - claimed_segments - ignored_segments),
            "unplaced_claim_ids": sorted(
                claim.claim_id for claim in claims
                if not (
                    (placement := self.placement_for_claim(claim.claim_id))
                    and placement.owner_entity_id
                )
            ),
            "unresolved_provenance_ids": sorted(unresolved),
            "failed_episode_ids": sorted(ep.episode_id for ep in episodes if ep.extraction_status == "failed"),
            "partial_episode_ids": sorted(ep.episode_id for ep in episodes if ep.extraction_status == "partial"),
        }

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)


_LABELED_TRANSCRIPT_LINE = re.compile(
    r"^\[(?P<label>[^]]+)]\s*(?:\((?P<time>[^)]+)\)\s*)?(?P<speaker>[^:]+):\s*(?P<text>.*)$"
)
_ROLE_LINE = re.compile(r"^(?P<role>USER|ASSISTANT|SYSTEM|TOOL)(?:\s*\([^)]*\))?:\s*(?P<text>.*)$", re.I)


def segment_transcript(transcript: str, source_id: str) -> list[SourceSegment]:
    """Split common transcript formats while preserving every nonempty line."""
    segments: list[SourceSegment] = []
    current: SourceSegment | None = None
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not segments and re.match(r"^(Session|Timestamp|Sample):\s*", line, re.I):
            continue
        labeled_turn = _LABELED_TRANSCRIPT_LINE.match(line)
        role_match = _ROLE_LINE.match(line)
        if labeled_turn:
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments),
                speaker=labeled_turn.group("speaker").strip(),
                timestamp=labeled_turn.group("time"),
                content=labeled_turn.group("text").strip(),
                metadata={"source_label": labeled_turn.group("label")},
            )
            segments.append(current)
        elif role_match:
            role = role_match.group("role").lower()
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments), role=role, speaker=role,
                content=role_match.group("text").strip(),
            )
            segments.append(current)
        elif current is not None:
            current.content = f"{current.content}\n{line}".strip()
        else:
            current = SourceSegment(
                segment_id=f"{source_id}#seg-{len(segments) + 1:04d}",
                index=len(segments), content=line,
            )
            segments.append(current)
    return segments


def normalize_temporal_facets(
    facets: dict[str, Any], anchor: str | None, claim_text: str | None = None
) -> dict[str, Any]:
    """Resolve relative time into one explicit, provenance-preserving interval."""
    result = dict(facets or {})
    existing_temporal = result.get("temporal")
    deadline_expression = result.pop("deadline", None)
    role = (
        str(existing_temporal.get("role") or "event_time")
        if isinstance(existing_temporal, dict)
        else "deadline" if deadline_expression else "event_time"
    )
    expression = str(
        (existing_temporal.get("expression") if isinstance(existing_temporal, dict) else None)
        or deadline_expression
        or result.pop("when", None)
        or result.pop("time_expression", None)
        or ""
    ).strip()
    for legacy_key in ("normalized_date", "date_precision", "normalization_anchor"):
        result.pop(legacy_key, None)
    if not expression and claim_text:
        deadline_match = re.search(
            r"\b(?:by|due(?: on)?)\s+("
            r"(?:last|this|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"(?:last|this|next) (?:week|month)|"
            r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"end of (?:this|next) (?:week|month)|"
            r"in (?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+) "
            r"(?:days?|weeks?)(?: from now)?|today|tomorrow)\b",
            claim_text,
            re.I,
        )
        if deadline_match:
            expression = deadline_match.group(1)
            role = "deadline"
    if not expression and claim_text:
        match = re.search(
            r"\b(today|yesterday|tomorrow|the day before yesterday|"
            r"the day after tomorrow|last week|this week|next week|"
            r"last month|this month|next month|"
            r"early next week|late next week|later this week|sometime next week|"
            r"soon|recently|"
            r"(?:in )?(?:a few|few|several) (?:days?|weeks?) "
            r"(?:ago|later|from now)|"
            r"(?:last|this|next) (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
            r"(?:in (?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|\d+) (?:days?|weeks?)(?: from now)?|"
            r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
            r"eleven|twelve|\d+) (?:days?|weeks?) (?:ago|later|from now))|"
            r"(?:(?:a|one|two|three|\d+) )?years? ago)\b",
            claim_text,
            re.I,
        )
        if match:
            expression = match.group(0)
    if anchor:
        result.setdefault("observed_at", anchor)
    if not expression:
        return result
    temporal: dict[str, Any] = {
        "expression": expression,
        "anchor": anchor,
        "role": role,
        "status": "unresolved",
        "certainty": "unknown",
    }
    result["temporal"] = temporal
    if not anchor:
        return result
    base = parse_source_datetime(anchor)
    if base is None:
        return result
    temporal["anchor_date"] = base.date().isoformat()
    lowered = expression.lower()
    if role == "deadline":
        lowered = re.sub(r"^(?:by|due(?: on)?)\s+", "", lowered).strip()
    deadline_boundary = _deadline_boundary(lowered, base) if role == "deadline" else None
    if deadline_boundary is not None:
        normalized = deadline_boundary.isoformat()
        temporal.update({
            "start": normalized,
            "end": normalized,
            "precision": "day",
            "status": "resolved",
            "certainty": "exact",
        })
        return result
    vague = _vague_temporal_interval(lowered, base)
    if vague is not None:
        temporal.update(vague)
        return result
    if lowered in {"soon", "recently"}:
        temporal.update({
            "direction": "future" if lowered == "soon" else "past",
            "certainty": "vague",
        })
        return result
    target: datetime | None = None
    if lowered == "today":
        target = base
    elif lowered == "yesterday":
        target = base - timedelta(days=1)
    elif lowered == "tomorrow":
        target = base + timedelta(days=1)
    elif lowered == "the day before yesterday":
        target = base - timedelta(days=2)
    elif lowered == "the day after tomorrow":
        target = base + timedelta(days=2)
    elif lowered in {"last week", "this week", "next week"}:
        offset = {"last week": -1, "this week": 0, "next week": 1}[lowered]
        start = base.date() - timedelta(days=base.weekday()) + timedelta(weeks=offset)
        temporal.update({
            "start": start.isoformat(),
            "end": (start + timedelta(days=6)).isoformat(),
            "precision": "week",
            "status": "resolved",
            "certainty": "exact",
        })
        return result
    elif lowered in {"last month", "this month", "next month"}:
        offset = {"last month": -1, "this month": 0, "next month": 1}[lowered]
        month_index = base.year * 12 + base.month - 1 + offset
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        last_day = calendar.monthrange(year, month)[1]
        temporal.update({
            "start": f"{year:04d}-{month:02d}-01",
            "end": f"{year:04d}-{month:02d}-{last_day:02d}",
            "precision": "month",
            "status": "resolved",
            "certainty": "exact",
        })
        return result
    offset_days = _relative_offset_days(lowered)
    if offset_days is not None:
        target = base + timedelta(days=offset_days)
    years_ago = re.fullmatch(r"(?:(a|one|two|three|\d+) )?years? ago", lowered)
    if years_ago:
        raw_years = years_ago.group(1) or "one"
        years = {"a": 1, "one": 1, "two": 2, "three": 3}.get(raw_years)
        if years is None and raw_years.isdigit():
            years = int(raw_years)
        if years is not None and 0 < years <= 100:
            year = base.year - years
            temporal.update({
                "start": f"{year:04d}-01-01",
                "end": f"{year:04d}-12-31",
                "precision": "year",
                "status": "resolved",
                "certainty": "exact",
            })
            return result
    weekday = re.fullmatch(
        r"(last|this|next) "
        r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        lowered,
    )
    if weekday:
        desired = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(weekday.group(2))
        if weekday.group(1) == "last":
            target = base + timedelta(days=desired - base.weekday() - 7)
        elif weekday.group(1) == "next":
            target = base + timedelta(days=desired - base.weekday() + 7)
        else:
            target = base + timedelta(days=desired - base.weekday())
    if target is not None:
        normalized = target.date().isoformat()
        temporal.update({
            "start": normalized,
            "end": normalized,
            "precision": "day",
            "status": "resolved",
            "certainty": "exact",
        })
    return result


def temporal_record(facets: dict[str, Any]) -> dict[str, Any] | None:
    value = facets.get("temporal")
    return value if isinstance(value, dict) and value.get("expression") else None


def query_temporal_record(query: str, anchor: datetime) -> dict[str, Any] | None:
    facets = normalize_temporal_facets({}, anchor.isoformat(), query)
    temporal = temporal_record(facets)
    if temporal and re.search(r"\b(?:deadline|deadlines|due)\b", query, re.I):
        temporal["role"] = "deadline"
    return temporal


def temporal_intervals_overlap(
    left: dict[str, Any], right: dict[str, Any]
) -> bool:
    left_start = str(left.get("start") or "")
    left_end = str(left.get("end") or left_start)
    right_start = str(right.get("start") or "")
    right_end = str(right.get("end") or right_start)
    if not all((left_start, left_end, right_start, right_end)):
        return False
    return left_start <= right_end and right_start <= left_end


def _relative_offset_days(expression: str) -> int | None:
    match = re.fullmatch(
        r"(?:in (a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|\d+) (days?|weeks?)(?: (from now))?|"
        r"(a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|\d+) (days?|weeks?) (ago|later|from now))",
        expression,
    )
    if not match:
        return None
    raw_count = match.group(1) or match.group(4)
    unit = match.group(2) or match.group(5)
    direction = match.group(3) or match.group(6) or "from now"
    count = NUMBER_WORDS.get(raw_count)
    if count is None and raw_count.isdigit():
        count = int(raw_count)
    if count is None or count <= 0 or count > 3660:
        return None
    days = count * (7 if unit.startswith("week") else 1)
    return -days if direction == "ago" else days


def _deadline_boundary(expression: str, anchor: datetime) -> date | None:
    weekdays = [
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
    ]
    if expression in weekdays:
        desired = weekdays.index(expression)
        return anchor.date() + timedelta(days=(desired - anchor.weekday()) % 7)
    if expression in {"end of this week", "end of next week"}:
        week_start = anchor.date() - timedelta(days=anchor.weekday())
        return week_start + timedelta(days=6 if expression == "end of this week" else 13)
    if expression in {"end of this month", "end of next month"}:
        offset = 0 if expression == "end of this month" else 1
        month_index = anchor.year * 12 + anchor.month - 1 + offset
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        return anchor.date().replace(
            year=year,
            month=month,
            day=calendar.monthrange(year, month)[1],
        )
    return None

def _vague_temporal_interval(
    expression: str, anchor: datetime
) -> dict[str, Any] | None:
    week_start = anchor.date() - timedelta(days=anchor.weekday())
    if expression in {"early next week", "late next week", "sometime next week"}:
        next_week = week_start + timedelta(weeks=1)
        offsets = {
            "early next week": (0, 2),
            "late next week": (4, 6),
            "sometime next week": (0, 6),
        }
        start_offset, end_offset = offsets[expression]
        return {
            "start": (next_week + timedelta(days=start_offset)).isoformat(),
            "end": (next_week + timedelta(days=end_offset)).isoformat(),
            "precision": "range",
            "status": "bounded",
            "certainty": "approximate",
        }
    if expression == "later this week":
        start = min(anchor.date() + timedelta(days=1), week_start + timedelta(days=6))
        return {
            "start": start.isoformat(),
            "end": (week_start + timedelta(days=6)).isoformat(),
            "precision": "range",
            "status": "bounded",
            "certainty": "approximate",
        }
    match = re.fullmatch(
        r"(?:in )?(a few|few|several) (days?|weeks?) (ago|later|from now)",
        expression,
    )
    if not match:
        return None
    quantity, unit, direction = match.groups()
    low, high = (2, 5) if quantity in {"a few", "few"} else (3, 7)
    multiplier = 7 if unit.startswith("week") else 1
    low *= multiplier
    high *= multiplier
    if direction == "ago":
        start = anchor.date() - timedelta(days=high)
        end = anchor.date() - timedelta(days=low)
    else:
        start = anchor.date() + timedelta(days=low)
        end = anchor.date() + timedelta(days=high)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "precision": "range",
        "status": "bounded",
        "certainty": "approximate",
    }


def parse_source_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip(), flags=re.I)
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in (
        "%I:%M %p on %d %B, %Y",
        "%I:%M%p on %d %B, %Y",
        "%d %B, %Y",
        "%B %d, %Y",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None
