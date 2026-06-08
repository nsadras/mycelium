from typing import Literal

from pydantic import BaseModel, RootModel


class EncodedEntryOutput(BaseModel):
    content: str
    durability: Literal["ephemeral", "session", "durable"]
    importance: Literal["low", "medium", "high"]


class EncodedSessionOutput(BaseModel):
    entries: list[EncodedEntryOutput]


class ImportanceRatingOutput(BaseModel):
    importance: float


class RoutingSelectionOutput(BaseModel):
    page: str
    priority: int
    reason: str | None = None


class RoutingOutput(RootModel[list[RoutingSelectionOutput]]):
    pass


class MemoryUsageItemOutput(BaseModel):
    page: str
    used: bool
    reason: str | None = None


class MemoryUsageOutput(BaseModel):
    pages: list[MemoryUsageItemOutput]


class ConsolidationTargetOutput(BaseModel):
    page: str
    action: Literal["update", "create", "none"]
    log_entry_ids: list[str] = []


class ConsolidationIdentifyOutput(BaseModel):
    targets: list[ConsolidationTargetOutput]


class CanonicalizationMappingOutput(BaseModel):
    proposed_page: str
    action: Literal["use_existing", "create_new", "drop"]
    canonical_page: str | None = None
    log_entry_ids: list[str] = []
    reason: str | None = None


class CanonicalizationOutput(BaseModel):
    mappings: list[CanonicalizationMappingOutput]


class RelatedEdgeOutput(BaseModel):
    target: str
    relation: str
    weight: float = 1.0


class WikiRewriteOutput(BaseModel):
    title: str
    content: str
    confidence: float
    importance: float
    tags: list[str] = []
    related: list[RelatedEdgeOutput] = []


class WikiMergeOutput(BaseModel):
    content: str


class WikiIndexOutput(BaseModel):
    index: str


class ToolExtractedFactOutput(BaseModel):
    fact: str
    confidence: float = 0.5
    recommended_memory_scope: Literal["ignore", "session", "durable"] = "ignore"
    suggested_topics: list[str] = []


class ToolObservationExtractionOutput(BaseModel):
    source_tool_entry_id: str
    tool_name: str | None = None
    query_or_url: str | None = None
    facts: list[ToolExtractedFactOutput] = []
    discarded_noise: list[str] = []


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
    tags: list[str] = []
    importance: float | None = None
