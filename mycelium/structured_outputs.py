"""Structured response contracts used by production LLM calls."""

from typing import Literal

from pydantic import BaseModel, Field, RootModel


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
    segment_ids: list[str] = Field(default_factory=list, max_length=32)
    speaker: str | None = None
    evidence_type: Literal["explicit", "inferred"] = "explicit"
    confidence: float = 0.8
    slot: str | None = None
    facets: dict = Field(default_factory=dict)


class ExtractedEpisodeOutput(BaseModel):
    claims: list[ExtractedClaimOutput] = Field(default_factory=list, max_length=128)
    ignored_segment_ids: list[str] = Field(default_factory=list, max_length=256)


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


class ConsolidationRouteOutput(BaseModel):
    evidence_alias: str
    disposition: Literal["route", "ignore"]
    page: str = ""
    action: Literal["update", "create", "none"] = "none"
    page_type: Literal["entity", "event", "topic"] = "topic"


class ConsolidationRoutesOutput(BaseModel):
    routes: list[ConsolidationRouteOutput] = Field(default_factory=list, max_length=64)


class PredictionErrorOutput(BaseModel):
    conflict_type: Literal["none", "additive", "partial", "major"]
    discrepancy_score: float
    explanation: str
    suggested_update: str | None = None


class ReconsolidationRewriteOutput(BaseModel):
    title: str
    content: str
    confidence: float
