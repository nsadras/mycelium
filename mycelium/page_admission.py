"""Independent page admission and entity-specific section contracts."""

from typing import Literal

from pydantic import ConfigDict, Field, create_model, model_validator

from mycelium.prompting import render_prompt_pair


ADMISSION_BASES = {
    "person": ("meaningful_person_profile", "direct_person_encounter"),
    "you": ("meaningful_person_profile",),
    "project": ("ongoing_effort_with_own_purpose",),
    "series": ("ongoing_collection_with_own_purpose",),
    "event": ("substantial_bounded_occurrence",),
    "organization": ("independent_organizational_context",),
    "place": ("independent_place_context",),
    "topic": ("independent_topic_context",),
    "artifact": ("independent_artifact_context",),
}
NO_PAGE_BASIS = "insufficient_independent_context"


def page_admission_model(evidence_aliases, entities, *, excluded_pages=None):
    excluded_pages = excluded_pages or {}
    fields = {}
    for eid, entity in entities.items():
        if entity.materialization_state != "provisional":
            continue
        allowed = tuple(
            alias
            for alias in evidence_aliases
            if eid not in excluded_pages.get(alias, ())
        )
        fields[eid] = (
            create_model(
                "Admission" + entity.entity_type.title(),
                __config__=ConfigDict(extra="forbid"),
                reason=(str, Field(min_length=1, max_length=500)),
                basis=(
                    Literal.__getitem__(
                        (*ADMISSION_BASES[entity.entity_type], NO_PAGE_BASIS)
                        if allowed
                        else (NO_PAGE_BASIS,)
                    ),
                    ...,
                ),
                supporting_claims=(
                    list[Literal.__getitem__(allowed)] if allowed else list[str],
                    Field(max_length=len(allowed)),
                ),
            ),
            ...,
        )
    choices = create_model(
        "NewPageAdmissions", __config__=ConfigDict(extra="forbid"), **fields
    )
    base = create_model(
        "PageAdmissionsFields",
        __config__=ConfigDict(extra="forbid"),
        page_admissions=(choices, ...),
    )

    class PageAdmissions(base):
        @model_validator(mode="after")
        def ground_admitted_pages(self):
            for _, item in self.page_admissions:
                if item.basis != NO_PAGE_BASIS and not item.supporting_claims:
                    raise ValueError("Admitting a page requires cited source claims")
            return self

    return PageAdmissions


def page_admission_prompt(registry, entity_plan, evidence, *, reviewed_pages=False):
    from mycelium.prompting import render_prompt

    system, user = render_prompt_pair(
        "memory/page_admission",
        registry=registry,
        entity_plan=entity_plan,
        evidence=evidence,
    )

    if reviewed_pages:
        system += "\n\n" + render_prompt("memory/page_review.system.jinja")
    return system, user
