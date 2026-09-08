"""Explicit, evidence-backed wiki destinations for canonical statements."""

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import section_keys
from mycelium.prompting import render_prompt_pair


def page_plan_model(evidence_aliases, entity_types):
    """Choose at most one section per page, independently across eligible pages."""
    class Decision(BaseModel):
        model_config = ConfigDict(extra="forbid")
        reason: str = Field(min_length=1)
        confidence: float = Field(ge=0, le=1)

    deferred = create_model("DeferredPagePlacement", __base__=Decision,
                            route_kind=(Literal["deferred"], ...))
    routes = [deferred]
    if entity_types:
        page_fields = {}
        for entity_id, kind in entity_types.items():
            page = create_model(
                f"{entity_id}PageSection", __config__=ConfigDict(extra="forbid"),
                section_key=(Literal.__getitem__((*section_keys(kind), "not_selected")), ...),
                reason=(str, Field(min_length=1)),
            )
            page_fields[entity_id] = (page, ...)
        pages_model = create_model("PageSelections", __config__=ConfigDict(extra="forbid"), **page_fields)

        class Placed(Decision):
            route_kind: Literal["general"]
            pages: pages_model
            owner_entity: Literal.__getitem__(tuple(entity_types))

            @model_validator(mode="after")
            def owner_is_selected(self):
                if self.pages.model_dump()[self.owner_entity]["section_key"] == "not_selected":
                    raise ValueError("The primary owner must be a selected page")
                return self

        routes.append(Placed)
    route_type = Union[tuple(routes)]
    decisions = create_model("PagePlacementDecisions", __config__=ConfigDict(extra="forbid"),
                             **{alias: (route_type, ...) for alias in evidence_aliases})
    return create_model("PagePlacementPlan", __config__=ConfigDict(extra="forbid"),
                        decisions=(decisions, ...))


def page_plan_prompt(registry, entity_plan, evidence):
    return render_prompt_pair("memory/page_plan", registry=registry,
                              entity_plan=entity_plan, evidence=evidence)
