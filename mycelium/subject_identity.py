"""Resolve a source-discovered subject and its name from identity evidence."""

import json
from typing import Literal, Union

from pydantic import ConfigDict, Field, create_model, model_validator

from mycelium.prompting import render_prompt_pair


def subject_identity_model(candidate_ids):
    ids = tuple(candidate_ids)
    common = {"reason": (str, Field(min_length=1, max_length=500))}
    names = {
        "title": (
            str,
            Field(
                min_length=1,
                description="Source-established name or a descriptive title when unnamed",
            ),
        ),
        "aliases": (list[str], Field(max_length=12)),
    }
    variants = [
        create_model(
            "NewSubjectIdentity",
            __config__=ConfigDict(extra="forbid"),
            **common,
            resolution=(Literal["new"], ...),
            **names,
        )
    ]
    if ids:
        variants.append(
            create_model(
                "ExistingSubjectIdentity",
                __config__=ConfigDict(extra="forbid"),
                **common,
                resolution=(Literal["existing"], ...),
                entity_id=(Literal.__getitem__(ids), ...),
                title=(
                    str,
                    Field(
                        description="Preferred title to store for this identity, retaining the registry title unless the source establishes a preferred name",
                        min_length=1,
                    ),
                ),
                aliases=(list[str], Field(max_length=12)),
            )
        )
    unresolved = create_model(
        "UnresolvedSubjectIdentityFields",
        __config__=ConfigDict(extra="forbid"),
        **common,
        resolution=(Literal["review_required"], ...),
        candidate_entity_ids=(
            list[Literal.__getitem__(ids)] if ids else list[str],
            Field(max_length=len(ids)),
        ),
        **names,
    )

    class UnresolvedSubjectIdentity(unresolved):
        @model_validator(mode="after")
        def unique_candidates(self):
            if len(self.candidate_entity_ids) != len(set(self.candidate_entity_ids)):
                raise ValueError("Review candidates must be unique")
            return self

    variants.append(UnresolvedSubjectIdentity)
    return create_model(
        "SubjectIdentity",
        __config__=ConfigDict(extra="forbid"),
        decision=(Union[tuple(variants)], ...),
    )


def subject_identity_prompt(subject, registry, evidence, reviewed="none"):
    return render_prompt_pair(
        "memory/subject_identity",
        subject=json.dumps(subject, ensure_ascii=False),
        registry=json.dumps(registry, ensure_ascii=False),
        evidence=evidence,
        reviewed=reviewed,
    )
