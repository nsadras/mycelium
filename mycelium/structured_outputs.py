"""Structured response contracts used by production LLM calls."""

from collections.abc import Collection, Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import ClaimType, DiscoverableEntityType


class ExtractedEntityOutput(BaseModel):
    entity: str
    role: str | None = None


class ExtractedClaimOutput(BaseModel):
    text: str
    claim_type: ClaimType = "unknown"
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
    entity_type: DiscoverableEntityType
    type_adjudication: Literal["accepted", "review_required"]
    type_reason: str = Field(min_length=1, max_length=500)
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)
    participant_evidence: list[str] = Field(max_length=48)


class IdentityMaturityDecisionOutput(BaseModel):
    """Fields shared by an isolated page-admission decision."""

    model_config = ConfigDict(extra="forbid")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class IdentityMaturityBasisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IdentityMaturityVerdictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["supported", "unsupported", "not_required"]
    reason: str = Field(min_length=1, max_length=500)


class EntityPlanDecisionOutput(BaseModel):
    """Fields shared by every structurally valid identity-scope decision."""

    model_config = ConfigDict(extra="forbid")
    preferred_title: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(max_length=12)
    adjudication: Literal["accepted", "review_required"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class ClaimRoutingDecisionOutput(BaseModel):
    """Fields shared by every structurally valid owner-routing decision."""

    model_config = ConfigDict(extra="forbid")
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


class FactClaimAssignmentOutput(BaseModel):
    """Assign one exact claim alias to one output fact key."""

    model_config = ConfigDict(extra="forbid")
    fact_key: str = Field(min_length=1, max_length=80)


class FactResolutionGroupOutput(BaseModel):
    """One presentation fact referenced by exact claim assignments."""

    model_config = ConfigDict(extra="forbid")
    fact_key: str = Field(min_length=1, max_length=80)
    state: Literal["current", "history"]
    section_key: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=800)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=800)


class FactTruthChangeOutput(BaseModel):
    """An unsafe truth change that must be reviewed before claim mutation."""

    model_config = ConfigDict(extra="forbid")
    relation: Literal["contradicts", "supersedes"]
    incoming_claim_aliases: list[str] = Field(min_length=1, max_length=48)
    target_claim_aliases: list[str] = Field(min_length=1, max_length=48)
    explanation: str = Field(min_length=1, max_length=800)
    confidence: float = Field(ge=0.0, le=1.0)


class FactResolutionPlanOutput(BaseModel):
    """Complete owner-scoped truth and presentation decision."""

    model_config = ConfigDict(extra="forbid")
    assignments: dict[str, FactClaimAssignmentOutput]
    facts: list[FactResolutionGroupOutput] = Field(min_length=1, max_length=128)
    truth_changes: list[FactTruthChangeOutput] = Field(default_factory=list, max_length=48)

    @model_validator(mode="after")
    def validate_complete_fact_graph(self):
        fact_keys = [fact.fact_key for fact in self.facts]
        if len(fact_keys) != len(set(fact_keys)):
            raise ValueError("Fact keys must be unique")
        assignments = (
            self.assignments.model_dump()
            if isinstance(self.assignments, BaseModel)
            else self.assignments
        )
        assigned_keys = {
            str(assignment["fact_key"]) for assignment in assignments.values()
        }
        if assigned_keys != set(fact_keys):
            raise ValueError(
                "Every assigned fact key must have exactly one used definition"
            )
        changed: set[str] = set()
        for change in self.truth_changes:
            incoming = set(change.incoming_claim_aliases)
            targets = set(change.target_claim_aliases)
            if incoming & targets or changed & (incoming | targets):
                raise ValueError(
                    "Truth-change claim sides must be distinct and non-overlapping"
                )
            incoming_keys = {assignments[alias]["fact_key"] for alias in incoming}
            target_keys = {assignments[alias]["fact_key"] for alias in targets}
            if incoming_keys & target_keys:
                raise ValueError("Truth-change sides cannot share a fact")
            changed.update(incoming | targets)
        return self


