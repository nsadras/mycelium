"""Source-first subject discovery, before exposure to the identity registry."""

from typing import Literal

from pydantic import ConfigDict, Field, create_model, model_validator

from mycelium.ontology import ENTITY_TYPES, ENTITY_ONTOLOGY
from mycelium.prompting import render_prompt, render_prompt_pair


def subject_discovery_model(claim_ids, roles, reviewed, *, canonical_user=False):
    evidence_ids = tuple([*claim_ids, *reviewed])
    if not evidence_ids:
        raise ValueError("Subject discovery requires source evidence")
    identifiers = tuple(f"S{i:03d}" for i in range(1, 49))
    variants = []
    for kind in ENTITY_TYPES:
        if kind == "you":
            continue
        allowed = [
            *claim_ids,
            *(
                alias
                for alias, value in reviewed.items()
                if value == kind or (kind == "person" and value == "you")
            ),
        ]
        if not allowed:
            continue
        variants.append(
            create_model(
                "Discovered" + kind.title(),
                __config__=ConfigDict(extra="forbid"),
                supporting_evidence=(
                    list[Literal.__getitem__(tuple(allowed))],
                    Field(max_length=len(evidence_ids)),
                ),
                description=(str, Field(min_length=1, max_length=500)),
                title=(str, Field(min_length=1, max_length=200)),
                entity_type=(Literal.__getitem__((kind,)), ...),
                alternate_names=(
                    list[str],
                    Field(
                        max_length=12,
                        description="Alternate human names explicitly stated for this subject; never operational evidence IDs.",
                    ),
                ),
                subject_id=(Literal.__getitem__(identifiers), ...),
            )
        )
    from typing import Union

    other_roles = {
        p: role for p, role in roles.items() if not (canonical_user and role == "user")
    }
    assignment = create_model(
        "ParticipantSubject",
        __config__=ConfigDict(extra="forbid"),
        subject_id=(Literal.__getitem__(identifiers), ...),
    )
    participants = create_model(
        "ParticipantSubjects",
        __config__=ConfigDict(extra="forbid"),
        **{p: (assignment, ...) for p in other_roles},
    )
    declared = (
        create_model(
            "DeclaredUser",
            __config__=ConfigDict(extra="forbid"),
            supporting_claims=(
                list[Literal.__getitem__(tuple(claim_ids))],
                Field(max_length=len(claim_ids)),
            ),
            description=(str, Field(min_length=1, max_length=500)),
            alternate_names=(list[str], Field(max_length=12)),
        )
        if canonical_user
        else None
    )

    def validate(self):
        subjects = {s.subject_id: s for s in self.subjects}
        if len(subjects) != len(self.subjects):
            raise ValueError("Subject IDs must be unique")
        bound = set()
        for value in self.participant_subjects.model_dump().values():
            sid = value["subject_id"]
            if sid not in subjects or subjects[sid].entity_type != "person":
                raise ValueError(
                    "Every participant must name a returned person subject"
                )
            bound.add(sid)
        for sid, subject in subjects.items():
            support = subject.supporting_evidence
            if len(support) != len(set(support)):
                raise ValueError("Subject evidence must be unique")
            if not support and sid not in bound:
                raise ValueError(
                    "A subject needs claim, review or participant evidence"
                )
        for alias in reviewed:
            if sum(alias in s.supporting_evidence for s in self.subjects) != 1:
                raise ValueError("Each reviewed occurrence must be represented once")
        if canonical_user:
            support = self.declared_user.supporting_claims
            if len(support) != len(set(support)):
                raise ValueError("User supporting claims must be unique")
        return self

    return create_model(
        "SubjectsWithParticipantBindings",
        __config__=ConfigDict(extra="forbid"),
        **({"declared_user": (declared, ...)} if canonical_user else {}),
        subjects=(list[Union[tuple(variants)]], Field(max_length=48)),
        participant_subjects=(participants, ...),
        __validators__={"validate_bindings": model_validator(mode="after")(validate)},
    )


def subject_discovery_prompt(evidence, reviewed, *, canonical_user=False):
    system, user = render_prompt_pair(
        "memory/subject_discovery", evidence=evidence, reviewed=reviewed
    )
    system += "\n\n" + render_prompt(
        "memory/source_subject_types.system.jinja",
        entity_types={
            kind.key: kind.description for kind in ENTITY_ONTOLOGY if kind.key != "you"
        },
    )
    system += "\n\n" + render_prompt("memory/subject_evidence_fields.system.jinja")
    if canonical_user:
        system += "\n\n" + render_prompt("memory/declared_user.system.jinja")
    return system, user
