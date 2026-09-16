"""Explicit source-backed subject relevance before wiki destination selection."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from mycelium.ontology import section_keys
from mycelium.prompting import render_prompt_pair


def page_plan_model(evidence_aliases, entity_types):
    page = create_model(
        "SelectedPage",
        __config__=ConfigDict(extra="forbid"),
        section_key=(
            Literal.__getitem__(
                tuple(
                    dict.fromkeys(
                        key
                        for kind in entity_types.values()
                        for key in section_keys(kind)
                    )
                )
            )
            if entity_types
            else str,
            ...,
        ),
        reason=(str, Field(min_length=1)),
    )
    pages_model = dict[
        Literal.__getitem__(tuple(entity_types)) if entity_types else str, page
    ]

    class Decision(BaseModel):
        model_config = ConfigDict(extra="forbid")
        pages: pages_model
        owner_entity: Literal.__getitem__((*entity_types, ""))
        reason: str | None
        uncertainty: str | None
        prominence: Literal["briefing", "detail"]

        @model_validator(mode="after")
        def validate_destinations(self):
            selected = set(self.pages)
            for entity_id, page in self.pages.items():
                if entity_id not in entity_types:
                    raise ValueError("The page ID must belong to the eligible registry")
                if page.section_key not in section_keys(entity_types[entity_id]):
                    raise ValueError(
                        "The section must belong to the selected entity type"
                    )
            if selected and self.owner_entity not in selected:
                raise ValueError("The primary owner must be a selected page")
            if not selected and (self.owner_entity or not self.reason):
                raise ValueError(
                    "An empty destination set requires no owner and a reason"
                )
            if selected and self.reason is not None:
                raise ValueError(
                    "Selected pages carry their own explanations; the overall reason is null"
                )
            return self

    decisions = create_model(
        "PagePlacementDecisions",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (Decision, ...) for alias in evidence_aliases},
    )
    return create_model(
        "PagePlacementPlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions, ...),
    )


def page_plan_prompt(registry, entity_plan, evidence, *, reviewed_pages=False):
    from mycelium.prompting import render_prompt

    system, user = render_prompt_pair(
        "memory/page_plan",
        registry=registry,
        entity_plan=entity_plan,
        evidence=evidence,
    )

    if reviewed_pages:
        system += "\n\n" + render_prompt("memory/page_review.system.jinja")
    return system, user
