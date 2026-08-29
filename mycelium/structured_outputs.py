"""Structured response contracts used by production LLM calls."""

from collections.abc import Collection, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model


class ExtractedEntityOutput(BaseModel):
    entity: str
    role: str | None = None


class ExtractedClaimOutput(BaseModel):
    text: str
    claim_type: Literal[
        "identity", "state", "event", "preference", "plan", "belief",
        "relationship", "decision", "commitment", "interaction", "observation",
        "unknown",
    ] = "unknown"
    predicate: str | None = None
    evidence_modality: Literal[
        "speech", "visual", "tool", "mixed", "unknown"
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


class SubjectGraphNodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^N[0-9]{3}$")
    title: str = Field(min_length=1, max_length=160)
    entity_type: Literal[
        "person", "project", "series", "event", "artifact", "topic",
        "organization", "place",
    ]
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)


class EntityPlanDecisionOutput(BaseModel):
    """One coherent identity, containment, and page-state decision."""

    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(max_length=160)
    preferred_title: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(max_length=12)
    parent_entity: str = Field(max_length=160)
    containment: Literal["component_of", "occurrence_of", "none"]
    page_state: Literal["materialized", "provisional", "no_page"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class ClaimRoutingDecisionOutput(BaseModel):
    """One coherent owner, relationship, and page-section decision."""

    model_config = ConfigDict(extra="forbid")
    owner_entity: str = Field(max_length=160)
    section: str = Field(max_length=160)
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


def entity_plan_output_model(
    node_types: Mapping[str, str],
    participant_roles: Mapping[str, str | None],
    existing_entity_types: Mapping[str, str],
) -> type[BaseModel]:
    """Build one exact identity, containment, admission, and participant plan."""
    node_ids = tuple(str(value) for value in node_types)
    existing_ids = tuple(str(value) for value in existing_entity_types)
    parent_ids = tuple(
        value
        for value in (*node_ids, *existing_ids)
        if node_types.get(value) in {"project", "series"}
        or existing_entity_types.get(value) in {"project", "series"}
    )
    parent_type = Literal.__getitem__(("", *parent_ids))
    decision_fields: dict[str, Any] = {}
    for node_id, node_type in node_types.items():
        same_type_ids = tuple(
            entity_id
            for entity_id, entity_type in existing_entity_types.items()
            if entity_type == node_type
            or (node_type == "person" and entity_type == "you")
        )
        entity_id_type = Literal.__getitem__(("", *same_type_ids))
        decision_model = create_model(
            f"{node_id}EntityPlanDecision",
            __base__=EntityPlanDecisionOutput,
            entity_id=(entity_id_type, ...),  # type: ignore[valid-type]
            parent_entity=(parent_type, ...),  # type: ignore[valid-type]
        )
        decision_fields[str(node_id)] = (decision_model, ...)
    decisions_model = create_model(
        "ExactEntityPlanDecisions",
        __config__=ConfigDict(extra="forbid"),
        **decision_fields,
    )

    person_refs = tuple(
        value
        for value in (*node_ids, *existing_ids)
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
        "ExactEntityPlanParticipants",
        __config__=ConfigDict(extra="forbid"),
        **participant_fields,
    )
    return create_model(
        "ExactEntityPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
        participants=(participants_model, ...),
    )


def claim_routing_output_model(
    evidence_aliases: Collection[str],
    entity_sections: Mapping[str, Collection[str]],
) -> type[BaseModel]:
    """Build exact unified owner, relationship, and section decisions."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    entity_ids = tuple(str(value) for value in entity_sections)
    if not aliases or not entity_ids:
        raise ValueError("Claim routing requires evidence aliases and entity IDs")
    owner_type = Literal.__getitem__(("", *entity_ids))
    subject_type = Literal.__getitem__(("", *entity_ids))
    entity_type = Literal.__getitem__(entity_ids)
    sections = tuple(dict.fromkeys(
        section
        for values in entity_sections.values()
        for section in values
    ))
    section_type = Literal.__getitem__(("", *sections))
    decision_model = create_model(
        "RegistryClaimRoutingDecision",
        __base__=ClaimRoutingDecisionOutput,
        owner_entity=(owner_type, ...),  # type: ignore[valid-type]
        section=(section_type, ...),  # type: ignore[valid-type]
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
    decisions_model = create_model(
        "ExactClaimRoutingDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (decision_model, ...) for alias in aliases},
    )
    return create_model(
        "ExactClaimRoutingPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )


class ReconsolidationDecisionOutput(BaseModel):
    incoming_alias: str
    relation: Literal["additive", "supports", "contradicts", "supersedes"]
    target_alias: str = ""
    explanation: str
    confidence: float = 0.8


class ReconsolidationDecisionsOutput(BaseModel):
    decisions: list[ReconsolidationDecisionOutput] = Field(default_factory=list, max_length=32)