def fact_resolution_output_model(
    claim_aliases: Collection[str],
    allowed_sections: Collection[str],
) -> type[BaseModel]:
    """Build an owner-scoped plan that structurally accounts for every claim."""
    claims = tuple(dict.fromkeys(str(value) for value in claim_aliases if value))
    sections = tuple(dict.fromkeys(str(value) for value in allowed_sections if value))
    if not claims or not sections:
        raise ValueError("Fact resolution requires claim aliases and allowed sections")
    assignments_model = create_model(
        "ExactFactClaimAssignments",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (FactClaimAssignmentOutput, ...) for alias in claims},
    )
    section_type = Literal.__getitem__(sections)
    exact_fact = create_model(
        "ExactFactResolutionGroup",
        __base__=FactResolutionGroupOutput,
        section_key=(section_type, ...),  # type: ignore[valid-type]
    )
    claim_type = Literal.__getitem__(claims)
    exact_change = create_model(
        "ExactFactTruthChange",
        __base__=FactTruthChangeOutput,
        incoming_claim_aliases=(
            list[claim_type],  # type: ignore[valid-type]
            Field(min_length=1, max_length=48),
        ),
        target_claim_aliases=(
            list[claim_type],  # type: ignore[valid-type]
            Field(min_length=1, max_length=48),
        ),
    )
    return create_model(
        "ExactFactResolutionPlan",
        __base__=FactResolutionPlanOutput,
        assignments=(assignments_model, ...),
        facts=(list[exact_fact], Field(min_length=1, max_length=128)),
        truth_changes=(list[exact_change], Field(default_factory=list, max_length=48)),
    )


def subject_node_output_model(
    evidence_aliases: Collection[str],
    participant_aliases: Collection[str] = (),
) -> type[BaseModel]:
    """Build an evidence-constrained subject census before relationship planning."""
    evidence_values = tuple(str(alias) for alias in evidence_aliases if alias)
    if not evidence_values:
        raise ValueError("Subject node planning requires evidence aliases")
    evidence_ref = Literal.__getitem__(evidence_values)
    participant_values = tuple(str(alias) for alias in participant_aliases if alias)
    participant_field = (
        (
            list[Literal.__getitem__(participant_values)],  # type: ignore[valid-type]
            Field(max_length=48),
        )
        if participant_values
        else (list[str], Field(max_length=0))
    )
    graph_node = create_model(
        "ExactEvidenceSubjectNode",
        __base__=SubjectGraphNodeOutput,
        supporting_evidence=(
            list[evidence_ref],  # type: ignore[valid-type]
            Field(min_length=1, max_length=48),
        ),
        participant_evidence=participant_field,
    )
    return create_model(
        "ExactSubjectNodePlan",
        __config__=ConfigDict(extra="forbid"),
        nodes=(list[graph_node], Field(max_length=32)),
    )


