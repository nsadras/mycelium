"""Structured response contracts used by production LLM calls."""

from collections.abc import Collection, Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model


class ExtractedEntityOutput(BaseModel):
    entity: str
    role: str | None = None


class ExtractedClaimOutput(BaseModel):
    text: str
    kind: str = "fact"
    claim_type: Literal[
        "identity", "state", "event", "preference", "plan", "belief",
        "relationship", "decision", "commitment", "interaction", "observation",
        "unknown",
    ] = "unknown"
    predicate: str | None = None
    evidence_modality: Literal[
        "speech", "visual", "tool", "inference", "mixed", "unknown"
    ] = "speech"
    temporal_status: Literal[
        "past", "current", "future", "recurring", "atemporal", "unknown"
    ] = "unknown"
    about: list[ExtractedEntityOutput] = Field(default_factory=list, max_length=12)
    segment_ids: list[str] = Field(min_length=1, max_length=32)
    speaker: str | None = None
    evidence_type: Literal["explicit", "inferred"] = "explicit"
    confidence: float = 0.8
    slot: str | None = None
    facets: dict = Field(default_factory=dict)


class ExtractedEpisodeOutput(BaseModel):
    claims: list[ExtractedClaimOutput] = Field(max_length=128)
    ignored_segment_ids: list[str] = Field(max_length=256)


def extraction_output_model(
    allowed_segment_ids: Collection[str],
) -> type[BaseModel]:
    """Build a retryable structured contract scoped to one extraction batch."""
    segment_ids = tuple(sorted({str(value) for value in allowed_segment_ids if value}))
    if not segment_ids:
        raise ValueError("Extraction output requires at least one allowed segment ID")
    segment_id_type = Literal.__getitem__(segment_ids)
    claim_model = create_model(
        "BatchExtractedClaimOutput",
        __base__=ExtractedClaimOutput,
        segment_ids=(
            list[segment_id_type],  # type: ignore[valid-type]
            Field(min_length=1, max_length=32),
        ),
    )
    return create_model(
        "BatchExtractedEpisodeOutput",
        __base__=ExtractedEpisodeOutput,
        claims=(
            list[claim_model],  # type: ignore[valid-type]
            Field(max_length=128),
        ),
        ignored_segment_ids=(
            list[segment_id_type],  # type: ignore[valid-type]
            Field(max_length=256),
        ),
    )


class GroundedAnswerOutput(BaseModel):
    answerable: bool
    answer: str
    evidence: str | None = None


class RoutingSelectionOutput(BaseModel):
    page: str
    priority: int
    reason: str | None = None


class RoutingOutput(RootModel[list[RoutingSelectionOutput]]):
    root: list[RoutingSelectionOutput] = Field(default_factory=list, max_length=8)


class _EntityCandidateBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list, max_length=12)


class PersonCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["person"]
    creation_basis: Literal["durable_person"]


class ProjectCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["project"]
    creation_basis: Literal["project_continuity"]


class TopicCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["topic"]
    creation_basis: Literal["intentional_topic", "topic_evidence"]


class OrganizationCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["organization"]
    creation_basis: Literal["lasting_organization"]


class PlaceCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["place"]
    creation_basis: Literal["lasting_place"]


class EventCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["event"]
    creation_basis: Literal["substantial_event"]


EntityCandidateOutput = Annotated[
    PersonCandidateOutput | ProjectCandidateOutput | TopicCandidateOutput
    | OrganizationCandidateOutput | PlaceCandidateOutput | EventCandidateOutput,
    Field(discriminator="entity_type"),
]


class EntityDiscoveryDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: EntityCandidateOutput | None = None
    reason: str = Field(min_length=1, max_length=500)


class ScopeEntityCandidateOutput(BaseModel):
    """One globally defined candidate used by cohort claim assignments."""

    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(pattern=r"^N[0-9]{3}$")
    title: str = Field(min_length=1, max_length=160)
    entity_type: Literal[
        "person", "project", "topic", "organization", "place", "event"
    ]
    aliases: list[str] = Field(default_factory=list, max_length=12)
    creation_basis: Literal[
        "meeting_participant", "durable_person", "named_project",
        "project_continuity", "intentional_topic",
        "topic_evidence", "lasting_organization", "lasting_place",
        "substantial_event",
    ]
    supporting_claims: list[str] = Field(default_factory=list, max_length=48)
    supporting_participants: list[str] = Field(default_factory=list, max_length=48)
    independent_scope: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class CanonicalScopeAssignmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disposition: Literal["canonical"]
    owner_entity: str = Field(min_length=1, max_length=160)
    linked_entities: list[str] = Field(default_factory=list, max_length=12)
    supporting_claims: list[str] = Field(default_factory=list, max_length=48)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class NoncanonicalScopeAssignmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disposition: Literal["deferred", "source_only"]
    supporting_claims: list[str] = Field(default_factory=list, max_length=48)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


