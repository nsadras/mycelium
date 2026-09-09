"""Explicit source-backed subject relevance before wiki destination selection."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator
from mycelium.ontology import section_keys
from mycelium.prompting import render_prompt_pair


def page_plan_model(evidence_aliases, entity_types):
    page_fields = {}
    for entity_id, kind in entity_types.items():
        page = create_model(
            f"{entity_id}PageSection",
            __config__=ConfigDict(extra="forbid"),
            subject_evidence=(str, Field(min_length=1)),
            relevance=(
                Literal[
                    "describes_subject",
                    "substantive_relationship",
                    "incidental_or_unrelated",
                ],
                ...,
            ),
            section_key=(
                Literal.__getitem__((*section_keys(kind), "not_selected")),
                ...,
            ),
            reason=(str, Field(min_length=1)),
        )
        page_fields[entity_id] = (page, ...)
    pages_model = create_model(
        "PageSelections", __config__=ConfigDict(extra="forbid"), **page_fields
    )

    class Decision(BaseModel):
        model_config = ConfigDict(extra="forbid")
        pages: pages_model
        owner_entity: Literal.__getitem__((*entity_types, ""))
        route_kind: Literal["general", "deferred"]
        reason: str = Field(min_length=1)
        confidence: float = Field(ge=0, le=1)

        @model_validator(mode="after")
        def validate_destinations(self):
            selected = {
                eid
                for eid, p in self.pages.model_dump().items()
                if p["section_key"] != "not_selected"
            }
            for p in self.pages.model_dump().values():
                if (
                    p["section_key"] != "not_selected"
                    and p["relevance"] == "incidental_or_unrelated"
                ):
                    raise ValueError(
                        "Selected pages require subject evidence or a substantive relationship"
                    )
            if self.route_kind == "general" and self.owner_entity not in selected:
                raise ValueError("The primary owner must be a selected page")
            if self.route_kind == "deferred" and (selected or self.owner_entity):
                raise ValueError("Deferred claims must have no selected pages or owner")
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




def page_plan_prompt(registry, entity_plan, evidence):
    return render_prompt_pair(
        "memory/page_plan",
        registry=registry,
        entity_plan=entity_plan,
        evidence=evidence,
    )
