"""Strict model-tool arguments; IDs and resource bounds are exact contracts."""

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class MemorySearchArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(
        min_length=1,
        max_length=4096,
        description="A focused description of the memory to find.",
    )
    limit: int = Field(
        default=6,
        ge=1,
        le=6,
        description="Maximum number of new memory records to return.",
    )

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value):
        if not value.strip():
            raise ValueError("memory_search requires a nonempty query")
        return value


class MemorySourcesArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    claim_ids: list[StrictStr] = Field(min_length=1, max_length=6)

    @field_validator("claim_ids")
    @classmethod
    def exact_ids(cls, values):
        if any(not value.strip() for value in values) or len(values) != len(
            set(values)
        ):
            raise ValueError("memory_sources requires distinct nonempty claim IDs")
        return values


MEMORY_TOOL_ARGUMENTS = {
    "memory_search": MemorySearchArguments,
    "memory_sources": MemorySourcesArguments,
}
