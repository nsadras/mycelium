"""Explicit, evidence-backed wiki destinations for canonical statements."""

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import section_keys
from mycelium.prompting import render_prompt_pair


def page_plan_model(evidence_aliases, entity_types):
    variants = []
    for kind in sorted(set(entity_types.values())):
        ids = tuple(e for e, t in entity_types.items() if t == kind)
        variants.append(create_model(
            f"{kind}PageDestination", __config__=ConfigDict(extra="forbid"),
            entity_id=(Literal.__getitem__(ids), ...),
            section_key=(Literal.__getitem__(tuple(section_keys(kind))), ...),
            reason=(str, Field(min_length=1)),
        ))

    class Decision(BaseModel):
        model_config = ConfigDict(extra="forbid")
        reason: str = Field(min_length=1)
        confidence: float = Field(ge=0, le=1)

    deferred = create_model("DeferredPagePlacement", __base__=Decision,
                            route_kind=(Literal["deferred"], ...))
    routes = [deferred]
    if variants:
        destination = Union[tuple(variants)]

        class Placed(Decision):
            route_kind: Literal["general"]
            owner_entity: Literal.__getitem__(tuple(entity_types))
            pages: list[destination] = Field(min_length=1)

            @model_validator(mode="after")
            def unique_destinations(self):
                ids = [p.entity_id for p in self.pages]
                if len(set(ids)) != len(ids) or self.owner_entity not in ids:
                    raise ValueError("Choose each destination once and include the primary owner")
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
