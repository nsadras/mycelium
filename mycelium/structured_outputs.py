"""Structured response contracts used by production LLM calls."""

from collections.abc import Collection
from typing import Any, Literal

from mycelium.models import PageType

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


class ConsolidationDestinationOutput(BaseModel):
    page: str = Field(min_length=1, max_length=120)
    page_type: Literal["entity", "event", "topic"]


def consolidation_output_model(
    evidence_aliases: Collection[str],
) -> type[BaseModel]:
    """Build an exact source-scoped page-assignment contract."""
    aliases = tuple(dict.fromkeys(str(value) for value in evidence_aliases if value))
    if not aliases:
        raise ValueError("Consolidation output requires at least one evidence alias")
    fields: dict[str, Any] = {
        alias: (ConsolidationDestinationOutput, ...)
        for alias in aliases
    }
    return create_model(
        "SourceConsolidationOutput",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


class PageTaxonomyDecisionOutput(BaseModel):
    page_type: PageType


def page_taxonomy_output_model(
    page_aliases: Collection[str],
) -> type[BaseModel]:
    """Build an exact contract for classifying already-formed wiki pages."""
    aliases = tuple(dict.fromkeys(str(value) for value in page_aliases if value))
    if not aliases:
        raise ValueError("Page taxonomy output requires at least one page alias")
    fields: dict[str, Any] = {
        alias: (PageTaxonomyDecisionOutput, ...)
        for alias in aliases
    }
    return create_model(
        "PageTaxonomyOutput",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )


class ReconsolidationDecisionOutput(BaseModel):
    incoming_alias: str
    relation: Literal["additive", "supports", "contradicts", "supersedes"]
    target_alias: str = ""
    explanation: str
    confidence: float = 0.8


class ReconsolidationDecisionsOutput(BaseModel):
    decisions: list[ReconsolidationDecisionOutput] = Field(default_factory=list, max_length=32)
