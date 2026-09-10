"""Identity decisions with known IDs and registry metadata supplied by the application."""

from typing import Literal, Union
from pydantic import ConfigDict, Field, create_model, model_validator
from mycelium.ontology import ENTITY_TYPES
from mycelium.prompting import render_prompt_pair


def identity_plan_model(evidence_ids, participant_roles, registry_types):
    allowed = set(evidence_ids) | set(participant_roles)
    user_aliases = [
        p
        for p, role in participant_roles.items()
        if role == "user" and "you" in registry_types
    ]
    participants = tuple(p for p in participant_roles if p not in user_aliases)
    evidence_type = Literal.__getitem__(tuple(sorted(allowed)))
    common = dict(
        reason=(str, Field(min_length=1, max_length=500)),
        supporting_evidence=(list[evidence_type], Field(min_length=1)),
        participant_evidence=(list[Literal.__getitem__(participants)], ...)
        if participants
        else (list[str], Field(max_length=0)),
        aliases=(list[str], ...),
    )
    new_type = Literal.__getitem__(tuple(t for t in ENTITY_TYPES if t != "you"))
    new = create_model(
        "NewIdentity",
        __config__=ConfigDict(extra="forbid"),
        **common,
        resolution=(Literal["new"], ...),
        title=(str, Field(min_length=1)),
        entity_type=(new_type, ...),
    )
    review = create_model(
        "UnresolvedIdentity",
        __config__=ConfigDict(extra="forbid"),
        **common,
        resolution=(Literal["review_required"], ...),
        title=(str, Field(min_length=1)),
        entity_type=(new_type, ...),
        candidate_entity_ids=(list[Literal.__getitem__(tuple(registry_types))], ...)
        if registry_types
        else (list[str], Field(max_length=0)),
    )
    variants = [new, review]
    existing_ids = tuple(e for e in registry_types if not (e == "you" and user_aliases))
    if existing_ids:
        variants.append(
            create_model(
                "ExistingIdentity",
                __config__=ConfigDict(extra="forbid"),
                **common,
                resolution=(Literal["existing"], ...),
                entity_id=(Literal.__getitem__(existing_ids), ...),
                title=(
                    str | None,
                    Field(
                        description="New name explicitly established by the evidence; null retains the registry title",
                        min_length=1,
                    ),
                ),
            )
        )
    fields = {}
    if user_aliases:
        user = create_model(
            "DeclaredUser",
            __config__=ConfigDict(extra="forbid"),
            **{
                **common,
                "participant_evidence": (
                    list[Literal.__getitem__(tuple(user_aliases))],
                    Field(min_length=1),
                ),
            },
        )
        fields["user"] = (user, ...)
    fields["subjects"] = (list[Union[tuple(variants)]], ...)
    base = create_model(
        "IdentityPlanFields", __config__=ConfigDict(extra="forbid"), **fields
    )

    class IdentityPlan(base):
        @model_validator(mode="after")
        def validate_bindings(self):
            nodes = [*self.subjects, *([self.user] if user_aliases else [])]
            existing = [
                n.entity_id for n in self.subjects if n.resolution == "existing"
            ]
            if len(existing) != len(set(existing)):
                raise ValueError(
                    "Combine evidence for the same canonical identity in one subject"
                )
            bound = [p for n in nodes for p in n.participant_evidence]
            if len(bound) != len(set(bound)):
                raise ValueError("Each participant binds to exactly one subject")
            if not set(user_aliases).issubset(bound):
                raise ValueError(
                    "Every explicitly bound user occurrence must be represented"
                )
            for n in nodes:
                kind = (
                    "you"
                    if user_aliases and n is self.user
                    else registry_types[n.entity_id]
                    if n.resolution == "existing"
                    else n.entity_type
                )
                if n.participant_evidence and kind not in {"person", "you"}:
                    raise ValueError("Participants must identify people")
                if not n.participant_evidence and not set(
                    n.supporting_evidence
                ).intersection(evidence_ids):
                    raise ValueError(
                        "Subjects discussed in claims must cite claim evidence"
                    )
            return self

    return IdentityPlan


def planned_subjects(plan, registry):
    """Attach exact registry metadata and local sequence IDs, without resolving meaning."""
    nodes = []
    for index, value in enumerate(plan["subjects"], 1):
        node = {**value, "node_id": f"n{index:03d}"}
        if node["resolution"] == "existing":
            entity = registry[node["entity_id"]]
            node.update(
                title=entity.title if node["title"] is None else node["title"],
                entity_type=entity.entity_type,
                candidate_entity_ids=[],
            )
        else:
            node["entity_id"] = ""
            if node["resolution"] == "new":
                node["candidate_entity_ids"] = []
        nodes.append(node)
    if "user" in plan:
        nodes.append(
            {
                **plan["user"],
                "node_id": "you",
                "entity_id": "you",
                "entity_type": "you",
                "resolution": "existing",
                "title": "You",
                "candidate_entity_ids": [],
            }
        )
    return nodes


def identity_plan_prompt(
    registry: str, evidence: str, reviewed: str, pending: str, bindings: str = "none"
):
    return render_prompt_pair(
        "memory/identity_plan",
        registry=registry,
        evidence=evidence,
        reviewed=reviewed,
        pending=pending,
        bindings=bindings,
    )


def declared_user_bindings(participants):
    """Expose user-declared source identity, without interpreting a speaker's name."""
    return (
        "\n".join(
            f"{alias}: speaker label {name!r} IS canonical entity_id=you (same person, not a new identity)."
            for alias, (_, name, role) in participants.items()
            if role == "user"
        )
        or "none"
    )
