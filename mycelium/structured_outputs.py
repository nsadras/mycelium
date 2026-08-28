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


class SeriesCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["series"]
    creation_basis: Literal["recurring_series"]


class ArtifactCandidateOutput(_EntityCandidateBase):
    entity_type: Literal["artifact"]
    creation_basis: Literal["lasting_artifact"]


EntityCandidateOutput = Annotated[
    PersonCandidateOutput | ProjectCandidateOutput | TopicCandidateOutput
    | OrganizationCandidateOutput | PlaceCandidateOutput | EventCandidateOutput
    | SeriesCandidateOutput | ArtifactCandidateOutput,
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
        "person", "project", "series", "event", "artifact", "topic",
        "organization", "place",
    ]
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)


class SubjectGraphEdgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_node: str = Field(min_length=1, max_length=160)
    target_node: str = Field(min_length=1, max_length=160)
    relation: Literal[
        "component_of", "occurrence_of", "participant_in", "about",
        "located_at", "uses", "produced_by", "related_to",
    ]
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)


class IdentityResolutionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(max_length=160)
    preferred_title: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(max_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class GraphAdmissionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_role: Literal["independent", "component", "context_only"]
    memory_evidence: Literal["accumulating", "thin", "unclear"]
    evidence_maturity: Literal["established", "emerging"]
    reason: str = Field(min_length=1, max_length=500)


class IdentityMatchVerificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    same_identity: bool
    reason: str = Field(min_length=1, max_length=500)


class SeriesSubjecthoodOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classification: Literal[
        "independent_recurring_frame", "personal_attribute_or_context"
    ]
    reason: str = Field(min_length=1, max_length=500)


class ClaimOwnerDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_entity: str = Field(max_length=160)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class ClaimSectionDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: str = Field(max_length=160)
    reason: str = Field(min_length=1, max_length=500)


class ClaimReferenceDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationship_kind: Literal["project_role", "other", "none"]
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


def subject_node_output_model(
    evidence_aliases: Collection[str],
) -> type[BaseModel]:
    """Build an evidence-constrained subject census before relationship planning."""
    evidence_values = tuple(str(alias) for alias in evidence_aliases if alias)
    if not evidence_values:
        raise ValueError("Subject node planning requires evidence aliases")
    evidence_ref = Literal.__getitem__(evidence_values)
    graph_node = create_model(
        "ExactEvidenceSubjectNode",
        __base__=SubjectGraphNodeOutput,
        supporting_evidence=(
            list[evidence_ref],  # type: ignore[valid-type]
            Field(min_length=1, max_length=48),
        ),
    )
    return create_model(
        "ExactSubjectNodePlan",
        __config__=ConfigDict(extra="forbid"),
        nodes=(list[graph_node], Field(max_length=32)),
    )


def subject_relationship_output_model(
    node_types: Mapping[str, str],
    participant_roles: Mapping[str, str | None],
    evidence_aliases: Collection[str],
    existing_entity_types: Mapping[str, str],
) -> type[BaseModel]:
    """Constrain the subject hierarchy and participants to a declared census."""
    node_ids = tuple(str(value) for value in node_types)
    stable_ids = tuple(str(value) for value in existing_entity_types)
    endpoints = tuple(dict.fromkeys((*node_ids, *stable_ids)))
    if not endpoints:
        raise ValueError("Subject relationships require declared endpoints")
    evidence_values = tuple(str(alias) for alias in evidence_aliases if alias)
    evidence_ref = Literal.__getitem__(evidence_values)
    graph_edge: type[BaseModel] = SubjectGraphEdgeOutput
    if node_ids:
        source_type = Literal.__getitem__(node_ids)
        parent_ids = tuple(
            endpoint
            for endpoint in endpoints
            if node_types.get(endpoint) in {"project", "series"}
            or existing_entity_types.get(endpoint) in {"project", "series"}
        )
        target_type = Literal.__getitem__(parent_ids or endpoints)
        graph_edge = create_model(
            "ExactDeclaredSubjectEdge",
            __base__=SubjectGraphEdgeOutput,
            source_node=(source_type, ...),  # type: ignore[valid-type]
            target_node=(target_type, ...),  # type: ignore[valid-type]
            relation=(Literal["component_of", "occurrence_of"], ...),
            supporting_evidence=(
                list[evidence_ref],  # type: ignore[valid-type]
                Field(min_length=1, max_length=48),
            ),
        )
    person_refs = tuple(
        value
        for value in endpoints
        if node_types.get(value) == "person"
        or existing_entity_types.get(value) == "person"
    )
    participant_fields: dict[str, Any] = {}
    for alias, role in participant_roles.items():
        if str(role or "").lower() == "user":
            participant_fields[str(alias)] = (UserParticipantResolutionOutput, ...)
            continue
        if not person_refs:
            raise ValueError("Non-user participants require a declared Person endpoint")
        person_type = Literal.__getitem__(person_refs)
        exact_person = create_model(
            f"ExactParticipant{alias}",
            __base__=PersonParticipantResolutionOutput,
            entity=(person_type, ...),  # type: ignore[valid-type]
        )
        participant_fields[str(alias)] = (exact_person, ...)
    participants_model = create_model(
        "ExactDeclaredParticipants",
        __config__=ConfigDict(extra="forbid"),
        **participant_fields,
    )
    return create_model(
        "ExactSubjectRelationshipPlan",
        __config__=ConfigDict(extra="forbid"),
        edges=(list[graph_edge], Field(max_length=len(node_ids))),
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
    *,
    contained_node_ids: Collection[str] = (),
    context_only_node_ids: Collection[str] = (),
) -> type[BaseModel]:
    """Build exact scope-role and personal-memory decisions for graph nodes."""
    contained = {str(node_id) for node_id in contained_node_ids}
    context_only = {str(node_id) for node_id in context_only_node_ids}
    admission_fields: dict[str, Any] = {}
    for node_id in node_ids:
        node_id = str(node_id)
        decision_model = GraphAdmissionOutput
        if node_id in contained:
            decision_model = create_model(
                f"{node_id}ContainedGraphAdmission",
                __base__=GraphAdmissionOutput,
                scope_role=(Literal["component"], ...),
            )
        elif node_id in context_only:
            decision_model = create_model(
                f"{node_id}ContextGraphAdmission",
                __base__=GraphAdmissionOutput,
                scope_role=(Literal["context_only"], ...),
            )
        admission_fields[node_id] = (decision_model, ...)
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


def series_subjecthood_output_model(node_id: str) -> type[BaseModel]:
    """Build one exact recurring-frame verification decision."""
    decisions_model = create_model(
        "ExactSeriesSubjecthoodDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{str(node_id): (SeriesSubjecthoodOutput, ...)},
    )
    return create_model(
        "ExactSeriesSubjecthoodPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
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


def claim_section_output_model(
    section_options: Mapping[str, Collection[str]],
) -> type[BaseModel]:
    """Build a per-claim section contract after ownership is fixed."""
    section_fields: dict[str, Any] = {}
    for alias, values in section_options.items():
        sections = tuple(dict.fromkeys(str(value) for value in values))
        if not sections:
            raise ValueError(f"Claim section options are empty for {alias}")
        section_type = Literal.__getitem__(sections)
        decision_model = create_model(
            f"ClaimSectionDecision{alias}",
            __base__=ClaimSectionDecisionOutput,
            section=(section_type, ...),  # type: ignore[valid-type]
        )
        section_fields[str(alias)] = (decision_model, ...)
    if not section_fields:
        raise ValueError("Claim section planning requires at least one evidence alias")
    sections_model = create_model(
        "ExactClaimSectionAssignments",
        __config__=ConfigDict(extra="forbid"),
        **section_fields,
    )
    return create_model(
        "ExactClaimSectionPlan",
        __config__=ConfigDict(extra="forbid"),
        sections=(sections_model, ...),
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
