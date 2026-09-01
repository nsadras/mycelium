"""Request and response contracts shared by memory API routers."""

from pathlib import Path

from pydantic import BaseModel, Field


class FlushRequest(BaseModel):
    session_id: str | None = None


class IdleFlushRequest(BaseModel):
    idle_minutes: int = 20
    max_turns: int = 25
    force: bool = False


class ProposalReviewRequest(BaseModel):
    reviewer_note: str | None = None


class IdentityReviewRequest(BaseModel):
    reviewer_note: str | None = None
    entity_id: str | None = None
    entity_type: str | None = None
    title: str | None = None
    scope: str | None = None
    page_state: str | None = None
    parent_entity_id: str | None = None


class EntityUpdateRequest(BaseModel):
    title: str | None = None
    slug: str | None = None
    aliases: list[str] | None = None
    entity_type: str | None = None


class EntityMergeRequest(BaseModel):
    target_entity_id: str


class EntitySplitRequest(BaseModel):
    claim_ids: list[str] = Field(min_length=1)
    title: str
    entity_type: str
    aliases: list[str] = Field(default_factory=list)


class PlacementUpdateRequest(BaseModel):
    owner_entity_id: str | None = None
    section_key: str | None = None
    linked_entity_ids: list[str] = Field(default_factory=list)
    reason: str = "Manual wiki organization"


class FactEditRequest(BaseModel):
    text: str = Field(min_length=1)
    reason: str = "Manual fact correction"


class ClaimCorrectionRequest(BaseModel):
    text: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    claim_type: str | None = None
    predicate: str | None = None
    temporal_status: str | None = None


class SourceRetractionRequest(BaseModel):
    reason: str = Field(min_length=1)


class FactMoveRequest(BaseModel):
    owner_entity_id: str
    section_key: str
    linked_entity_ids: list[str] = Field(default_factory=list)
    reason: str = "Manual fact organization"


class FactGroupRequest(BaseModel):
    fact_ids: list[str] = Field(min_length=2)
    text: str = Field(min_length=1)
    reason: str = "Manual fact grouping"


class FactSplitGroup(BaseModel):
    claim_ids: list[str] = Field(min_length=1)
    text: str = Field(min_length=1)


class FactSplitRequest(BaseModel):
    groups: list[FactSplitGroup] = Field(min_length=2)
    reason: str = "Manual fact split"


def wiki_page_response(page):
    return {
        "slug": page.slug,
        "title": page.title,
        "content": page.content,
        "version": page.version,
        "page_type": page.page_type,
        "tags": page.tags,
        "source_log_entries": page.source_log_entries,
        "related": [{"target": r.target, "relation": r.relation} for r in page.related],
        "update_log": [
            {"version": u.version, "reason": u.reason, "date": u.date.isoformat()}
            for u in page.update_log
        ],
        "entity_id": page.entity_id,
        "entity_status": page.entity_status,
        "aliases": page.aliases,
        "sections": page.sections,
    }


def _stored_memory_file(path: Path) -> dict[str, str]:
    return {
        "filename": path.name,
        "content": path.read_text(encoding="utf-8"),
    }
