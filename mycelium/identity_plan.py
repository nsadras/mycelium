"""Evidence-backed identity resolution, independent of wiki placement."""

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.ontology import PageType, ENTITY_TYPES
from mycelium.prompting import render_prompt_pair


class IdentitySubject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str
    title: str = Field(min_length=1)
    entity_type: PageType
    resolution: Literal["existing", "new", "review_required"]
    entity_id: str
    aliases: list[str]
    supporting_evidence: list[str] = Field(min_length=1)
    participant_evidence: list[str]
    candidate_entity_ids: list[str]
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


def _subject_variants(evidence_ids, participant_roles, registry_types):
    """Canonical references select stored IDs; only the application allocates new IDs."""
    evidence_type = Literal.__getitem__(tuple(sorted(set(evidence_ids) | set(participant_roles))))
    participants = [p for p, role in participant_roles.items()
                    if not (role == "user" and "you" in registry_types)]
    grounded = create_model(
        "GroundedIdentitySubject", __base__=IdentitySubject,
        supporting_evidence=(list[evidence_type], Field(min_length=1)),
        participant_evidence=(list[Literal.__getitem__(tuple(participants))], ...)
        if participants else (list[str], Field(max_length=0)),
    )
    non_user_type = Literal.__getitem__(tuple(t for t in ENTITY_TYPES if t != "you"))
    variants = [create_model(
        "NewIdentity", __base__=grounded,
        resolution=(Literal["new"], ...), entity_id=(Literal[""], ...),
        entity_type=(non_user_type, ...),
        candidate_entity_ids=(list[str], Field(max_length=0)),
    ), create_model(
        "UnresolvedIdentity", __base__=grounded,
        resolution=(Literal["review_required"], ...), entity_id=(Literal[""], ...),
        entity_type=(non_user_type, ...),
        candidate_entity_ids=(list[Literal.__getitem__(tuple(registry_types))], ...)
        if registry_types else (list[str], Field(max_length=0)),
    )]
    for entity_type in sorted(set(registry_types.values()) - {"you"}):
        ids = tuple(e for e, t in registry_types.items() if t == entity_type)
        variants.append(create_model(
            f"Existing_{entity_type}_Identity", __base__=grounded,
            resolution=(Literal["existing"], ...), entity_id=(Literal.__getitem__(ids), ...),
            entity_type=(Literal.__getitem__((entity_type,)), ...),
            candidate_entity_ids=(list[str], Field(max_length=0)),
        ))
    if "you" in registry_types and not any(role == "user" for role in participant_roles.values()):
        variants.append(create_model(
            "MentionedUserIdentity", __base__=grounded,
            resolution=(Literal["existing"], ...), entity_id=(Literal["you"], ...),
            entity_type=(Literal["you"], ...), participant_evidence=(list[str], Field(max_length=0)),
            candidate_entity_ids=(list[str], Field(max_length=0)),
        ))
    return Union[tuple(variants)]


def identity_plan_model(evidence_ids, participant_roles, registry_types):
    """Validate declared IDs/roles, never infer identity from language."""
    allowed = set(evidence_ids) | set(participant_roles)
    user_aliases = [p for p, role in participant_roles.items() if role == "user" and "you" in registry_types]
    evidence_type = Literal.__getitem__(tuple(sorted(allowed)))
    subject_model = _subject_variants(evidence_ids, participant_roles, registry_types)

    class IdentityPlan(BaseModel):
        model_config = ConfigDict(extra="forbid")
        subjects: list[subject_model]

        @model_validator(mode="after")
        def validate_references(self):
            subjects = [*self.subjects, *([self.user] if user_aliases else [])]
            nodes = {n.node_id: n for n in subjects}
            if len(nodes) != len(subjects) or any(not n for n in nodes):
                raise ValueError("Subject IDs must be nonempty and unique")
            existing = []
            for n in subjects:
                if set(n.supporting_evidence) - allowed:
                    raise ValueError("Unknown supporting evidence")
                if n.resolution == "existing":
                    existing.append(n.entity_id)
            if len(existing) != len(set(existing)):
                raise ValueError("Combine evidence for the same canonical identity in one subject")
            bound = [p for n in subjects for p in n.participant_evidence]
            if len(bound) != len(set(bound)):
                raise ValueError("Each participant binds to exactly one subject")
            participants = {p: n.node_id for n in subjects for p in n.participant_evidence}
            if not set(user_aliases).issubset(participants):
                raise ValueError("Every explicitly bound user occurrence must be represented")
            for alias, node_id in participants.items():
                node = nodes.get(node_id)
                if node is None or node.entity_type not in {"person", "you"}:
                    raise ValueError("Participant must reference a declared person/user subject")
                if participant_roles[alias] == "user" and "you" in registry_types:
                    if node.resolution != "existing" or node.entity_id != "you":
                        raise ValueError("Explicit user participant must bind to canonical You")
            for n in subjects:
                if not n.participant_evidence and not set(n.supporting_evidence).intersection(evidence_ids):
                    raise ValueError("Subjects discussed in claims must cite claim evidence")
            return self

    if not user_aliases:
        return IdentityPlan
    user_model = create_model(
        "DeclaredUserIdentity", __base__=IdentitySubject,
        node_id=(Literal["you"], ...), title=(Literal["You"], ...),
        entity_type=(Literal["you"], ...), resolution=(Literal["existing"], ...),
        entity_id=(Literal["you"], ...),
        supporting_evidence=(list[evidence_type], Field(min_length=1)),
        participant_evidence=(list[Literal.__getitem__(tuple(user_aliases))],
                              Field(min_length=len(user_aliases), max_length=len(user_aliases))),
        candidate_entity_ids=(list[str], Field(max_length=0)),
    )
    return create_model("UserBoundIdentityPlan", __base__=IdentityPlan, user=(user_model, ...))


def planned_subjects(plan):
    return [*plan["subjects"], *([plan["user"]] if "user" in plan else [])]


def identity_plan_prompt(registry: str, evidence: str, reviewed: str, pending: str, bindings: str = "none"):
    return render_prompt_pair(
        "memory/identity_plan", registry=registry, evidence=evidence,
        reviewed=reviewed, pending=pending, bindings=bindings,
    )


def declared_user_bindings(participants):
    """Expose user-declared source identity, without interpreting a speaker's name."""
    return "\n".join(
        f"{alias}: speaker label {name!r} IS canonical entity_id=you (same person, not a new identity)."
        for alias, (_, name, role) in participants.items() if role == "user"
    ) or "none"
