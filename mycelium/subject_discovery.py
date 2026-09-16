"""Source-first subject discovery, before exposure to the identity registry."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import ENTITY_TYPES, ENTITY_ONTOLOGY
from mycelium.prompting import render_prompt, render_prompt_pair


def subject_discovery_model(claim_ids, participant_roles, reviewed_types):
    evidence_ids = tuple([*claim_ids, *participant_roles, *reviewed_types])
    if not evidence_ids:
        raise ValueError("Subject discovery requires source evidence")
    common = {
        "description": (str, Field(min_length=1, max_length=500)),
        "title": (str, Field(min_length=1, max_length=200)),
        "aliases": (list[str], Field(max_length=12)),
    }
    variants = []
    for kind in ENTITY_TYPES:
        if kind == "you":
            continue
        allowed = [
            *claim_ids,
            *(participant_roles if kind == "person" else []),
            *(
                alias
                for alias, value in reviewed_types.items()
                if value == kind or (kind == "person" and value == "you")
            ),
        ]
        if not allowed:
            continue
        variants.append(
            create_model(
                "Discovered" + kind.title(),
                __config__=ConfigDict(extra="forbid"),
                **common,
                entity_type=(Literal.__getitem__((kind,)), ...),
                supporting_evidence=(
                    list[Literal.__getitem__(tuple(allowed))],
                    Field(min_length=1, max_length=len(allowed)),
                ),
            )
        )
    from typing import Union

    subject_type = Union[tuple(variants)]

    class SourceSubjects(BaseModel):
        model_config = ConfigDict(extra="forbid")
        subjects: list[subject_type] = Field(max_length=48)

        @model_validator(mode="after")
        def account_for_declared_occurrences(self):
            for subject in self.subjects:
                if len(subject.supporting_evidence) != len(
                    set(subject.supporting_evidence)
                ):
                    raise ValueError("Subject evidence must be unique")
            for alias in [*participant_roles, *reviewed_types]:
                occurrences = [
                    s for s in self.subjects if alias in s.supporting_evidence
                ]
                if len(occurrences) != 1:
                    raise ValueError(
                        f"Declared identity occurrence {alias} must be represented once"
                    )
            return self

    return SourceSubjects


def subject_discovery_prompt(evidence, reviewed):
    system, user = render_prompt_pair(
        "memory/subject_discovery", evidence=evidence, reviewed=reviewed
    )
    system += "\n\n" + render_prompt(
        "memory/source_subject_types.system.jinja",
        entity_types={
            kind.key: kind.description for kind in ENTITY_ONTOLOGY if kind.key != "you"
        },
    )
    return system, user
