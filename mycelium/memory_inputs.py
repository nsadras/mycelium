"""Compact model inputs with reversible references to canonical evidence.

These transformations change representation, never identity or claim ownership.
Only declared reference fields are rewritten; human text remains literal.
"""

from copy import deepcopy


SINGLE_IDS = {"id", "owner_id", "subject_id", "memory_id", "source_id",
              "target_claim_id", "proposal_id"}
MULTIPLE_IDS = {"subject_ids", "segment_ids", "new_subject_ids", "memory_ids",
                "linked_subject_ids", "affected_subject_ids", "incoming_claim_ids",
                "target_claim_ids", "affected_entity_ids"}


class RequestIds:
    def __init__(self):
        self.forward = {}
        self.reverse = {}

    def reference(self, identifier):
        if identifier not in self.forward:
            local = f"r{len(self.forward)}"
            self.forward[identifier] = local
            self.reverse[local] = identifier
        return self.forward[identifier]

    def encode(self, value):
        if isinstance(value, list):
            return [self.encode(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key == "metadata":
                result[key] = deepcopy(item)
            elif key in SINGLE_IDS and item is not None:
                result[key] = self.reference(item)
            elif key in MULTIPLE_IDS:
                result[key] = [self.reference(identifier) for identifier in item]
            else:
                result[key] = self.encode(item)
        return result

    def retention(self, value):
        result = deepcopy(value)
        for subject in result["subjects"]:
            subject["id"] = self.reverse[subject["id"]]
        for memory in result["memories"]:
            for field in ("segment_ids", "subject_ids"):
                memory[field] = [self.reverse[identifier] for identifier in memory[field]]
        for change in result["changes"]:
            change["earlier_id"] = self.reverse[change["earlier_id"]]
        return result

    def presentation(self, value):
        result = deepcopy(value)
        for item in result["items"]:
            item["owner_id"] = self.reverse[item["owner_id"]]
            for field in ("memory_ids", "linked_subject_ids"):
                item[field] = [self.reverse[identifier] for identifier in item[field]]
        return result


def compact_retention(payload):
    data = deepcopy(payload)
    for field in ("segments", "context_segments"):
        for row in data.get(field, []):
            # Citations map back to the complete canonical segment, including its
            # source and metadata. A differing timestamp remains in the request.
            row.pop("source_id", None)
            if row.get("source_time") == data.get("occurred_at"):
                row.pop("source_time", None)
            metadata = row.get("metadata", {})
            metadata.pop("engram_segment_id", None)
            if not metadata:
                row.pop("metadata", None)
            if row.get("role") is None:
                row.pop("role", None)
    ids = RequestIds()
    return ids.encode(data), ids


def compact_presentation(payload):
    ids = RequestIds()
    return ids.encode(payload), ids
