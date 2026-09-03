"""Persisted artifact records and their structural validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mycelium.ontology import (
    CLAIM_TYPES,
    ENTITY_TYPES,
    SUBJECT_PAGE_STATES,
    SUBJECT_PERSISTED_SCOPES,
)

EVIDENCE_MODALITIES = {"speech", "visual", "tool", "mixed", "unknown"}
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
ENTITY_REFERENCE_ROLES = {
    "subject", "object", "context", "canonical_owner", "identity_subject",
}
RECONSOLIDATION_RELATIONS = {"contradicts", "supersedes"}
RECONSOLIDATION_STATUSES = {"pending", "approved", "rejected", "applied", "stale"}
SOURCE_STATUSES = {"active", "retracted"}
CLAIM_STATUSES = {"active", "superseded", "retracted"}

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
    status: str = "active"
    retracted_at: str | None = None
    retraction_reason: str | None = None

    def __post_init__(self) -> None:
        self.status = str(self.status).strip().lower()
        if self.status not in SOURCE_STATUSES:
            raise ValueError(f"Unsupported source status: {self.status}")
        if self.status == "retracted" and not (
            self.retracted_at and str(self.retraction_reason or "").strip()
        ):
            raise ValueError("Retracted sources require a timestamp and reason")
        if self.status == "active" and (self.retracted_at or self.retraction_reason):
            raise ValueError("Active sources cannot contain retraction details")


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
    about: list[dict[str, str]]
    provenance: list[ClaimProvenance]
    recorded_at: str
    status: str = "active"
    confidence: float = 0.8
    slot: str | None = None
    facets: dict[str, Any] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)
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
        self.status = str(self.status).strip().lower()
        if self.status not in CLAIM_STATUSES:
            raise ValueError(f"Unsupported claim status: {self.status}")

        normalized_type = _normalized_label(self.claim_type)
        if normalized_type not in CLAIM_TYPES:
            normalized_type = "unknown"
        self.claim_type = normalized_type

        modality = _normalized_label(self.evidence_modality)
        if modality not in EVIDENCE_MODALITIES:
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
        if self.entity_type not in ENTITY_TYPES:
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
    proposed_scope: str | None = None
    proposed_parent_entity_id: str | None = None
    proposed_page_state: str | None = None
    proposed_aliases: list[str] = field(default_factory=list)
    proposed_type_reason: str | None = None
    reviewer_note: str | None = None
    reviewed_at: str | None = None

    def __post_init__(self) -> None:
        if self.decision_type not in {"entity_creation", "participant_resolution"}:
            raise ValueError(f"Unsupported entity-resolution decision: {self.decision_type}")
        if self.review_state not in {"accepted", "review_required", "rejected"}:
            raise ValueError(f"Unsupported identity review state: {self.review_state}")
        if self.proposed_scope is not None and (
            self.proposed_scope not in SUBJECT_PERSISTED_SCOPES
        ):
            raise ValueError(f"Unsupported proposed identity scope: {self.proposed_scope}")
        if self.proposed_page_state is not None and (
            self.proposed_page_state not in SUBJECT_PAGE_STATES
        ):
            raise ValueError(
                f"Unsupported proposed identity page state: {self.proposed_page_state}"
            )
        self.source_ids = sorted(set(self.source_ids))
        self.supporting_claim_ids = sorted(set(self.supporting_claim_ids))
        self.supporting_segment_ids = sorted(set(self.supporting_segment_ids))
        self.proposed_aliases = sorted(set(self.proposed_aliases))
        self.confidence = max(0.0, min(1.0, float(self.confidence)))


@dataclass
class IdentityMaturityAssessment:
    assessment_id: str
    dream_run_id: str
    identity_key: str
    source_node_ids: list[str]
    proposed_title: str
    proposed_entity_type: str
    supporting_source_ids: list[str]
    supporting_claim_ids: list[str]
    supporting_segment_ids: list[str]
    proposal_admission: str
    proposal_basis: dict
    proposal_reason: str
    proposal_confidence: float
    verifier_verdict: str
    verifier_reason: str
    effective_admission: str
    created_at: str
    entity_id: str | None = None

    def __post_init__(self) -> None:
        if self.proposal_admission not in {"materialized", "provisional"}:
            raise ValueError(
                f"Unsupported maturity proposal: {self.proposal_admission}"
            )
        if self.verifier_verdict not in {
            "supported", "unsupported", "not_required",
        }:
            raise ValueError(
                f"Unsupported maturity verdict: {self.verifier_verdict}"
            )
        if self.effective_admission not in {
            "materialized", "provisional", "no_page", "review_required",
        }:
            raise ValueError(
                f"Unsupported effective maturity: {self.effective_admission}"
            )
        self.source_node_ids = sorted(set(self.source_node_ids))
        self.supporting_source_ids = sorted(set(self.supporting_source_ids))
        self.supporting_claim_ids = sorted(set(self.supporting_claim_ids))
        self.supporting_segment_ids = sorted(set(self.supporting_segment_ids))
        self.proposal_confidence = max(
            0.0, min(1.0, float(self.proposal_confidence))
        )


@dataclass
class IdentityWorkUnit:
    """Durable bounded unit for resumable identity adjudication."""

    unit_id: str
    claim_ids: list[str]
    source_ids: list[str]
    status: str = "pending"
    stage: str = "subject_nodes"
    attempt_count: int = 0
    subject_nodes: list[dict[str, Any]] = field(default_factory=list)
    identity_node_decisions: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    local_identity_decisions: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    pending_identity_decisions: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    identity_groups: list[dict[str, Any]] = field(default_factory=list)
    existing_identity_verdicts: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    type_proposals: dict[str, dict[str, Any]] = field(default_factory=dict)
    type_verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)
    new_identity_verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)
    maturity_decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    maturity_verdicts: dict[str, dict[str, Any]] = field(default_factory=dict)
    entity_plan: dict[str, Any] = field(default_factory=dict)
    last_error: str | None = None
    dream_run_ids: list[str] = field(default_factory=list)
    updated_at: str | None = None

    def __post_init__(self) -> None:
        self.claim_ids = sorted(set(self.claim_ids))
        self.source_ids = sorted(set(self.source_ids))
        self.dream_run_ids = list(dict.fromkeys(self.dream_run_ids))
        if not self.claim_ids or not self.source_ids:
            raise ValueError("Identity work units require claims and sources")
        if self.status not in {"pending", "failed", "complete"}:
            raise ValueError(f"Unsupported identity work status: {self.status}")

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
    identity_blocker_ids: list[str] = field(default_factory=list)

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
        self.identity_blocker_ids = sorted(set(self.identity_blocker_ids))


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
    identity_blocker_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.origin not in {"automatic", "manual", "review"}:
            raise ValueError(f"Unsupported scope-decision origin: {self.origin}")
        if self.status not in {"active", "superseded", "proposed", "rejected"}:
            raise ValueError(f"Unsupported scope-decision status: {self.status}")
        if self.status == "superseded" and not self.superseded_by_decision_id:
            raise ValueError("Superseded scope decisions require a successor")
        self.linked_entity_ids = sorted(set(self.linked_entity_ids))
        self.supporting_claim_ids = sorted(set(self.supporting_claim_ids))
        self.identity_blocker_ids = sorted(set(self.identity_blocker_ids))
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
    state: str
    linked_entity_ids: list[str]
    synthesis_origin: str
    confidence: float
    reason: str
    created_at: str
    updated_at: str
    manual_text: bool = False

    def __post_init__(self) -> None:
        if self.state not in {"current", "history"}:
            raise ValueError(f"Unsupported consolidated-fact state: {self.state}")
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
class DreamCommit:
    """Replayable write set for one Dream lifecycle commit."""

    commit_id: str
    run_id: str
    status: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"prepared", "applying", "complete"}:
            raise ValueError(f"Unsupported Dream commit status: {self.status}")
        if not self.commit_id or not self.run_id or not self.payload:
            raise ValueError("Dream commits require identity and a replay payload")


@dataclass
class ReconsolidationProposal:
    proposal_id: str
    incoming_claim_ids: list[str]
    target_claim_ids: list[str]
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
        self.incoming_claim_ids = sorted(set(self.incoming_claim_ids))
        self.target_claim_ids = sorted(set(self.target_claim_ids))
        if not self.incoming_claim_ids or not self.target_claim_ids:
            raise ValueError("A reconsolidation proposal requires both claim sides")
        if set(self.incoming_claim_ids) & set(self.target_claim_ids):
            raise ValueError("A reconsolidation proposal requires distinct claim sides")
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
class ExtractionSegmentDisposition:
    segment_id: str
    disposition: str
    claim_ids: list[str] = field(default_factory=list)
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in {"claimed", "source_only", "claim_pending"}:
            raise ValueError(f"Unsupported extraction disposition: {self.disposition}")
        self.claim_ids = list(dict.fromkeys(self.claim_ids))
        if self.disposition == "claimed" and not self.claim_ids:
            raise ValueError("Claimed segments require at least one claim")
        if self.disposition != "claimed" and self.claim_ids:
            raise ValueError("Only claimed segments can reference claims")
        if self.disposition in {"source_only", "claim_pending"} and not str(
            self.reason or ""
        ).strip():
            raise ValueError(f"{self.disposition} segments require a reason")


@dataclass
class ExtractionBatchState:
    batch_id: str
    batch_index: int
    segment_ids: list[str]
    claim_bearing_segment_ids: list[str] = field(default_factory=list)
    coverage_status: str = "pending"
    claim_status: str = "pending"
    attempt_count: int = 0
    last_error: str | None = None

    def __post_init__(self) -> None:
        self.segment_ids = list(dict.fromkeys(self.segment_ids))
        self.claim_bearing_segment_ids = list(
            dict.fromkeys(self.claim_bearing_segment_ids)
        )
        if not self.segment_ids:
            raise ValueError("Extraction batches require source segments")
        if not set(self.claim_bearing_segment_ids) <= set(self.segment_ids):
            raise ValueError("Claim-bearing segments must belong to their batch")
        if self.coverage_status not in {"pending", "complete", "failed"}:
            raise ValueError(f"Unsupported coverage status: {self.coverage_status}")
        if self.claim_status not in {
            "pending", "not_required", "complete", "failed"
        }:
            raise ValueError(f"Unsupported claim status: {self.claim_status}")
        if self.claim_status in {"not_required", "complete"} and (
            self.coverage_status != "complete"
        ):
            raise ValueError("Terminal claim status requires complete coverage")
        if self.claim_status == "not_required" and self.claim_bearing_segment_ids:
            raise ValueError("A source-only batch cannot have claim-bearing segments")


@dataclass
class EpisodeManifest:
    episode_id: str
    source_id: str
    source_type: str
    occurred_at: str | None
    participants: list[str]
    segment_ids: list[str]
    claim_ids: list[str] = field(default_factory=list)
    segment_dispositions: list[ExtractionSegmentDisposition] = field(default_factory=list)
    extraction_batches: list[ExtractionBatchState] = field(default_factory=list)
    extraction_status: str = "pending"
    extraction_error: str | None = None


@dataclass
class IngestionOperation:
    """Durable identity and progress for one source-ingestion request."""

    operation_id: str
    idempotency_key: str
    input_digest: str
    entry_id: str
    source_id: str
    episode_id: str
    status: str
    created_at: str
    updated_at: str
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"planned", "extracting", "complete", "failed"}:
            raise ValueError(f"Unsupported ingestion operation status: {self.status}")
        if not all((
            self.operation_id,
            self.idempotency_key,
            self.input_digest,
            self.entry_id,
            self.source_id,
            self.episode_id,
        )):
            raise ValueError("Ingestion operations require stable identities")


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
