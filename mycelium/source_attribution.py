"""Source-backed claim attribution, independent of wiki page availability."""

import json
from typing import Annotated, Literal
from pydantic import ConfigDict, Field, create_model, model_validator
from mycelium.prompting import render_prompt


def source_attribution_model(claim_ids, entity_ids, source_participants):
    variants, subjects = {}, {}
    for eid in entity_ids:
        reporting = eid in source_participants
        if reporting not in variants:
            variants[reporting] = create_model(
                "ParticipantAttribution" if reporting else "EntityAttribution",
                __config__=ConfigDict(extra="forbid"),
                assertions=(
                    list[Annotated[str, Field(min_length=1, max_length=500)]],
                    Field(
                        max_length=12,
                        description="What the statement asserts about this entity; empty if none",
                    ),
                ),
                relation_to_claim=(
                    Literal.__getitem__(
                        (
                            "described",
                            *(("reporting_only",) if reporting else ()),
                            "unrelated",
                        )
                    ),
                    ...,
                ),
            )
        subjects[eid] = (variants[reporting], ...)
    entities = create_model(
        "EntityAttributions", __config__=ConfigDict(extra="forbid"), **subjects
    )
    claims = create_model(
        "ClaimAttributions",
        __config__=ConfigDict(extra="forbid"),
        **{cid: (entities, ...) for cid in claim_ids},
    )
    base = create_model(
        "SourceAttribution",
        __config__=ConfigDict(extra="forbid"),
        attributions=(claims, ...),
    )

    class SourceAttribution(base):
        @model_validator(mode="after")
        def consistent_assertions(self):
            for subjects in self.attributions.model_dump().values():
                for decision in subjects.values():
                    assertions = decision["assertions"]
                    if bool(assertions) != (
                        decision["relation_to_claim"] == "described"
                    ):
                        raise ValueError(
                            "Only described relations have asserted content"
                        )
            return self

    return SourceAttribution


def source_attribution_prompt(subjects, evidence):
    # Prior automatic projections and identity-review metadata do not establish
    # a claim's meaning. Reviewed identities are already resolved in subjects.
    evidence = {
        **evidence,
        "claims": {
            cid: {key: row[key] for key in ("text", "citations")}
            for cid, row in evidence["claims"].items()
        },
    }
    return (
        render_prompt("memory/source_attribution.system.jinja"),
        json.dumps({"resolved_subjects": subjects, **evidence}),
    )


def attributed_pages(attributions, eligible, excluded_pages):
    """Project explicit attribution and exact review exclusions onto pages.

    Page availability cannot change who a statement describes. Every eligible
    described subject gets a section; reporting-only subjects never get one.
    """
    return {
        cid: [
            eid
            for eid, decision in subjects.items()
            if decision["relation_to_claim"] == "described"
            and eid in eligible
            and eid not in excluded_pages.get(cid, ())
        ]
        for cid, subjects in attributions.items()
    }
