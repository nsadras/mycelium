"""Structured response contracts used by production LLM calls."""

from collections.abc import Collection, Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import ClaimType, DiscoverableEntityType


class ExtractedEntityOutput(BaseModel):
    entity: str
    role: str | None = None


class ExtractedClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_key: str = Field(pattern=r"^C[0-9]{3}$")
    text: str = Field(min_length=1, max_length=1000)
    claim_type: ClaimType = "unknown"
    predicate: str | None = None
    evidence_modality: Literal[
        "speech", "visual", "tool", "mixed", "unknown"
    ] = "speech"
    temporal_status: Literal[
        "past", "current", "future", "recurring", "atemporal", "unknown"
    ] = "unknown"
    temporal_anchor_segment_id: str | None = None
    about: list[ExtractedEntityOutput] = Field(min_length=1, max_length=12)
    segment_ids: list[str] = Field(min_length=1, max_length=32)
    speaker: str | None = None
    evidence_type: Literal["explicit", "inferred"] = "explicit"
    confidence: float = 0.8
    slot: str | None = None
    facets: dict = Field(default_factory=dict)


class ExtractedClaimedSegmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: str
    disposition: Literal["claimed"]
    claim_keys: list[str] = Field(min_length=1, max_length=128)


class ExtractedSourceOnlySegmentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: str
    disposition: Literal["source_only"]
    claim_keys: list[str] = Field(max_length=0)
    reason: str = Field(min_length=1, max_length=500)


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
    claimed_disposition = create_model(
        "BatchExtractedClaimedSegmentOutput",
        __base__=ExtractedClaimedSegmentOutput,
        segment_id=(segment_id_type, ...),  # type: ignore[valid-type]
    )
    source_only_disposition = create_model(
        "BatchExtractedSourceOnlySegmentOutput",
        __base__=ExtractedSourceOnlySegmentOutput,
        segment_id=(segment_id_type, ...),  # type: ignore[valid-type]
    )
    disposition_union = Annotated[
        Union[claimed_disposition, source_only_disposition],
        Field(discriminator="disposition"),
    ]
    base_model = create_model(
        "BatchExtractedEpisodeOutput",
        __config__=ConfigDict(extra="forbid"),
        claims=(
            list[claim_model],  # type: ignore[valid-type]
            Field(max_length=128),
        ),
        segment_dispositions=(
            list[disposition_union],  # type: ignore[valid-type]
            Field(min_length=len(segment_ids), max_length=len(segment_ids)),
        ),
    )

    class ExactBatchExtractedEpisodeOutput(base_model):  # type: ignore[valid-type, misc]
        @model_validator(mode="after")
        def validate_complete_segment_accounting(self):
            dispositions = self.segment_dispositions
            disposition_ids = [item.segment_id for item in dispositions]
            if len(disposition_ids) != len(set(disposition_ids)):
                raise ValueError("Each supplied segment requires exactly one disposition")
            if set(disposition_ids) != set(segment_ids):
                raise ValueError("Every supplied segment requires a disposition")

            claims_by_key = {claim.claim_key: claim for claim in self.claims}
            if len(claims_by_key) != len(self.claims):
                raise ValueError("Extraction claim keys must be unique")
            linked_claim_keys: set[str] = set()
            evidence_links: dict[str, set[str]] = {
                key: set() for key in claims_by_key
            }
            for disposition in dispositions:
                for claim_key in disposition.claim_keys:
                    claim = claims_by_key.get(claim_key)
                    if claim is None:
                        raise ValueError(
                            f"Segment disposition references unknown claim key {claim_key}"
                        )
                    linked_claim_keys.add(claim_key)
                    evidence_links[claim_key].add(disposition.segment_id)
            if linked_claim_keys != set(claims_by_key):
                raise ValueError("Every extracted claim requires a segment disposition link")
            for claim_key, claim in claims_by_key.items():
                if evidence_links[claim_key] != set(claim.segment_ids):
                    raise ValueError(
                        f"Claim {claim_key} evidence and segment dispositions disagree"
                    )
            return self

    return ExactBatchExtractedEpisodeOutput


class GroundedAnswerOutput(BaseModel):
    answerable: bool
    answer: str
    evidence: str | None = None


class SubjectGraphNodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(pattern=r"^N[0-9]{3}$")
    title: str = Field(min_length=1, max_length=160)
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)
    participant_evidence: list[str] = Field(max_length=48)


class IdentityMatchGroupOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity_key: str = Field(pattern=r"^I[0-9]{3}$")
    node_ids: list[str] = Field(min_length=1, max_length=32)
    preferred_title: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(max_length=12)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


class IdentityTypeProposalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: DiscoverableEntityType
    reason: str = Field(min_length=1, max_length=500)
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)


class IdentityTypeVerdictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["supported", "ambiguous", "unsupported"]
    alternative_types: list[DiscoverableEntityType] = Field(max_length=8)
    reason: str = Field(min_length=1, max_length=500)
    supporting_evidence: list[str] = Field(min_length=1, max_length=48)

    @model_validator(mode="after")
    def validate_alternatives(self):
        if self.verdict == "supported" and self.alternative_types:
            raise ValueError("Supported type verdicts cannot list alternatives")
        if self.verdict != "supported" and not self.alternative_types:
            raise ValueError("Ambiguous and unsupported verdicts require alternatives")
        return self


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
    fact_key: str = Field(pattern=r"^F[0-9]{3}$")


class FactPresentationOutput(BaseModel):
    """One presentation fact for a fixed claim group."""
    model_config = ConfigDict(extra="forbid")
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


def fact_truth_output_model(claim_aliases: Collection[str]) -> type[BaseModel]:
    """Build a compact owner-wide truth-change decision."""
    claims = tuple(dict.fromkeys(str(value) for value in claim_aliases if value))
    if not claims:
        raise ValueError("Fact truth resolution requires claim aliases")
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
    base_model = create_model(
        "ExactFactTruthPlan",
        __config__=ConfigDict(extra="forbid"),
        truth_changes=(list[exact_change], Field(default_factory=list, max_length=48)),
    )

    class ExactFactTruthPlan(base_model):  # type: ignore[valid-type, misc]
        @model_validator(mode="after")
        def validate_disjoint_changes(self):
            changed: set[str] = set()
            for change in self.truth_changes:
                incoming = set(change.incoming_claim_aliases)
                targets = set(change.target_claim_aliases)
                if incoming & targets or changed & (incoming | targets):
                    raise ValueError(
                        "Truth-change claim sides must be distinct and non-overlapping"
                    )
                changed.update(incoming | targets)
            return self

    return ExactFactTruthPlan


def fact_grouping_output_model(
    claim_aliases: Collection[str],
    truth_changes: Collection[Mapping[str, Any]],
) -> type[BaseModel]:
    """Build exact compact claim-to-fact assignments after truth adjudication."""
    claims = tuple(dict.fromkeys(str(value) for value in claim_aliases if value))
    if not claims:
        raise ValueError("Fact grouping requires claim aliases")
    assignments_model = create_model(
        "ExactFactClaimAssignments",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (FactClaimAssignmentOutput, ...) for alias in claims},
    )
    base_model = create_model(
        "ExactFactGroupingPlan",
        __config__=ConfigDict(extra="forbid"),
        assignments=(assignments_model, ...),
    )
    change_sides = [
        (
            tuple(str(value) for value in change["incoming_claim_aliases"]),
            tuple(str(value) for value in change["target_claim_aliases"]),
        )
        for change in truth_changes
    ]

    class ExactFactGroupingPlan(base_model):  # type: ignore[valid-type, misc]
        @model_validator(mode="after")
        def validate_truth_change_separation(self):
            assignments = self.assignments.model_dump()
            for incoming, targets in change_sides:
                incoming_keys = {assignments[alias]["fact_key"] for alias in incoming}
                target_keys = {assignments[alias]["fact_key"] for alias in targets}
                if incoming_keys & target_keys:
                    raise ValueError("Truth-change sides cannot share a fact")
            return self

    return ExactFactGroupingPlan