def identity_maturity_output_model(
    allowed_bases: Mapping[str, Collection[str]],
    evidence_aliases: Collection[str],
) -> type[BaseModel]:
    """Build exact keyed page-admission decisions for fixed subject nodes."""
    decision_fields: dict[str, Any] = {}
    for node_id, bases in allowed_bases.items():
        provisional = create_model(
            f"{node_id}ProvisionalMaturityDecision",
            __base__=IdentityMaturityDecisionOutput,
            admission=(Literal["provisional"], ...),
        )
        variants: list[type[BaseModel]] = [provisional]
        basis_values = tuple(dict.fromkeys(str(value) for value in bases))
        if basis_values:
            basis_variants: list[type[BaseModel]] = []
            for basis in basis_values:
                fields: dict[str, Any] = {
                    "continuity_basis": (Literal.__getitem__((basis,)), ...),
                }
                if basis == "explicit_prior_history":
                    evidence_values = tuple(str(value) for value in evidence_aliases)
                    evidence_type = Literal.__getitem__(evidence_values)
                    fields.update({
                        "prior_state": (str, Field(min_length=1, max_length=500)),
                        "prior_evidence": (
                            list[evidence_type],  # type: ignore[valid-type]
                            Field(min_length=1, max_length=48),
                        ),
                        "continuation_state": (
                            str, Field(min_length=1, max_length=500),
                        ),
                        "continuation_evidence": (
                            list[evidence_type],  # type: ignore[valid-type]
                            Field(min_length=1, max_length=48),
                        ),
                    })
                basis_variants.append(create_model(
                    f"{node_id}{basis.title().replace('_', '')}Basis",
                    __base__=IdentityMaturityBasisOutput,
                    **fields,
                ))
            basis_union = Annotated[
                Union.__getitem__(tuple(basis_variants)),
                Field(discriminator="continuity_basis"),
            ]
            variants.append(create_model(
                f"{node_id}MaterializedMaturityDecision",
                __base__=IdentityMaturityDecisionOutput,
                admission=(Literal["materialized"], ...),
                basis=(basis_union, ...),
            ))
        decision_fields[str(node_id)] = (
            Annotated[
                Union.__getitem__(tuple(variants)),
                Field(discriminator="admission"),
            ],
            ...,
        )
    decisions_model = create_model(
        "ExactIdentityMaturityDecisions",
        __config__=ConfigDict(extra="forbid"),
        **decision_fields,
    )
    return create_model(
        "ExactIdentityMaturityPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )


def identity_maturity_verification_output_model(
    explicit_nodes: Collection[str],
    all_nodes: Collection[str],
) -> type[BaseModel]:
    explicit_nodes = set(explicit_nodes)
    fields: dict[str, Any] = {}
    for node_id in all_nodes:
        verdict_values = (
            ("supported", "unsupported")
            if node_id in explicit_nodes
            else ("not_required",)
        )
        fields[str(node_id)] = (create_model(
            f"{node_id}MaturityVerdict",
            __base__=IdentityMaturityVerdictOutput,
            verdict=(Literal.__getitem__(verdict_values), ...),
        ), ...)
    decisions_model = create_model(
        "ExactIdentityMaturityVerdicts",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return create_model(
        "ExactIdentityMaturityVerification",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )
def entity_plan_output_model(
    node_types: Mapping[str, str],
    participant_roles: Mapping[str, str | None],
    existing_entity_types: Mapping[str, str],
    reviewed_entity_ids: Mapping[str, str] | None = None,
    materialization_bases: Mapping[str, Collection[str]] | None = None,
    review_required_nodes: Collection[str] = (),
) -> type[BaseModel]:
    """Build identity variants whose schema already enforces scope invariants."""
    node_ids = tuple(str(value) for value in node_types)
    existing_ids = tuple(str(value) for value in existing_entity_types)
    parent_ids = tuple(
        value
        for value in (*node_ids, *existing_ids)
        if node_types.get(value) in {"project", "series"}
        or existing_entity_types.get(value) in {"project", "series"}
    )
    decision_fields: dict[str, Any] = {}
    reviewed_entity_ids = reviewed_entity_ids or {}
    materialization_bases = materialization_bases or {}
    review_required_nodes = set(review_required_nodes)
    for node_id, node_type in node_types.items():
        reviewed_id = reviewed_entity_ids.get(node_id)
        adjudication_values = (
            ("accepted",)
            if reviewed_id
            else (
                ("review_required",)
                if node_id in review_required_nodes
                else ("accepted", "review_required")
            )
        )
        adjudication_type = Literal.__getitem__(adjudication_values)
        same_type_ids = (
            (reviewed_id,)
            if reviewed_id
            else tuple(
                entity_id
                for entity_id, entity_type in existing_entity_types.items()
                if entity_type == node_type
                or (node_type == "person" and entity_type == "you")
            )
        )
        entity_id_type = Literal.__getitem__(
            same_type_ids if reviewed_id else ("", *same_type_ids)
        )
        provisional_model = create_model(
            f"{node_id}ProvisionalEntityDecision",
            __base__=EntityPlanDecisionOutput,
            scope=(Literal["provisional"], ...),
            entity_id=(entity_id_type, ...),  # type: ignore[valid-type]
            parent_entity=(Literal[""], ...),
            adjudication=(adjudication_type, ...),  # type: ignore[valid-type]
        )
        context_model = create_model(
            f"{node_id}ContextEntityDecision",
            __base__=EntityPlanDecisionOutput,
            scope=(Literal["context"], ...),
            entity_id=(entity_id_type, ...),  # type: ignore[valid-type]
            parent_entity=(Literal[""], ...),
            adjudication=(adjudication_type, ...),  # type: ignore[valid-type]
        )
        variants: list[type[BaseModel]] = [provisional_model, context_model]
        continuity_values = tuple(materialization_bases.get(node_id, ()))
        if continuity_values:
            continuity_type = Literal.__getitem__(continuity_values)
            variants.insert(0, create_model(
                f"{node_id}MaterializedEntityDecision",
                __base__=EntityPlanDecisionOutput,
                scope=(Literal["materialized"], ...),
                entity_id=(entity_id_type, ...),  # type: ignore[valid-type]
                parent_entity=(Literal[""], ...),
                continuity_basis=(continuity_type, ...),  # type: ignore[valid-type]
                adjudication=(adjudication_type, ...),  # type: ignore[valid-type]
            ))
        if node_type == "event":
            variants.append(create_model(
                f"{node_id}StandaloneEventDecision",
                __base__=EntityPlanDecisionOutput,
                scope=(Literal["standalone_event"], ...),
                entity_id=(entity_id_type, ...),  # type: ignore[valid-type]
                parent_entity=(Literal[""], ...),
                adjudication=(adjudication_type, ...),  # type: ignore[valid-type]
            ))
        allowed_parents = tuple(value for value in parent_ids if value != node_id)
        if allowed_parents:
            parent_type = Literal.__getitem__(allowed_parents)
            scope_value = "occurrence" if node_type == "event" else "component"
            scope_type = Literal.__getitem__((scope_value,))
            contained_model = create_model(
                f"{node_id}ContainedEntityDecision",
                __base__=EntityPlanDecisionOutput,
                scope=(scope_type, ...),  # type: ignore[valid-type]
                entity_id=(entity_id_type, ...),  # type: ignore[valid-type]
                parent_entity=(parent_type, ...),  # type: ignore[valid-type]
                adjudication=(adjudication_type, ...),  # type: ignore[valid-type]
            )
            variants.append(contained_model)
        decision_union = Annotated[
            Union.__getitem__(tuple(variants)),
            Field(discriminator="scope"),
        ]
        decision_fields[str(node_id)] = (decision_union, ...)
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
    entity_types: Mapping[str, str],
) -> type[BaseModel]:
    """Build owner routes whose variants enforce downstream relationship rules."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    entity_ids = tuple(str(value) for value in entity_types)
    if not aliases:
        raise ValueError("Claim routing requires evidence aliases")
    deferred_model = create_model(
        "DeferredClaimRoute",
        __base__=ClaimRoutingDecisionOutput,
        route_kind=(Literal["deferred"], ...),
    )
    variants: list[type[BaseModel]] = [deferred_model]
    if entity_ids:
        owner_type = Literal.__getitem__(entity_ids)
        subject_type = Literal.__getitem__(("", *entity_ids))
        entity_type = Literal.__getitem__(entity_ids)
        variants.append(create_model(
            "GeneralClaimRoute",
            __base__=ClaimRoutingDecisionOutput,
            route_kind=(Literal["general"], ...),
            owner_entity=(owner_type, ...),  # type: ignore[valid-type]
            relationship_kind=(Literal["other", "none"], ...),
            subject_entity=(subject_type, ...),  # type: ignore[valid-type]
            object_entities=(
                list[entity_type],  # type: ignore[valid-type]
                Field(max_length=12),
            ),
            contextual_entities=(
                list[entity_type],  # type: ignore[valid-type]
                Field(max_length=12),
            ),
        ))
        person_ids = tuple(
            entity_id for entity_id, entity_type_name in entity_types.items()
            if entity_type_name in {"person", "you"}
        )
        project_ids = tuple(
            entity_id for entity_id, entity_type_name in entity_types.items()
            if entity_type_name == "project"
        )
        if person_ids and project_ids:
            person_type = Literal.__getitem__(person_ids)
            project_type = Literal.__getitem__(project_ids)
            variants.append(create_model(
                "ProjectRoleClaimRoute",
                __base__=ClaimRoutingDecisionOutput,
                route_kind=(Literal["project_role"], ...),
                owner_entity=(person_type, ...),  # type: ignore[valid-type]
                project_entity=(project_type, ...),  # type: ignore[valid-type]
            ))
    decision_union = Annotated[
        Union.__getitem__(tuple(variants)),
        Field(discriminator="route_kind"),
    ]
    decisions_model = create_model(
        "ExactClaimRoutingDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (decision_union, ...) for alias in aliases},
    )
    return create_model(
        "ExactClaimRoutingPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )
