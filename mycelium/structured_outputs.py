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
    temporal_anchor_segment_id: str | None = None
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
        temporal_anchor_segment_id=(
            segment_id_type | None,  # type: ignore[valid-type, operator]
            None,
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


class SubjectGraphNodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^N[0-9]{3}$")
    title: str = Field(min_length=1, max_length=160)
    entity_type: Literal[
        "person", "project", "topic", "organization", "place", "event"
    ]
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)
    reason: str = Field(min_length=1, max_length=500)


class SubjectGraphEdgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_node: str = Field(min_length=1, max_length=160)
    target_node: str = Field(min_length=1, max_length=160)
    relation: Literal[
        "component_of", "participant_in", "about", "located_at", "related_to"
    ]
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)
    reason: str = Field(min_length=1, max_length=500)


class IdentityResolutionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(max_length=160)
    preferred_title: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(max_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class GraphAdmissionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_role: Literal["independent", "component", "incidental"]
    continuity: Literal["established", "emerging", "not_applicable"]
    reason: str = Field(min_length=1, max_length=500)


class IdentityMatchVerificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    same_identity: bool
    reason: str = Field(min_length=1, max_length=500)


class ClaimOwnerDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_entity: str = Field(max_length=160)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class ClaimReferenceDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_entity: str = Field(max_length=160)
    object_entities: list[str] = Field(max_length=12)
    contextual_entities: list[str] = Field(max_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


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


class SubjectGraphPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[SubjectGraphNodeOutput] = Field(max_length=32)
    edges: list[SubjectGraphEdgeOutput] = Field(max_length=64)
    participants: dict[str, ParticipantScopeResolutionOutput]


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


def subject_graph_output_model(
    participant_aliases: Collection[str] | Mapping[str, str | None] = (),
    *,
    evidence_aliases: Collection[str] = (),
    existing_entity_types: Mapping[str, str] | None = None,
) -> type[BaseModel]:
    """Build a graph contract with exact evidence, registry, and participant values."""
    existing_entity_types = existing_entity_types or {}
    participant_roles = (
        {str(alias): role for alias, role in participant_aliases.items() if alias}
        if isinstance(participant_aliases, Mapping)
        else {str(alias): None for alias in participant_aliases if alias}
    )
    node_ref = Annotated[str, Field(pattern=r"^N[0-9]{3}$")]
    person_ids = tuple(
        entity_id
        for entity_id, entity_type in existing_entity_types.items()
        if entity_type == "person"
    )
    person_ref = (
        node_ref | Literal.__getitem__(person_ids)
        if person_ids
        else node_ref
    )
    exact_person_participant = create_model(
        "ExactPersonParticipantResolution",
        __base__=PersonParticipantResolutionOutput,
        entity=(person_ref, ...),
    )
    participant_fields: dict[str, Any] = {}
    for alias, role in participant_roles.items():
        participant_fields[alias] = (
            UserParticipantResolutionOutput
            if str(role or "").lower() == "user"
            else exact_person_participant,
            ...,
        )
    participants_model = create_model(
        "ExactCohortParticipants",
        __config__=ConfigDict(extra="forbid"),
        **participant_fields,
    )
    evidence_values = tuple(str(alias) for alias in evidence_aliases if alias)
    evidence_ref = (
        Literal.__getitem__(evidence_values) if evidence_values else str
    )
    graph_node = create_model(
        "ExactEvidenceSubjectGraphNode",
        __base__=SubjectGraphNodeOutput,
        supporting_evidence=(
            list[evidence_ref],  # type: ignore[valid-type]
            Field(min_length=1, max_length=48),
        ),
    )
    stable_endpoints = tuple(sorted({"you", *existing_entity_types}))
    endpoint_ref = node_ref | Literal.__getitem__(stable_endpoints)
    graph_edge = create_model(
        "ExactEndpointSubjectGraphEdge",
        __base__=SubjectGraphEdgeOutput,
        source_node=(endpoint_ref, ...),
        target_node=(endpoint_ref, ...),
        supporting_evidence=(
            list[evidence_ref],  # type: ignore[valid-type]
            Field(min_length=1, max_length=48),
        ),
    )
    return create_model(
        "ExactSubjectGraphPlan",
        __config__=ConfigDict(extra="forbid"),
        nodes=(list[graph_node], Field(max_length=32)),
        edges=(list[graph_edge], Field(max_length=64)),
        participants=(participants_model, ...),
    )


def identity_resolution_output_model(
    candidate_types: Mapping[str, str],
    existing_entity_types: Mapping[str, str],
) -> type[BaseModel]:
    """Build same-type exact identity decisions for graph nodes."""
    resolution_fields: dict[str, Any] = {}
    for candidate_id, candidate_type in candidate_types.items():
        same_type_ids = tuple(
            entity_id
            for entity_id, entity_type in existing_entity_types.items()
            if entity_type == candidate_type
            or (candidate_type == "person" and entity_type == "you")
        )
        entity_id_type = Literal.__getitem__(("", *same_type_ids))
        decision_model = create_model(
            f"{candidate_id}SameTypeIdentityResolution",
            __base__=IdentityResolutionOutput,
            entity_id=(entity_id_type, ...),  # type: ignore[valid-type]
        )
        resolution_fields[str(candidate_id)] = (decision_model, ...)
    resolutions_model = create_model(
        "ExactSameTypeIdentityResolutions",
        __config__=ConfigDict(extra="forbid"),
        **resolution_fields,
    )
    return create_model(
        "ExactGraphIdentityResolutionPlan",
        __config__=ConfigDict(extra="forbid"),
        resolutions=(resolutions_model, ...),
    )


def graph_admission_output_model(
    node_ids: Collection[str],
) -> type[BaseModel]:
    """Build exact memory-role and continuity decisions for graph nodes."""
    admission_fields: dict[str, Any] = {
        str(node_id): (GraphAdmissionOutput, ...) for node_id in node_ids
    }
    admissions_model = create_model(
        "ExactGraphAdmissions",
        __config__=ConfigDict(extra="forbid"),
        **admission_fields,
    )
    return create_model(
        "ExactGraphAdmissionPlan",
        __config__=ConfigDict(extra="forbid"),
        admissions=(admissions_model, ...),
    )


def identity_verification_output_model(
    candidate_ids: Collection[str],
) -> type[BaseModel]:
    """Build exact pairwise verification decisions for proposed identity matches."""
    verification_fields: dict[str, Any] = {
        str(candidate_id): (IdentityMatchVerificationOutput, ...)
        for candidate_id in candidate_ids
    }
    verifications_model = create_model(
        "ExactIdentityMatchVerifications",
        __config__=ConfigDict(extra="forbid"),
        **verification_fields,
    )
    return create_model(
        "ExactIdentityVerificationPlan",
        __config__=ConfigDict(extra="forbid"),
        verifications=(verifications_model, ...),
    )


def claim_owner_output_model(
    evidence_aliases: Collection[str],
    entity_ids: Collection[str],
) -> type[BaseModel]:
    """Build an owner-only contract limited to the completed registry."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    if not aliases:
        raise ValueError("Claim ownership requires at least one evidence alias")
    registry_ids = tuple(dict.fromkeys(str(value) for value in entity_ids if value))
    if not registry_ids:
        raise ValueError("Claim ownership requires at least one entity ID")
    owner_type = Literal.__getitem__((*registry_ids, ""))
    decision_model = create_model(
        "RegistryClaimOwnerDecision",
        __base__=ClaimOwnerDecisionOutput,
        owner_entity=(owner_type, ...),  # type: ignore[valid-type]
    )
    assignment_fields: dict[str, Any] = {
        alias: (decision_model, ...) for alias in aliases
    }
    assignments_model = create_model(
        "ExactClaimOwnerAssignments",
        __config__=ConfigDict(extra="forbid"),
        **assignment_fields,
    )
    return create_model(
        "ExactClaimOwnerPlan",
        __config__=ConfigDict(extra="forbid"),
        assignments=(assignments_model, ...),
    )


def claim_reference_output_model(
    evidence_aliases: Collection[str],
    entity_ids: Collection[str],
) -> type[BaseModel]:
    """Build a stable endpoint-role contract for already-owned claims."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    if not aliases:
        raise ValueError("Claim references require at least one evidence alias")
    registry_ids = tuple(dict.fromkeys(str(value) for value in entity_ids if value))
    if not registry_ids:
        raise ValueError("Claim references require at least one entity ID")
    entity_type = Literal.__getitem__(registry_ids)
    subject_type = Literal.__getitem__(("", *registry_ids))
    decision_model = create_model(
        "RegistryClaimReferenceDecision",
        __base__=ClaimReferenceDecisionOutput,
        subject_entity=(subject_type, ...),  # type: ignore[valid-type]
        object_entities=(
            list[entity_type],  # type: ignore[valid-type]
            Field(max_length=12),
        ),
        contextual_entities=(
            list[entity_type],  # type: ignore[valid-type]
            Field(max_length=12),
        ),
    )
    reference_fields: dict[str, Any] = {
        alias: (decision_model, ...) for alias in aliases
    }
    references_model = create_model(
        "ExactClaimReferences",
        __config__=ConfigDict(extra="forbid"),
        **reference_fields,
    )
    return create_model(
        "ExactClaimReferencePlan",
        __config__=ConfigDict(extra="forbid"),
        references=(references_model, ...),
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