def fact_rendering_output_model(
    fact_keys: Collection[str],
    allowed_sections: Collection[str],
) -> type[BaseModel]:
    """Build exact presentation definitions for one bounded group batch."""
    keys = tuple(dict.fromkeys(str(value) for value in fact_keys if value))
    sections = tuple(dict.fromkeys(str(value) for value in allowed_sections if value))
    if not keys or not sections:
        raise ValueError("Fact rendering requires fact keys and allowed sections")
    section_type = Literal.__getitem__(sections)
    presentation = create_model(
        "ExactFactPresentation",
        __base__=FactPresentationOutput,
        section_key=(section_type, ...),  # type: ignore[valid-type]
    )
    facts_model = create_model(
        "ExactFactPresentations",
        __config__=ConfigDict(extra="forbid"),
        **{key: (presentation, ...) for key in keys},
    )
    return create_model(
        "ExactFactRenderingPlan",
        __config__=ConfigDict(extra="forbid"),
        facts=(facts_model, ...),
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


def identity_matching_output_model(
    node_ids: Collection[str],
    existing_entity_ids: Collection[str],
) -> type[BaseModel]:
    """Build an exact identity partition before any type or scope decision."""
    nodes = tuple(dict.fromkeys(str(value) for value in node_ids if value))
    existing = tuple(
        dict.fromkeys(str(value) for value in existing_entity_ids if value)
    )
    if not nodes:
        raise ValueError("Identity matching requires subject nodes")
    node_type = Literal.__getitem__(nodes)
    common_fields: dict[str, Any] = {
        "node_ids": (
            list[node_type],  # type: ignore[valid-type]
            Field(min_length=1, max_length=len(nodes)),
        ),
    }
    variants: list[type[BaseModel]] = [create_model(
        "NewIdentityMatchGroup",
        __base__=IdentityMatchGroupOutput,
        resolution=(Literal["new"], ...),
        entity_id=(Literal[""], ...),
        candidate_entity_ids=(list[str], Field(max_length=0)),
        **common_fields,
    )]
    if existing:
        existing_type = Literal.__getitem__(existing)
        variants.extend([
            create_model(
                "ExistingIdentityMatchGroup",
                __base__=IdentityMatchGroupOutput,
                resolution=(Literal["existing"], ...),
                entity_id=(existing_type, ...),  # type: ignore[valid-type]
                candidate_entity_ids=(list[str], Field(max_length=0)),
                **common_fields,
            ),
            create_model(
                "ReviewIdentityMatchGroup",
                __base__=IdentityMatchGroupOutput,
                resolution=(Literal["review_required"], ...),
                entity_id=(Literal[""], ...),
                candidate_entity_ids=(
                    list[existing_type],  # type: ignore[valid-type]
                    Field(min_length=1, max_length=len(existing)),
                ),
                **common_fields,
            ),
        ])
    group_union = Annotated[
        Union.__getitem__(tuple(variants)),
        Field(discriminator="resolution"),
    ]
    base_model = create_model(
        "ExactIdentityMatchingPlan",
        __config__=ConfigDict(extra="forbid"),
        identities=(list[group_union], Field(min_length=1, max_length=len(nodes))),
    )

    class ExactIdentityMatchingPlan(base_model):  # type: ignore[valid-type, misc]
        @model_validator(mode="after")
        def validate_identity_partition(self):
            grouped_nodes = [
                node_id for group in self.identities for node_id in group.node_ids
            ]
            if len(grouped_nodes) != len(set(grouped_nodes)):
                raise ValueError("Identity groups cannot share subject nodes")
            if set(grouped_nodes) != set(nodes):
                raise ValueError("Identity groups must exactly partition subject nodes")
            identity_keys = [group.identity_key for group in self.identities]
            if len(identity_keys) != len(set(identity_keys)):
                raise ValueError("Identity keys must be unique")
            resolved_ids = [
                group.entity_id
                for group in self.identities
                if group.resolution == "existing"
            ]
            if len(resolved_ids) != len(set(resolved_ids)):
                raise ValueError(
                    "An existing entity can belong to only one identity group"
                )
            return self

    return ExactIdentityMatchingPlan


def identity_type_output_model(
    identity_evidence: Mapping[str, Collection[str]],
) -> type[BaseModel]:
    """Build exact type proposals for unresolved identity groups."""
    fields: dict[str, Any] = {}
    for identity_key, evidence in identity_evidence.items():
        evidence_values = tuple(dict.fromkeys(str(value) for value in evidence))
        evidence_type = Literal.__getitem__(evidence_values)
        fields[str(identity_key)] = (create_model(
            f"{identity_key}TypeProposal",
            __base__=IdentityTypeProposalOutput,
            supporting_evidence=(
                list[evidence_type],  # type: ignore[valid-type]
                Field(min_length=1, max_length=len(evidence_values)),
            ),
        ), ...)
    decisions_model = create_model(
        "ExactIdentityTypeProposals",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return create_model(
        "ExactIdentityTypePlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )


def identity_type_verification_output_model(
    proposals: Mapping[str, str],
    identity_evidence: Mapping[str, Collection[str]],
) -> type[BaseModel]:
    """Build exact independent verdicts for proposed ontology types."""
    fields: dict[str, Any] = {}
    for identity_key, proposed_type in proposals.items():
        evidence_values = tuple(
            dict.fromkeys(str(value) for value in identity_evidence[identity_key])
        )
        evidence_type = Literal.__getitem__(evidence_values)
        alternatives = tuple(
            value for value in DiscoverableEntityType.__args__
            if value != proposed_type
        )
        alternative_type = Literal.__getitem__(alternatives)
        fields[str(identity_key)] = (create_model(
            f"{identity_key}TypeVerdict",
            __base__=IdentityTypeVerdictOutput,
            alternative_types=(
                list[alternative_type],  # type: ignore[valid-type]
                Field(max_length=len(alternatives)),
            ),
            supporting_evidence=(
                list[evidence_type],  # type: ignore[valid-type]
                Field(min_length=1, max_length=len(evidence_values)),
            ),
        ), ...)
    decisions_model = create_model(
        "ExactIdentityTypeVerdicts",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return create_model(
        "ExactIdentityTypeVerification",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
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
    matched_entity_ids: Mapping[str, str] | None = None,
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
    matched_entity_ids = matched_entity_ids or {}
    materialization_bases = materialization_bases or {}
    review_required_nodes = set(review_required_nodes)
    for node_id, node_type in node_types.items():
        matched_id = matched_entity_ids.get(node_id)
        adjudication_values = (
            ("accepted",)
            if matched_id
            else (
                ("review_required",)
                if node_id in review_required_nodes
                else ("accepted", "review_required")
            )
        )
        adjudication_type = Literal.__getitem__(adjudication_values)
        entity_id_type = Literal.__getitem__((matched_id,) if matched_id else ("",))
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