ScopeAssignmentOutput = Annotated[
    CanonicalScopeAssignmentOutput | NoncanonicalScopeAssignmentOutput,
    Field(discriminator="disposition"),
]


class UserParticipantResolutionOutput(BaseModel):
    """Resolve a structurally labelled user speaker to the singleton You entity."""

    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["you"]
    entity: Literal["you"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class PersonParticipantResolutionOutput(BaseModel):
    """Resolve a non-user meeting speaker to a Person entity reference."""

    model_config = ConfigDict(extra="forbid")
    entity_type: Literal["person"]
    entity: str = Field(min_length=1, max_length=160)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


ParticipantScopeResolutionOutput = (
    UserParticipantResolutionOutput | PersonParticipantResolutionOutput
)


class CohortScopePlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[ScopeEntityCandidateOutput] = Field(
        default_factory=list, max_length=24
    )
    assignments: dict[str, ScopeAssignmentOutput]
    participants: dict[str, ParticipantScopeResolutionOutput] = Field(
        default_factory=dict
    )


class ConsolidatedFactGroupOutput(BaseModel):
    """A presentation-level grouping of compatible claims in one fixed scope."""

    model_config = ConfigDict(extra="forbid")
    claim_aliases: list[str] = Field(min_length=1, max_length=48)
    text: str = Field(min_length=1, max_length=600)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class ConsolidatedFactPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[ConsolidatedFactGroupOutput] = Field(min_length=1, max_length=96)


def cohort_scope_output_model(
    evidence_aliases: Collection[str],
    participant_aliases: Collection[str] | Mapping[str, str | None] = (),
) -> type[BaseModel]:
    """Build a cohort contract with exact assignment keys visible to guided decoding."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    if not aliases:
        raise ValueError("Cohort scope planning requires at least one evidence alias")
    assignment_fields: dict[str, Any] = {
        alias: (ScopeAssignmentOutput, ...) for alias in aliases
    }
    assignments_model = create_model(
        "ExactCohortAssignments",
        __config__=ConfigDict(extra="forbid"),
        **assignment_fields,
    )
    participant_roles = (
        {str(alias): role for alias, role in participant_aliases.items() if alias}
        if isinstance(participant_aliases, Mapping)
        else {str(alias): None for alias in participant_aliases if alias}
    )
    participant_fields: dict[str, Any] = {
        alias: ((
            UserParticipantResolutionOutput
            if str(role or "").lower() == "user"
            else PersonParticipantResolutionOutput
        ), ...)
        for alias, role in participant_roles.items()
    }
    participants_model = create_model(
        "ExactCohortParticipants",
        __config__=ConfigDict(extra="forbid"),
        **participant_fields,
    )
    return create_model(
        "ExactCohortScopePlan",
        __config__=ConfigDict(extra="forbid"),
        candidates=(
            list[ScopeEntityCandidateOutput],
            Field(default_factory=list, max_length=24),
        ),
        assignments=(assignments_model, ...),
        participants=(participants_model, ...),
    )


def entity_discovery_output_model(
    evidence_aliases: Collection[str],
) -> type[BaseModel]:
    """Require one entity-creation decision for each unresolved claim."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    if not aliases:
        raise ValueError("Entity discovery requires at least one evidence alias")
    fields: dict[str, Any] = {
        alias: (EntityDiscoveryDecisionOutput, ...) for alias in aliases
    }
    return create_model(
        "SourceEntityDiscoveryOutput",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


class ClaimPlacementOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_entity: str = Field(default="", max_length=160)
    linked_entities: list[str] = Field(default_factory=list, max_length=12)
    reason: str = Field(min_length=1, max_length=500)


def placement_output_model(
    evidence_aliases: Collection[str],
) -> type[BaseModel]:
    """Build an exact source-scoped claim-placement contract."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    if not aliases:
        raise ValueError("Consolidation output requires at least one evidence alias")
    fields: dict[str, Any] = {
        alias: (ClaimPlacementOutput, ...)
        for alias in aliases
    }
    return create_model(
        "SourcePlacementOutput",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


# The old slug-routing schema was intentionally removed. Keep one import name while
# call sites transition in the same release; it resolves to the new contract rather
# than accepting the old wire shape.
consolidation_output_model = placement_output_model


class ReconsolidationDecisionOutput(BaseModel):
    incoming_alias: str
    relation: Literal["additive", "supports", "contradicts", "supersedes"]
    target_alias: str = ""
    explanation: str
    confidence: float = 0.8


class ReconsolidationDecisionsOutput(BaseModel):
    decisions: list[ReconsolidationDecisionOutput] = Field(default_factory=list, max_length=32)
