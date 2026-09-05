"""Structured response contracts used by production LLM calls."""

from collections.abc import Collection, Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import (
    ClaimType,
)


class ExtractedEntityOutput(BaseModel):
    entity: str
    role: str | None = None


class ExtractedClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


def extraction_output_model(
    segment_ids: Collection[str], context_segment_ids: Collection[str] = (),
) -> type[BaseModel]:
    """Extract and account for every new segment in one validated response."""
    ids = tuple(sorted(set(segment_ids)))
    if not ids:
        raise ValueError("Extraction requires source segments")
    id_type = Literal.__getitem__(ids)
    disposition = create_model(
        "ExtractionDisposition", __config__=ConfigDict(extra="forbid"),
        segment_id=(id_type, ...),
        disposition=(Literal["claimed", "source_only"], ...),
        reason=(str, Field(min_length=1, max_length=500)),
    )
    fields = {}
    if context_segment_ids:
        context_type = Literal.__getitem__(tuple(sorted(set(context_segment_ids))))
        fields["context_segment_ids"] = (list[context_type], Field(
            description="Exact earlier-context evidence IDs used to resolve or support this statement. Required; empty only if the new segments support the entire statement independently."
        ))
    claim = create_model(
        "ExtractedStatement", __base__=ExtractedClaimOutput,
        segment_ids=(list[id_type], Field(min_length=1, max_length=32)),
        temporal_anchor_segment_id=(id_type | None, None),
        **fields,
    )
    base = create_model(
        "ExtractionResponse", __config__=ConfigDict(extra="forbid"),
        segment_dispositions=(list[disposition], Field(min_length=len(ids), max_length=len(ids))),
        claims=(list[claim], Field(max_length=128)),
    )

    class ExactExtractionResponse(base):
        @model_validator(mode="after")
        def validate_accounting(self):
            supplied = [d.segment_id for d in self.segment_dispositions]
            if len(supplied) != len(set(supplied)) or set(supplied) != set(ids):
                raise ValueError("Every source segment requires exactly one disposition")
            claimed = {d.segment_id for d in self.segment_dispositions if d.disposition == "claimed"}
            cited = {s for c in self.claims for s in c.segment_ids}
            if claimed != cited:
                raise ValueError("Claim citations must cover exactly the segments marked claimed")
            return self

    return ExactExtractionResponse


class GroundedAnswerOutput(BaseModel):
    answerable: bool
    answer: str
    evidence: str | None = None


class AssistantContextCandidateDecisionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disposition: Literal["include", "exclude"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)


def assistant_context_selection_output_model(
    candidate_aliases: Collection[str],
) -> type[BaseModel]:
    """Require an explicit relevance disposition for every supplied candidate."""
    aliases = tuple(sorted({str(value) for value in candidate_aliases if value}))
    if not aliases:
        raise ValueError("Context selection requires at least one candidate alias")
    decisions_model = create_model(
        "AssistantContextCandidateDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{
            alias: (AssistantContextCandidateDecisionOutput, ...)
            for alias in aliases
        },
    )
    return create_model(
        "AssistantContextSelectionOutput",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )


class FactClaimAssignmentOutput(BaseModel):
    """Assign one exact claim alias to one output fact key."""

    model_config = ConfigDict(extra="forbid")
    fact_key: str = Field(pattern=r"^F[0-9]{3}$")


class FactCandidateSelectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_fact_ids: list[str] = Field(max_length=12)
    reason: str = Field(min_length=1, max_length=800)


class FactPresentationOutput(BaseModel):
    """One presentation fact for a fixed claim group."""
    model_config = ConfigDict(extra="forbid")
    state: Literal["current", "history"]
    section_key: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=800)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=800)


class FactQualityVerdictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["supported", "unsupported"]
    reason: str = Field(min_length=1, max_length=800)


class FactGroupQualityVerdictOutput(BaseModel):
    """Whether one proposed claim group can be represented by one display fact."""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["equivalent", "composable", "split_required"]
    reason: str = Field(min_length=1, max_length=800)


class FactTruthNoChangeOutput(BaseModel):
    """An incoming claim that does not change an accepted truth."""

    model_config = ConfigDict(extra="forbid")
    disposition: Literal["no_change"]
    reason: str = Field(min_length=1, max_length=800)
    confidence: float = Field(ge=0.0, le=1.0)


