"""Compact model inputs with reversible references to canonical evidence.

These transformations change representation, never identity or claim ownership.
Only declared reference fields are rewritten; human text remains literal.
"""

from copy import deepcopy


PASSAGE_CHARACTERS = 1200


SINGLE_IDS = {"id", "owner_id", "subject_id", "memory_id", "source_id",
              "target_claim_id", "proposal_id", "participant_id", "speaker_subject_id"}
MULTIPLE_IDS = {"subject_ids", "segment_ids", "new_subject_ids", "memory_ids",
                "linked_subject_ids", "affected_subject_ids", "incoming_claim_ids",
                "target_claim_ids", "affected_entity_ids", "participant_ids"}


class RequestIds:
    def __init__(self):
        self.forward = {}
        self.reverse = {}
        self.citations = {}

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
            subject["participant_ids"] = [self.reverse[pid] for pid in subject["participant_ids"]]
        for memory in result["memories"]:
            memory["segment_ids"] = list(dict.fromkeys(
                sid for reference in memory["segment_ids"] for sid in self.citations[reference]))
            memory["subject_ids"] = [self.reverse[identifier] for identifier in memory["subject_ids"]]
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
    citations = {}
    for field in ("segments", "context_segments"):
        passages = []
        previous_index, previous_context = None, None
        for row in data.get(field, []):
            # An index gap means omitted evidence; never join across it. Source
            # and attribution boundaries are exact structure, not semantic guesses.
            index = row.pop("index", None)
            if row.get("source_time") == data.get("occurred_at"):
                row.pop("source_time", None)
            metadata = row.get("metadata", {})
            metadata.pop("engram_segment_id", None)
            if not metadata:
                row.pop("metadata", None)
            if row.get("role") is None:
                row.pop("role", None)
            context = {k: v for k, v in row.items() if k not in {"id", "text"}}
            if (passages and row.get("source_id") is not None and index is not None
                    and previous_index is not None and index == previous_index + 1
                    and context == previous_context
                    and len(passages[-1]["text"]) + 1 + len(row["text"]) <= PASSAGE_CHARACTERS):
                passages[-1]["text"] += " " + row["text"]
                citations[passages[-1]["id"]].append(row["id"])
            else:
                passages.append(row)
                citations[row["id"]] = [row["id"]]
            previous_index, previous_context = index, context
        for row in passages:
            row.pop("source_id", None)
        data[field] = passages
    ids = RequestIds()
    request = ids.encode(data)
    ids.citations = {ids.forward[sid]: members for sid, members in citations.items()}
    return request, ids


def compact_presentation(payload):
    ids = RequestIds()
    return ids.encode(payload), ids
