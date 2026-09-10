"""Structured response contracts used by production LLM calls."""

from collections import Counter
from collections.abc import Collection, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import (
    ClaimType,
)


class ExtractedEntityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str = Field(min_length=1)
    role: Literal["subject", "owner", "participant"]


class ExtractedDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    when: str | None = Field(
        description="Time words stated for the event or state; null if absent"
    )
    deadline: str | None = Field(
        description="Latest permissible completion time explicitly imposed by the source; a scheduled day alone gives when, with deadline null"
    )
    inference_basis: str | None = Field(
        description="Evidence for an inferred assertion; null for a directly stated assertion"
    )


class ExtractedClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(
        min_length=1,
        max_length=1000,
        description="Complete statement with names, qualifications and referenced details. State accepting or declining a proposal explicitly.",
    )
    claim_type: ClaimType
    predicate: Literal["project_role"] | None = None
    evidence_modality: Literal["speech", "visual", "tool", "mixed", "unknown"]
    temporal_status: Literal[
        "past", "current", "future", "recurring", "atemporal", "unknown"
    ]
    temporal_anchor_segment_id: str | None = None
    about: list[ExtractedEntityOutput] = Field(min_length=1, max_length=12)
    segment_ids: list[str] = Field(min_length=1, max_length=32)
    facets: ExtractedDetails


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
    ordered_fields = [
        *evidence_order,
        *(name for name in claim.model_fields if name not in evidence_order),
    ]
    claim = create_model(
        "EvidenceFirstStatement",
        __config__=ConfigDict(extra="forbid"),
        **{
            name: (claim.model_fields[name].annotation, claim.model_fields[name])
            for name in ordered_fields
        },
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
            for claim in self.claims:
                if (
                    claim.temporal_anchor_segment_id is not None
                    and claim.temporal_anchor_segment_id not in claim.segment_ids
                ):
                    raise ValueError(
                        "A time anchor must be one of the claim's cited new segments"
                    )
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


def fact_truth_output_model(target_claim_aliases: Collection[str]) -> type[BaseModel]:
    """One incoming statement, with an explicit comparison for every older target."""
    targets = tuple(dict.fromkeys(target_claim_aliases))
    if not targets:
        raise ValueError("Truth review requires older targets")
    target_type = Literal.__getitem__(targets)
    comparison = create_model(
        "Comparison",
        __config__=ConfigDict(extra="forbid"),
        target=(target_type, ...),
        scope=(Literal["same", "distinct", "unresolved"], ...),
        reason=(str, Field(min_length=1, max_length=500)),
    )
    base = create_model(
        "TruthDecision",
        __config__=ConfigDict(extra="forbid"),
        comparisons=(
            list[comparison],
            Field(min_length=len(targets), max_length=len(targets)),
        ),
        relation=(Literal["no_change", "contradicts", "supersedes"], ...),
        targets=(list[target_type], Field(max_length=len(targets))),
        reason=(str, Field(min_length=1, max_length=800)),
    )

    class ExactTruthDecision(base):
        @model_validator(mode="after")
        def validate_targets(self):
            compared = [c.target for c in self.comparisons]
            if len(set(compared)) != len(compared) or set(compared) != set(targets):
                raise ValueError("Compare every older target exactly once")
            if len(set(self.targets)) != len(self.targets):
                raise ValueError("Changed targets must be unique")
            if (self.relation == "no_change") != (not self.targets):
                raise ValueError(
                    "A change requires targets; no_change requires an empty targets list"
                )
            scopes = {c.target: c.scope for c in self.comparisons}
            if any(scopes[t] != "same" for t in self.targets):
                raise ValueError("Changed targets require established same scope")
            return self

    return ExactTruthDecision


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
        text=(str | None, Field(max_length=1000)),
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
                if len(members) == 1 and fact.text is not None:
                    raise ValueError(
                        "Singleton text is rendered by the application; return null"
                    )
                if len(members) > 1 and not fact.text:
                    raise ValueError("Multi-claim groups require synthesized text")
                for change in truth_changes:
                    if set(members) & set(change["incoming_claim_aliases"]) and set(
                        members
                    ) & set(change["target_claim_aliases"]):
                        raise ValueError("Truth-change sides cannot share a fact")
            return self

    return ExactFactSynthesis
