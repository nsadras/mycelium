"""Neutral model decisions for lifecycle mechanics; bounded native runs assess meaning."""

import json


def lifecycle_response(_system, user, schema, **kwargs):
    stage = kwargs.get("debug_label")
    if stage == "memory-correction":
        return {"about": [{"entity": "user", "role": "subject"}], "claim_type": "preference",
                "predicate": None, "temporal_status": "atemporal",
                "facets": {"times": [], "inference_basis": None}}
    payload = json.loads(user)
    if stage == "memory-retention":
        sid = payload["existing_subjects"][0]["id"] if payload["existing_subjects"] else payload["new_subject_ids"][0]
        value = {"subjects": [{"id": sid, "title": "You", "entity_type": "you", "participant_ids": []}],
                 "memories": [{"id": f"m{i}", "text": s["text"], "segment_ids": [s["id"]], "subject_ids": [sid]}
                              for i, s in enumerate(payload["segments"])], "changes": []}
    elif stage == "memory-presentation":
        protected = {cid for f in payload["existing_items"] if f["protected"] for cid in f["memory_ids"]}
        value = {"items": [{"owner_id": payload["affected_subject_ids"][0], "heading": "Preferences",
                            "memory_ids": [m["id"]], "linked_subject_ids": [], "state": "current"}
                          for m in payload["memories"] if m["id"] not in protected]}
    else:
        raise AssertionError(f"Unexpected lifecycle model call: {stage}")
    return value if isinstance(schema, dict) else schema.model_validate(value).model_dump()
