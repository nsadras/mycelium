"""Source-scoped participant bindings; semantic assignments come from the model or user."""

import hashlib
import json


def participant_id(source, segment):
    # A declared speaker key identifies a source participant, not a global person.
    # The original diarization key keeps equally named speakers distinct.
    if segment.participant_id is not None:
        key = ["id", segment.participant_id]
    elif segment.speaker is not None or segment.role is not None:
        key = ["label", segment.role, segment.speaker]
    else:
        return None
    digest = hashlib.sha256(json.dumps([source.source_id, key]).encode()).hexdigest()[:20]
    return "participant-" + digest


def binding(artifacts, pid):
    if pid is None:
        return None
    try:
        return artifacts.db.get("participant-bindings", pid)
    except FileNotFoundError:
        return None


def participants(artifacts, source):
    rows = {}
    try:
        owner = artifacts.get_entity("you")
    except FileNotFoundError:
        owner = None
    for segment in source.segments:
        pid = participant_id(source, segment)
        if pid is None or pid in rows or segment.role == "system":
            continue
        fixed = binding(artifacts, pid)
        entity_id = fixed["entity_id"] if fixed else (
            "you" if segment.role == "user" and owner is not None and owner.status == "active" else None)
        if entity_id and artifacts.get_entity(entity_id).status != "active":
            raise ValueError("Participant binding refers to an inactive identity; review it before Build")
        rows[pid] = {"id": pid, "source_id": source.source_id, "name": segment.speaker or segment.role, "role": segment.role,
                     "subject_id": entity_id,
                     "binding_origin": fixed["origin"] if fixed else "user" if entity_id else None}
    return list(rows.values())


def save_binding(artifacts, source_id, pid, entity_id, decision_id, *, origin):
    entity = artifacts.get_entity(entity_id)
    if entity.status != "active" or entity.entity_type not in {"person", "you"}:
        raise ValueError("Participant bindings require an active person")
    artifacts.db.put("participant-bindings", pid, {
        "participant_id": pid, "source_id": source_id, "entity_id": entity_id,
        "decision_id": decision_id, "origin": origin,
    })