class FactTruthChangeOutput(BaseModel):
    """An unsafe truth change that must be reviewed before claim mutation."""

    model_config = ConfigDict(extra="forbid")
    disposition: Literal["truth_change"]
    relation: Literal["contradicts", "supersedes"]
    target_claim_aliases: list[str] = Field(min_length=1, max_length=48)
    durable_field: str = Field(min_length=1, max_length=200)
    prior_state: str = Field(min_length=1, max_length=300)
    incoming_state: str = Field(min_length=1, max_length=300)
    transition_evidence: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=800)
    confidence: float = Field(ge=0.0, le=1.0)


def fact_truth_output_model(
    incoming_claim_aliases: Collection[str],
    target_claim_aliases: Collection[str],
) -> type[BaseModel]:
    """Build one exact truth adjudication for every incoming claim alias."""
    incoming = tuple(dict.fromkeys(
        str(value) for value in incoming_claim_aliases if value
    ))
    targets = tuple(dict.fromkeys(
        str(value) for value in target_claim_aliases if value
    ))
    if not incoming:
        raise ValueError("Fact truth resolution requires incoming claim aliases")
    decision_fields: dict[str, Any] = {}
    for alias in incoming:
        no_change = create_model(
            f"{alias}FactTruthNoChange",
            __base__=FactTruthNoChangeOutput,
        )
        if not targets:
            decision_fields[alias] = (no_change, ...)
            continue
        target_type = Literal.__getitem__(targets)
        truth_change = create_model(
            f"{alias}FactTruthChange",
            __base__=FactTruthChangeOutput,
            target_claim_aliases=(
                list[target_type],  # type: ignore[valid-type]
                Field(min_length=1, max_length=len(targets)),
            ),
        )
        decision_fields[alias] = (
            Annotated[
                Union[no_change, truth_change],
                Field(discriminator="disposition"),
            ],
            ...,
        )
    decisions_model = create_model(
        "ExactFactTruthDecisions",
        __config__=ConfigDict(extra="forbid"),
        **decision_fields,
    )
    base_model = create_model(
        "ExactFactTruthPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )

    class ExactFactTruthPlan(base_model):  # type: ignore[valid-type, misc]
        @model_validator(mode="after")
        def validate_noncompeting_targets(self):
            changed_targets: set[str] = set()
            for decision in self.decisions:
                if decision[1].disposition != "truth_change":
                    continue
                decision_targets = set(decision[1].target_claim_aliases)
                if changed_targets & decision_targets:
                    raise ValueError(
                        "Incoming truth changes cannot compete for the same target claim"
                    )
                changed_targets.update(decision_targets)
            return self

    return ExactFactTruthPlan


def fact_candidate_selection_output_model(
    incoming_claim_aliases: Collection[str],
    prior_fact_aliases: Collection[str],
) -> type[BaseModel]:
    """Select bounded prior fact candidates for every incoming claim."""
    incoming = tuple(dict.fromkeys(
        str(value) for value in incoming_claim_aliases if value
    ))
    facts = tuple(dict.fromkeys(
        str(value) for value in prior_fact_aliases if value
    ))
    if not incoming or not facts:
        raise ValueError("Fact candidate selection requires claims and prior facts")
    fact_type = Literal.__getitem__(facts)
    decision = create_model(
        "ExactFactCandidateSelection",
        __base__=FactCandidateSelectionOutput,
        candidate_fact_ids=(
            list[fact_type],  # type: ignore[valid-type]
            Field(max_length=len(facts)),
        ),
    )
    decisions = create_model(
        "ExactFactCandidateDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (decision, ...) for alias in incoming},
    )
    return create_model(
        "ExactFactCandidatePlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions, ...),
    )


def fact_grouping_output_model(
    claim_aliases: Collection[str],
    truth_changes: Collection[Mapping[str, Any]],
) -> type[BaseModel]:
    """Build exact compact claim-to-fact assignments after truth adjudication."""
    claims = tuple(dict.fromkeys(str(value) for value in claim_aliases if value))
    if not claims:
        raise ValueError("Fact grouping requires claim aliases")
    protected_fact_keys: dict[str, str] = {}
    next_fact_index = 1
    for change in truth_changes:
        target_key = f"F{next_fact_index:03d}"
        next_fact_index += 1
        incoming_key = f"F{next_fact_index:03d}"
        next_fact_index += 1
        protected_fact_keys.update({
            str(alias): target_key
            for alias in change["target_claim_aliases"]
        })
        protected_fact_keys.update({
            str(alias): incoming_key
            for alias in change["incoming_claim_aliases"]
        })
    assignment_fields: dict[str, Any] = {}
    for alias in claims:
        protected_key = protected_fact_keys.get(alias)
        assignment = FactClaimAssignmentOutput
        if protected_key is not None:
            assignment = create_model(
                f"{alias}ProtectedFactAssignment",
                __base__=FactClaimAssignmentOutput,
                fact_key=(Literal.__getitem__((protected_key,)), ...),
            )
        assignment_fields[alias] = (assignment, ...)
    assignments_model = create_model(
        "ExactFactClaimAssignments",
        __config__=ConfigDict(extra="forbid"),
        **assignment_fields,
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
    fixed_text_by_key: Mapping[str, str] | None = None,
) -> type[BaseModel]:
    """Build exact presentation definitions for one bounded group batch."""
    keys = tuple(dict.fromkeys(str(value) for value in fact_keys if value))
    sections = tuple(dict.fromkeys(str(value) for value in allowed_sections if value))
    if not keys or not sections:
        raise ValueError("Fact rendering requires fact keys and allowed sections")
    section_type = Literal.__getitem__(sections)
    fixed_text_by_key = fixed_text_by_key or {}
    presentations = {}
    for key in keys:
        fields: dict[str, Any] = {
            "section_key": (section_type, ...),  # type: ignore[valid-type]
        }
        if key in fixed_text_by_key:
            text_type = Literal.__getitem__((fixed_text_by_key[key],))
            fields["text"] = (text_type, ...)
        presentations[key] = create_model(
            f"{key}ExactFactPresentation",
            __base__=FactPresentationOutput,
            **fields,
        )
    facts_model = create_model(
        "ExactFactPresentations",
        __config__=ConfigDict(extra="forbid"),
        **{key: (presentations[key], ...) for key in keys},
    )
    return create_model(
        "ExactFactRenderingPlan",
        __config__=ConfigDict(extra="forbid"),
        facts=(facts_model, ...),
    )


def fact_group_quality_output_model(
    fact_keys: Collection[str],
) -> type[BaseModel]:
    """Build exact compatibility verdicts for proposed multi-claim groups."""
    keys = tuple(dict.fromkeys(str(value) for value in fact_keys if value))
    if not keys:
        raise ValueError("Fact group verification requires fact keys")
    decisions = create_model(
        "ExactFactGroupQualityDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{key: (FactGroupQualityVerdictOutput, ...) for key in keys},
    )
    return create_model(
        "ExactFactGroupQualityPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions, ...),
    )


def fact_quality_output_model(fact_keys: Collection[str]) -> type[BaseModel]:
    keys = tuple(dict.fromkeys(str(value) for value in fact_keys if value))
    if not keys:
        raise ValueError("Fact quality verification requires fact keys")
    decisions = create_model(
        "ExactFactQualityDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{key: (FactQualityVerdictOutput, ...) for key in keys},
    )
    return create_model(
        "ExactFactQualityPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions, ...),
    )


def fact_repair_output_model(
    rendered_facts: Mapping[str, Mapping[str, Any]],
) -> type[BaseModel]:
    if not rendered_facts:
        raise ValueError("Fact repair requires rejected facts")
    fields: dict[str, Any] = {}
    for key, fact in rendered_facts.items():
        presentation = create_model(
            f"{key}ExactFactRepair",
            __base__=FactPresentationOutput,
            state=(Literal.__getitem__((str(fact["state"]),)), ...),
            section_key=(Literal.__getitem__((str(fact["section_key"]),)), ...),
        )
        fields[str(key)] = (presentation, ...)
    facts = create_model(
        "ExactFactRepairs",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return create_model(
        "ExactFactRepairPlan",
        __config__=ConfigDict(extra="forbid"),
        facts=(facts, ...),
    )
