"""Expand exact human-reviewed occurrence IDs to claim evidence IDs."""

from copy import deepcopy


def expand_review_evidence(plan, bindings):
    """Map exact reviewed occurrence IDs back to their cited claim aliases."""
    expanded = deepcopy(plan)
    for node in [
        *expanded["subjects"],
        *([expanded["user"]] if "user" in expanded else []),
    ]:
        node["supporting_evidence"] = list(
            dict.fromkeys(
                bindings[alias]["claim_alias"] if alias in bindings else alias
                for alias in node["supporting_evidence"]
            )
        )
    return expanded
