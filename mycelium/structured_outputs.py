"""Structured response contracts used by production LLM calls."""

from collections.abc import Collection
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    model_validator,
)

from mycelium.temporal_contract import temporal_details_model

from mycelium.ontology import (
    ClaimType,
)


class ExtractedEntityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str = Field(min_length=1)
    role: Literal["subject", "owner", "participant"]


class ReplacementMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    about: list[ExtractedEntityOutput] = Field(min_length=1)
    claim_type: ClaimType
    predicate: Literal["project_role"] | None
    temporal_status: Literal["past", "current", "future", "recurring", "atemporal", "unknown"]
    facets: temporal_details_model(["replacement"])


class GroundedAnswerOutput(BaseModel):
    answerable: bool
    answer: str
    evidence: str | None = None


def complementary_selection_model(candidate_aliases: Collection[str], limit: int = 5) -> type[BaseModel]:
    aliases = tuple(candidate_aliases)
    if not aliases:
        raise ValueError("Selection requires candidates")
    base = create_model(
        "ComplementarySelectionFields", __config__=ConfigDict(extra="forbid"),
        selected_ids=(list[Literal.__getitem__(aliases)], Field(max_length=limit)),
        supported_aspects=(list[str], Field(max_length=limit)),
        remaining_gaps=(list[str], Field(max_length=limit)),
    )

    class ComplementarySelection(base):
        @model_validator(mode="after")
        def unique_selection(self):
            if len(self.selected_ids) != len(set(self.selected_ids)):
                raise ValueError("Select each record at most once")
            return self

    return ComplementarySelection
