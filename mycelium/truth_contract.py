"""Owner-independent comparisons of canonical statements."""

from collections.abc import Collection, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from mycelium.prompting import render_prompt_pair


class TruthComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["same", "distinct", "unresolved"]
    relation: Literal["no_change", "contradicts", "left_supersedes_right", "right_supersedes_left"]
    reason: str = Field(min_length=1, max_length=800)

    @model_validator(mode="after")
    def established_scope_for_change(self):
        if self.relation != "no_change" and self.scope != "same":
            raise ValueError("A truth change requires established same scope")
        return self


def truth_comparison_model(pair_ids: Collection[str]) -> type[BaseModel]:
    if not pair_ids or len(set(pair_ids)) != len(pair_ids):
        raise ValueError("Truth comparison requires distinct pair IDs")
    comparisons = create_model(
        "ExactTruthComparisons", __config__=ConfigDict(extra="forbid"),
        **{pair_id: (TruthComparison, ...) for pair_id in pair_ids},
    )
    return create_model(
        "TruthComparisonPlan", __config__=ConfigDict(extra="forbid"),
        comparisons=(comparisons, ...),
    )


def truth_comparison_prompt(payload: str):
    return render_prompt_pair("memory/truth_comparison", payload=payload)


def truth_candidates_model(allowed: Mapping[str, Collection[str]]) -> type[BaseModel]:
    """Every incoming alias has its own legal targets, excluding its exact ID."""
    if not allowed or any(not values for values in allowed.values()):
        raise ValueError("Candidate selection requires nonempty eligible targets")
    fields = {}
    for alias, values in allowed.items():
        targets = tuple(sorted(set(values)))
        comparisons = create_model(
            f"EligibleComparisons{alias}", __config__=ConfigDict(extra="forbid"),
            **{target: (Literal["compare", "unrelated", "uncertain"], ...) for target in targets},
        )
        decision = create_model(
            f"TruthCandidates{alias}", __config__=ConfigDict(extra="forbid"),
            candidates=(comparisons, ...),
            reason=(str, Field(min_length=1, max_length=400)),
        )
        fields[alias] = (decision, ...)
    decisions = create_model("TruthCandidateDecisions", __config__=ConfigDict(extra="forbid"), **fields)
    return create_model("TruthCandidatePlan", __config__=ConfigDict(extra="forbid"), decisions=(decisions, ...))
