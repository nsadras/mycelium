"""Admit independent records by exact structure, never repair their meaning."""

from collections import Counter

from pydantic import ValidationError

from mycelium.ollama import StructuredOutputError


def retention(payload, response):
    from mycelium.memory_contract import Subject, Memory, Change, retention_model, subject_type_error

    fields = {"subjects": Subject, "memories": Memory, "changes": Change}
    if not isinstance(response, dict) or response.keys() != fields.keys() or any(
        not isinstance(response[key], list) for key in fields
    ):
        raise StructuredOutputError("Retention requires subjects, memories and changes lists")
    rejected = []

    def reject(kind, index, row, reason):
        rejected.append({"category": "model_output_contract", "collection": kind,
                         "index": index, "reason": reason, "record": row})

    def rows(kind):
        duplicates = Counter(row.get("id") for row in response[kind]
                             if isinstance(row, dict) and isinstance(row.get("id"), str))
        for index, row in enumerate(response[kind]):
            try:
                parsed = fields[kind].model_validate(row)
                if kind != "changes" and duplicates[parsed.id] > 1:
                    raise ValueError("Duplicate local ID; all conflicting records were rejected")
                yield index, parsed.model_dump()
            except (ValueError, ValidationError) as exc:
                reject(kind, index, row, str(exc))

    existing = {s["id"]: s for s in payload.get("existing_subjects", [])}
    allowed = set(payload["new_subject_ids"]) | existing.keys()
    participants = {p["id"]: p for p in payload.get("participants", [])}
    segments = {s["id"] for s in payload["segments"]}
    context = {s["id"] for s in payload.get("context_segments", [])}
    prior = {m["id"] for m in payload.get("prior_memories", [])}
    subjects = []
    for index, row in rows("subjects"):
        reason = "Subject ID was not supplied" if row["id"] not in allowed else subject_type_error(row, existing)
        if reason:
            reject("subjects", index, row, reason)
        else:
            subjects.append((index, row))
    # An illegal project binding must not invalidate a valid person's binding.
    # Count conflicts only among structurally eligible assignments.
    for index, row in subjects:
        kept = []
        for pid in row["participant_ids"]:
            participant = participants.get(pid)
            entity_type = existing.get(row["id"], row)["entity_type"]
            reason = ("Participant ID was not supplied" if participant is None else
                      "A participant can only bind to a person" if entity_type not in {"person", "you"} else
                      "Established participant binding cannot change" if participant.get("subject_id") not in {None, row["id"]} else None)
            if reason:
                reject("participant_bindings", index, {"subject_id": row["id"], "participant_id": pid}, reason)
            else:
                kept.append(pid)
        row["participant_ids"] = kept
    assignments = Counter(pid for _, row in subjects for pid in row["participant_ids"])
    for index, row in subjects:
        for pid in row["participant_ids"]:
            if assignments[pid] > 1:
                reject("participant_bindings", index, {"subject_id": row["id"], "participant_id": pid},
                       "Conflicting participant bindings")
        row["participant_ids"] = [pid for pid in row["participant_ids"] if assignments[pid] == 1]
    output = {"subjects": [row for _, row in subjects], "memories": [], "changes": []}
    subjects = {row["id"] for row in output["subjects"]} | existing.keys()
    for index, row in rows("memories"):
        reason = ("New memory ID conflicts with prior evidence" if row["id"] in prior else
                  "Citation was not supplied" if not set(row["segment_ids"]) <= segments | context else
                  "No new source evidence was cited" if not set(row["segment_ids"]) & segments else
                  "Subject is unknown or its declaration was rejected" if not set(row["subject_ids"]) <= subjects else None)
        if reason:
            reject("memories", index, row, reason)
        else:
            output["memories"].append(row)
    memories = {row["id"] for row in output["memories"]}
    for index, row in rows("changes"):
        if row["earlier_id"] not in prior or row["later_id"] not in memories:
            reject("changes", index, row, "Change references unknown or rejected evidence")
        else:
            output["changes"].append(row)
    # The same strict persistence contract remains the final integrity check.
    return retention_model(payload).model_validate(output).model_dump(), rejected
