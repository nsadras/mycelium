"""Assign explicit human reviews to source-discovered subject occurrences."""

import json
from typing import Literal

from pydantic import ConfigDict, Field, create_model, model_validator

from mycelium.prompting import render_prompt_pair


def subject_review_model(subjects, bindings):
    choice = Literal.__getitem__((*subjects, "unresolved"))
    assignment = create_model(
        "ReviewedSubjectAssignment",
        __config__=ConfigDict(extra="forbid"),
        subject_alias=(choice, ...),
        reason=(str, Field(min_length=1, max_length=500)),
    )
    fields = create_model(
        "ReviewedSubjectAssignments",
        __config__=ConfigDict(extra="forbid"),
        **{alias: (assignment, ...) for alias in bindings},
    )
    base = create_model(
        "ReviewedSubjectBindingsFields",
        __config__=ConfigDict(extra="forbid"),
        assignments=(fields, ...),
    )

    class ReviewedSubjectBindings(base):
        @model_validator(mode="after")
        def preserve_distinct_bindings(self):
            assigned = {}
            for alias, value in self.assignments:
                if value.subject_alias == "unresolved":
                    continue
                eid = bindings[alias]["entity_id"]
                if (
                    value.subject_alias in assigned
                    and assigned[value.subject_alias] != eid
                ):
                    raise ValueError(
                        "Different reviewed identities require separate source subjects"
                    )
                assigned[value.subject_alias] = eid
            return self

    return ReviewedSubjectBindings


def subject_review_prompt(subjects, bindings, evidence):
    return render_prompt_pair(
        "memory/subject_review_bindings",
        subjects=json.dumps(subjects, ensure_ascii=False),
        bindings=json.dumps(bindings, ensure_ascii=False),
        evidence=evidence,
    )
