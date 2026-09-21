"""Budget the exact compacted contract; optional context never forces a split."""

from copy import deepcopy
import json

from mycelium.budget import ContextBudgetError, request_tokens, output_contract
from mycelium.memory_inputs import compact_retention, compact_presentation


OUTPUT_TOKENS = 8192


def presentation_request(payload):
    from mycelium.memory_contract import PRESENT, presentation_model
    request, _ = compact_presentation(payload)
    schema = presentation_model(request).model_json_schema()
    return json.dumps({"messages": [
        {"role": "system", "content": PRESENT},
        {"role": "user", "content": output_contract(json.dumps(request, ensure_ascii=False), schema)},
    ]}, ensure_ascii=False)


def retention_size(payload):
    from mycelium.memory_contract import RETAIN, retention_model
    request, _ = compact_retention(payload)
    return request_tokens([
        {"role": "system", "content": RETAIN},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ], retention_model(request).model_json_schema())


def fit_retention(payload, context_window):
    """Keep all new evidence and fixed identities; trim optional context by order."""
    selected = deepcopy(payload)
    allowance = context_window - OUTPUT_TOKENS - 2048
    omitted = {"prior_memory_ids": [], "context_segment_ids": [], "candidate_ids": []}
    fixed = {p["subject_id"] for p in selected["participants"] if p["subject_id"]} | {"you"}
    while (size := retention_size(selected)) > allowance:
        if selected["prior_memories"]:
            omitted["prior_memory_ids"].append(selected["prior_memories"].pop()["id"])
        else:
            optional = [s for s in selected["existing_subjects"] if s["id"] not in fixed]
            if optional:
                removed = optional[-1]
                selected["existing_subjects"].remove(removed)
                omitted["candidate_ids"].append(removed["id"])
            elif any(s.get("evidence") for s in selected["existing_subjects"]):
                for subject in selected["existing_subjects"]:
                    for evidence in subject.pop("evidence", []):
                        omitted["prior_memory_ids"].append(evidence["id"])
            elif selected["context_segments"]:
                omitted["context_segment_ids"].append(selected["context_segments"].pop(0)["id"])
            else:
                raise ContextBudgetError(f"New evidence and required identity context exceed input allowance ({size} > {allowance})")
    return selected, {"estimated_input_tokens": size, "input_allowance": allowance, "omitted": omitted}
