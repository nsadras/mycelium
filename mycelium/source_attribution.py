"""Source-backed claim attribution, independent of wiki page availability."""

import json
from typing import Literal, Union
from pydantic import ConfigDict, Field, create_model
from mycelium.prompting import render_prompt


def source_attribution_model(claim_ids, entity_ids, source_participants):
    variants, subjects = {}, {}
    for eid in entity_ids:
        reporting = eid in source_participants
        if reporting not in variants:
            variants[reporting] = Union[
                tuple(
                    create_model(
                        relation.title(),
                        __config__=ConfigDict(extra="forbid"),
                        relation_to_claim=(Literal.__getitem__((relation,)), ...),
                        reason=(
                            str if relation != "unrelated" else type(None),
                            Field(min_length=1, max_length=500)
                            if relation != "unrelated"
                            else ...,
                        ),
                    )
                    for relation in (
                        "described",
                        *(("reporting_only",) if reporting else ()),
                        "unrelated",
                    )
                )
            ]
        subjects[eid] = (variants[reporting], ...)
    relations = create_model(
        "EntityAttributions", __config__=ConfigDict(extra="forbid"), **subjects
    )
    claims = create_model(
        "ClaimAttributions",
        __config__=ConfigDict(extra="forbid"),
        **{cid: (relations, ...) for cid in claim_ids},
    )
    return create_model(
        "SourceAttribution",
        __config__=ConfigDict(extra="forbid"),
        attributions=(claims, ...),
    )


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
