"""Bounded semantic query representation for the embedding model."""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from mycelium.budget import count_tokens


class SearchQueryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)

    @field_validator("query")
    @classmethod
    def bounded_query(cls, value):
        if count_tokens(value) > 1024:
            raise ValueError("The search query must fit within 1024 estimated tokens")
        return value
