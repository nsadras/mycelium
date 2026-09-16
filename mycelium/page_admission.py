"""Independent page admission and entity-specific section contracts."""

from typing import Literal

from pydantic import ConfigDict, Field, create_model, model_validator

from mycelium.ontology import section_keys
from mycelium.page_plan import page_plan_model
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


def page_admission_model(evidence_aliases, entities):
    fields = {}
    for eid, entity in entities.items():
        if entity.materialization_state != "provisional":
            continue
        fields[eid] = (
            create_model(
                "Admission" + entity.entity_type.title(),
                __config__=ConfigDict(extra="forbid"),
                reason=(str, Field(min_length=1, max_length=500)),
                basis=(
                    Literal.__getitem__(
                        (*ADMISSION_BASES[entity.entity_type], NO_PAGE_BASIS)
                    ),
                    ...,
                ),
                supporting_claims=(
                    list[Literal.__getitem__(tuple(evidence_aliases))],
                    Field(max_length=len(evidence_aliases)),
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


def typed_page_plan_model(evidence_aliases, entity_types):
    original = page_plan_model(evidence_aliases, entity_types)
    decision = (
        original.model_fields["decisions"]
        .annotation.model_fields[next(iter(evidence_aliases))]
        .annotation
    )
    properties = {}
    for eid, kind in entity_types.items():
        page = create_model(
            "PageSection",
            __config__=ConfigDict(extra="forbid"),
            section_key=(Literal.__getitem__(section_keys(kind)), ...),
            reason=(str, Field(min_length=1)),
        )
        properties[eid] = page.model_json_schema()
    typed_decision = create_model(
        "TypedPagePlacement",
        __base__=decision,
        pages=(
            decision.model_fields["pages"].annotation,
            Field(
                json_schema_extra={
                    "properties": properties,
                    "additionalProperties": False,
                }
            ),
        ),
    )
    placements = create_model(
        "TypedPagePlacements",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (typed_decision, ...) for alias in evidence_aliases},
    )
    return create_model(
        "TypedPagePlan",
        __config__=ConfigDict(extra="forbid"),
        decisions=(placements, ...),
    )


def page_admission_prompt(registry, entity_plan, evidence):
    return render_prompt_pair(
        "memory/page_admission",
        registry=registry,
        entity_plan=entity_plan,
        evidence=evidence,
    )
