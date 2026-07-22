from typing import Literal

from pydantic import BaseModel, Field, RootModel


class EncodedEntryOutput(BaseModel):
    content: str
    durability: Literal["ephemeral", "session", "durable"]
    importance: Literal["low", "medium", "high"]


class EncodedSessionOutput(BaseModel):
    entries: list[EncodedEntryOutput] = Field(default_factory=list, max_length=20)


class ExtractedEntityOutput(BaseModel):
    entity: str
    role: str | None = None


class ExtractedClaimOutput(BaseModel):
    text: str
    kind: str = "fact"
    about: list[ExtractedEntityOutput] = Field(default_factory=list, max_length=12)
    segment_ids: list[str] = Field(default_factory=list, max_length=32)
    speaker: str | None = None
    evidence_type: Literal["explicit", "inferred"] = "explicit"
    confidence: float = 0.8
    slot: str | None = None
    facets: dict = Field(default_factory=dict)


class ExtractedEpisodeOutput(BaseModel):
    summary: str = ""
    claims: list[ExtractedClaimOutput] = Field(default_factory=list, max_length=128)
    ignored_segment_ids: list[str] = Field(default_factory=list, max_length=128)


class DerivedClaimOutput(BaseModel):
    text: str
    kind: str = "derived insight"
    about: list[ExtractedEntityOutput] = Field(default_factory=list, max_length=12)
    basis_claim_ids: list[str] = Field(default_factory=list, min_length=1, max_length=12)
    inference_basis: str
    confidence: float = 0.6
    facets: dict = Field(default_factory=dict)


class DerivedClaimsOutput(BaseModel):
    claims: list[DerivedClaimOutput] = Field(default_factory=list, max_length=64)


class ImportanceRatingOutput(BaseModel):
    importance: float


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


class MemoryUsageItemOutput(BaseModel):
    page: str
    used: bool
    reason: str | None = None


class MemoryUsageOutput(BaseModel):
    pages: list[MemoryUsageItemOutput] = Field(default_factory=list, max_length=12)


class ConsolidationTargetOutput(BaseModel):
    page: str
    action: Literal["update", "create", "none"]
    page_type: Literal["entity", "event", "topic"] = "topic"
    log_entry_ids: list[str] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class ConsolidationIdentifyOutput(BaseModel):
    targets: list[ConsolidationTargetOutput] = Field(default_factory=list, max_length=8)


class CanonicalizationMappingOutput(BaseModel):
    proposed_page: str
    action: Literal["use_existing", "create_new", "drop"]
    canonical_page: str | None = None
    page_type: Literal["entity", "event", "topic"] = "topic"
    log_entry_ids: list[str] = Field(default_factory=list, max_length=20)
    reason: str | None = None


class CanonicalizationOutput(BaseModel):
    mappings: list[CanonicalizationMappingOutput] = Field(default_factory=list, max_length=20)


class RelatedEdgeOutput(BaseModel):
    target: str
    relation: str
    weight: float = 1.0


class WikiRewriteOutput(BaseModel):
    title: str
    content: str
    confidence: float
    importance: float
    tags: list[str] = Field(default_factory=list, max_length=12)
    related: list[RelatedEdgeOutput] = Field(default_factory=list, max_length=12)


class WikiAppendFactOutput(BaseModel):
    fact: str
    section: Literal["key_facts", "event_timeline"] = "key_facts"
    date: str | None = None
    people: str | None = None
    source: str | None = None


class WikiAppendOutput(BaseModel):
    new_facts: list[WikiAppendFactOutput] = Field(default_factory=list, max_length=20)
    new_tags: list[str] = Field(default_factory=list, max_length=8)
    confidence_adjustment: float = 0.0
    importance_adjustment: float = 0.0


class WikiMergeOutput(BaseModel):
    content: str


class WikiIndexOutput(BaseModel):
    index: str


class ToolExtractedFactOutput(BaseModel):
    fact: str
    confidence: float = 0.5
    recommended_memory_scope: Literal["ignore", "session", "durable"] = "ignore"
    suggested_topics: list[str] = Field(default_factory=list, max_length=8)


class ToolObservationExtractionOutput(BaseModel):
    source_tool_entry_id: str
    tool_name: str | None = None
    query_or_url: str | None = None
    facts: list[ToolExtractedFactOutput] = Field(default_factory=list, max_length=12)
    discarded_noise: list[str] = Field(default_factory=list, max_length=12)


class PredictionErrorOutput(BaseModel):
    conflict_type: Literal["none", "additive", "partial", "major"]
    discrepancy_score: float
    explanation: str
    suggested_update: str | None = None


class ReconsolidationRewriteOutput(BaseModel):
    title: str
    content: str
    confidence: float
    update_reason: str
    tags: list[str] = Field(default_factory=list, max_length=12)
    importance: float | None = None
