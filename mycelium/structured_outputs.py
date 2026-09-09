"""Structured response contracts used by production LLM calls."""

from collections import Counter
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
    evidence_modality: Literal["speech", "visual", "tool", "mixed", "unknown"] = (
        "speech"
    )
    temporal_status: Literal[
        "past", "current", "future", "recurring", "atemporal", "unknown"
    ]
    temporal_anchor_segment_id: str | None = None
    about: list[ExtractedEntityOutput] = Field(min_length=1, max_length=12)
    segment_ids: list[str] = Field(min_length=1, max_length=32)
    speaker: str | None = None
    evidence_type: Literal["explicit", "inferred"] = "explicit"
    confidence: float = 0.8
    slot: str | None = None
    facets: dict = Field(default_factory=dict)


def extraction_output_model(
    segment_ids: Collection[str],
    context_segment_ids: Collection[str] = (),
) -> type[BaseModel]:
    """Extract and account for every new segment in one validated response."""
    ids = tuple(sorted(set(segment_ids)))
    if not ids:
        raise ValueError("Extraction requires source segments")
    id_type = Literal.__getitem__(ids)
    source_only = create_model(
        "SourceOnlySegment",
        __config__=ConfigDict(extra="forbid"),
        segment_id=(id_type, ...),
        reason=(str, Field(min_length=1, max_length=500)),
    )
    fields = {}
    if context_segment_ids:
        context_type = Literal.__getitem__(tuple(sorted(set(context_segment_ids))))
        fields["context_segment_ids"] = (
            list[context_type],
            Field(
                description="Exact earlier-context evidence IDs used to resolve or support this statement. Required; empty only if the new segments support the entire statement independently."
            ),
        )
    claim = create_model(
        "ExtractedStatement",
        __base__=ExtractedClaimOutput,
        segment_ids=(list[id_type], Field(min_length=1, max_length=32)),
        temporal_anchor_segment_id=(id_type | None, None),
        **fields,
    )
    evidence_order = ["segment_ids", *fields, "temporal_status", "facets"]
    ordered_fields = [*evidence_order, *(name for name in claim.model_fields if name not in evidence_order)]
    claim = create_model(
        "EvidenceFirstStatement", __config__=ConfigDict(extra="forbid"),
        **{name: (claim.model_fields[name].annotation, claim.model_fields[name]) for name in ordered_fields},
    )
    base = create_model(
        "ExtractionResponse",
        __config__=ConfigDict(extra="forbid"),
        claims=(list[claim], Field(max_length=128)),
        source_only=(list[source_only], Field(max_length=len(ids))),
    )

    class ExactExtractionResponse(base):
        @model_validator(mode="after")
        def validate_accounting(self):
            remainder = [d.segment_id for d in self.source_only]
            cited = {s for c in self.claims for s in c.segment_ids}
            if len(remainder) != len(set(remainder)):
                raise ValueError("Duplicate source-only segment")
            if cited & set(remainder):
                raise ValueError(
                    f"Cited segments cannot also be source-only: {sorted(cited & set(remainder))}"
                )
            if cited | set(remainder) != set(ids):
                raise ValueError(
                    f"Claims and source-only reasons must account for every new segment; missing={sorted(set(ids) - cited - set(remainder))}"
                )
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
        **{alias: (AssistantContextCandidateDecisionOutput, ...) for alias in aliases},
    )
    return create_model(
        "AssistantContextSelectionOutput",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions_model, ...),
    )


class FactCandidateSelectionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_fact_ids: list[str] = Field(max_length=12)
    reason: str = Field(min_length=1, max_length=800)


class FactScopeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prior_referent: str = Field(min_length=1)
    incoming_referent: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    relation: Literal["same", "distinct", "unresolved"]


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
    incoming = tuple(
        dict.fromkeys(str(value) for value in incoming_claim_aliases if value)
    )
    targets = tuple(
        dict.fromkeys(str(value) for value in target_claim_aliases if value)
    )
    if not incoming:
        raise ValueError("Fact truth resolution requires incoming claim aliases")
    decision_fields: dict[str, Any] = {}
    scope_fields = {}
    if targets:
        scope_model = create_model(
            "TargetScopes",
            __config__=ConfigDict(extra="forbid"),
            **{alias: (FactScopeComparison, ...) for alias in targets},
        )
        scope_fields["scope"] = (scope_model, ...)
    for alias in incoming:
        no_change = create_model(
            f"{alias}FactTruthNoChange",
            __base__=FactTruthNoChangeOutput,
            **scope_fields,
        )
        if not targets:
            decision_fields[alias] = (no_change, ...)
            continue
        target_type = Literal.__getitem__(targets)
        truth_change = create_model(
            f"{alias}FactTruthChange",
            __base__=FactTruthChangeOutput,
            **scope_fields,
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
                if any(
                    getattr(decision[1].scope, target).relation != "same"
                    for target in decision_targets
                ):
                    raise ValueError(
                        "Truth changes require model-established same scope for every target"
                    )
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
    incoming = tuple(
        dict.fromkeys(str(value) for value in incoming_claim_aliases if value)
    )
    facts = tuple(dict.fromkeys(str(value) for value in prior_fact_aliases if value))
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


def fact_synthesis_output_model(
    claim_texts: Mapping[str, str],
    allowed_sections: Collection[str],
    truth_changes: Collection[Mapping[str, Any]] = (),
) -> type[BaseModel]:
    """Partition canonical claims into grounded presentation groups in one response."""
    if not claim_texts or not allowed_sections:
        raise ValueError("Synthesis requires claims and allowed sections")
    alias_type = Literal.__getitem__(tuple(claim_texts))
    section_type = Literal.__getitem__(tuple(dict.fromkeys(allowed_sections)))
    fact = create_model(
        "SynthesizedFact",
        __config__=ConfigDict(extra="forbid"),
        memory_scope=(str, Field(min_length=1)),
        member_claim_aliases=(
            list[alias_type],
            Field(min_length=1, max_length=len(claim_texts)),
        ),
        state=(Literal["current", "history"], ...),
        section_key=(section_type, ...),
        text=(str, Field(min_length=1, max_length=1000)),
        confidence=(float, Field(ge=0.0, le=1.0)),
        reason=(str, Field(min_length=1, max_length=800)),
    )
    base = create_model(
        "FactSynthesis",
        __config__=ConfigDict(extra="forbid"),
        facts=(list[fact], Field(min_length=1, max_length=len(claim_texts))),
    )

    class ExactFactSynthesis(base):
        @model_validator(mode="after")
        def validate_projection(self):
            supplied = [
                alias for fact in self.facts for alias in fact.member_claim_aliases
            ]
            if len(supplied) != len(set(supplied)) or set(supplied) != set(claim_texts):
                repeated = sorted(
                    alias for alias, count in Counter(supplied).items() if count > 1
                )
                missing = sorted(set(claim_texts) - set(supplied))
                raise ValueError(
                    "Every canonical claim must belong to exactly one display group; "
                    f"repeated={repeated}; missing={missing}. Do not add a second review-summary group."
                )
            for fact in self.facts:
                members = fact.member_claim_aliases
                if len(members) == 1 and fact.text != claim_texts[members[0]]:
                    raise ValueError(
                        f"Singleton {members[0]} must copy the canonical claim text exactly: "
                        f"{claim_texts[members[0]]!r}"
                    )
                for change in truth_changes:
                    if set(members) & set(change["incoming_claim_aliases"]) and set(
                        members
                    ) & set(change["target_claim_aliases"]):
                        raise ValueError("Truth-change sides cannot share a fact")
            return self

    return ExactFactSynthesis
