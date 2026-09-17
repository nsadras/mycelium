"""Typed presentation on already attributed subject pages."""

import json
from typing import Literal
from pydantic import ConfigDict, Field, create_model
from mycelium.ontology import routing_section_keys
from mycelium.prompting import render_prompt


def page_plan_model(pages_by_claim, entity_types):
    fields = {}
    for cid, pages in pages_by_claim.items():
        if not pages:
            continue
        if len(set(pages)) != len(pages) or not set(pages) <= entity_types.keys():
            raise ValueError("Attributed pages must be unique resolved subject IDs")
        sections = create_model(
            "PageSections",
            __config__=ConfigDict(extra="forbid"),
            **{
                eid: (Literal.__getitem__(routing_section_keys(entity_types[eid])), ...)
                for eid in pages
            },
        )
        decision = create_model(
            "SubjectPresentation",
            __config__=ConfigDict(extra="forbid"),
            primary_reason=(str, Field(min_length=1, max_length=500)),
            primary_subject=(Literal.__getitem__(tuple(pages)), ...),
            pages=(sections, ...),
            uncertainty=(str | None, ...),
            prominence=(Literal["briefing", "detail"], ...),
        )
        fields[cid] = (decision, ...)
    decisions = create_model(
        "StatementPresentations", __config__=ConfigDict(extra="forbid"), **fields
    )
    return create_model(
        "PagePresentations",
        __config__=ConfigDict(extra="forbid"),
        decisions=(decisions, ...),
    )


def page_plan_prompt(registry, attributions, evidence):
    return (
        render_prompt("memory/page_plan.system.jinja"),
        json.dumps(
            {"registry": registry, "attributions": attributions, "evidence": evidence}
        ),
    )
