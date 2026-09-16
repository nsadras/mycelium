"""Bind user-reviewed identity occurrences without owning whole claims."""

import json
from copy import deepcopy

from pydantic import model_validator

from mycelium.identity_plan import identity_plan_model, identity_plan_prompt
from mycelium.prompting import render_prompt_pair


def reviewed_identity_model(evidence_ids, participant_roles, registry_types, bindings):
    for binding in bindings.values():
        if binding["entity_id"] not in registry_types or binding["claim_alias"] not in evidence_ids:
            raise ValueError("A reviewed identity must cite an eligible entity and claim")
    base = identity_plan_model([*evidence_ids, *bindings], participant_roles, registry_types)

    class ReviewedIdentityPlan(base):
        @model_validator(mode="after")
        def preserve_reviewed_occurrences(self):
            subjects = [(n.entity_id if n.resolution == "existing" else None, n)
                        for n in self.subjects]
            if "user" in type(self).model_fields:
                subjects.append(("you", self.user))
            for alias, binding in bindings.items():
                matches = [entity_id for entity_id, node in subjects if alias in node.supporting_evidence]
                if matches != [binding["entity_id"]]:
                    raise ValueError(f"The human identity binding {alias} must occur exactly once on {binding['entity_id']}")
            return self

    return ReviewedIdentityPlan


def reviewed_identity_prompt(registry, evidence, reviewed, pending, source_bindings, bindings):
    system, user = identity_plan_prompt(registry, evidence, reviewed, pending, source_bindings)
    if bindings:
        extra_system, extra_user = render_prompt_pair("memory/identity_review_bindings",
            payload=json.dumps(bindings, ensure_ascii=False))
        system += "\n\n" + extra_system
        user += "\n\n" + extra_user
    return system, user


def expand_review_evidence(plan, bindings):
    """Map exact reviewed occurrence IDs back to their cited claim aliases."""
    expanded = deepcopy(plan)
    for node in [*expanded["subjects"], *([expanded["user"]] if "user" in expanded else [])]:
        node["supporting_evidence"] = list(dict.fromkeys(
            bindings[alias]["claim_alias"] if alias in bindings else alias
            for alias in node["supporting_evidence"]
        ))
    return expanded
