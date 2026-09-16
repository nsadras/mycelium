"""Bounded evidence grouping and independently reusable group rendering."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.prompting import render_prompt_pair

MAX_GROUP_MEMBERS = 12


def fact_groups_model(claim_ids, sections):
    ids = tuple(claim_ids)
    if not ids or not sections:
        raise ValueError("Fact grouping requires canonical claims and allowed sections")
    group = create_model(
        "CanonicalFactGroup",
        __config__=ConfigDict(extra="forbid"),
        member_claim_aliases=(
            list[Literal.__getitem__(ids)],
            Field(min_length=1, max_length=min(MAX_GROUP_MEMBERS, len(ids))),
        ),
        memory_scope=(str, Field(min_length=1, max_length=500)),
        state=(Literal["current", "history"], ...),
        section_key=(Literal.__getitem__(tuple(sections)), ...),
        prominence=(Literal["briefing", "detail"], ...),
    )
    base = create_model(
        "CanonicalFactGroupsFields",
        __config__=ConfigDict(extra="forbid"),
        groups=(list[group], Field(min_length=1, max_length=len(ids))),
    )

    class CanonicalFactGroups(base):
        @model_validator(mode="after")
        def exact_partition(self):
            found = [
                alias for group in self.groups for alias in group.member_claim_aliases
            ]
            if len(found) != len(set(found)) or set(found) != set(ids):
                raise ValueError(
                    "Every canonical claim must belong to exactly one bounded group"
                )
            return self

    return CanonicalFactGroups


class FactText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)


def fact_groups_prompt(owner, claims, sections):
    return render_prompt_pair(
        "memory/fact_groups", owner=owner, claims=claims, sections=sections
    )


def fact_text_prompt(owner, claims):
    return render_prompt_pair("memory/fact_text", owner=owner, claims=claims)
