"""Compact model inputs with reversible references to canonical evidence.

These transformations change representation, never identity or claim ownership.
Only declared reference fields are rewritten; human text remains literal.
"""

from copy import deepcopy
from dataclasses import asdict
import json
from typing import Any, Literal, NotRequired, TypedDict

from mycelium.operations import MemoryEvidence
from mycelium.artifacts import ArtifactStore, MemoryClaim
from mycelium.artifact_integrity import cited_source_segments
from mycelium import identity_context


# These describe existing dictionaries for readers and type checkers. The dynamic
# schemas in memory_contract validate model decisions against each request's IDs.
class RetentionInput(TypedDict):
    source_type: str
    occurred_at: str | None
    participants: list[dict[str, Any]]
    metadata: dict[str, Any]
    segments: list[dict[str, Any]]
    context_segments: list[dict[str, Any]]
    prior_memories: list[dict[str, Any]]
    existing_subjects: list[dict[str, Any]]
    new_subject_ids: list[str]


class RetentionResult(TypedDict):
    subjects: list[dict[str, Any]]
    memories: list[dict[str, Any]]
    changes: list[dict[str, Any]]
    _rejections: NotRequired[list[dict[str, Any]]]


class PresentationInput(TypedDict):
    subjects: list[dict[str, Any]]
    affected_subject_ids: list[str]
    memories: list[dict[str, Any]]
    context_memories: list[dict[str, Any]]
    existing_items: list[dict[str, Any]]
    pending_changes: list[dict[str, Any]]
    page_exclusions: list[dict[str, str]]


class PresentationResult(TypedDict):
    items: list[dict[str, Any]]


PASSAGE_CHARACTERS = 1200


SINGLE_IDS = {
    "id",
    "owner_id",
    "subject_id",
    "memory_id",
    "source_id",
    "target_claim_id",
    "proposal_id",
    "participant_id",
    "speaker_subject_id",
}
MULTIPLE_IDS = {
    "subject_ids",
    "segment_ids",
    "new_subject_ids",
    "memory_ids",
    "linked_subject_ids",
    "affected_subject_ids",
    "incoming_claim_ids",
    "target_claim_ids",
    "affected_entity_ids",
    "participant_ids",
}


class RequestIds:
    def __init__(self) -> None:
        self.forward: dict[str, str] = {}
        self.reverse: dict[str, str] = {}
        self.citations: dict[str, list[str]] = {}

    def reference(self, identifier: str) -> str:
        if identifier not in self.forward:
            local = f"r{len(self.forward)}"
            self.forward[identifier] = local
            self.reverse[local] = identifier
        return self.forward[identifier]

    def encode(self, value: Any) -> Any:
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

    def decode_retention_result(self, value: RetentionResult) -> RetentionResult:
        result = deepcopy(value)
        for subject in result["subjects"]:
            subject["id"] = self.reverse[subject["id"]]
            subject["participant_ids"] = [
                self.reverse[pid] for pid in subject["participant_ids"]
            ]
        for memory in result["memories"]:
            memory["segment_ids"] = list(
                dict.fromkeys(
                    sid
                    for reference in memory["segment_ids"]
                    for sid in self.citations[reference]
                )
            )
            memory["subject_ids"] = [
                self.reverse[identifier] for identifier in memory["subject_ids"]
            ]
        for change in result["changes"]:
            change["earlier_id"] = self.reverse[change["earlier_id"]]
        return result

    def decode_presentation_result(
        self, value: PresentationResult
    ) -> PresentationResult:
        result = deepcopy(value)
        for item in result["items"]:
            item["owner_id"] = self.reverse[item["owner_id"]]
            for field in ("memory_ids", "linked_subject_ids"):
                item[field] = [self.reverse[identifier] for identifier in item[field]]
        return result


def compact_retention(payload: RetentionInput) -> tuple[RetentionInput, RequestIds]:
    data = deepcopy(payload)
    citations = {}
    field: Literal["segments", "context_segments"]
    for field in ("segments", "context_segments"):
        passages: list[dict[str, Any]] = []
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
            if (
                passages
                and row.get("source_id") is not None
                and index is not None
                and previous_index is not None
                and index == previous_index + 1
                and context == previous_context
                and len(passages[-1]["text"]) + 1 + len(row["text"])
                <= PASSAGE_CHARACTERS
            ):
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


def compact_presentation(
    payload: PresentationInput,
) -> tuple[PresentationInput, RequestIds]:
    ids = RequestIds()
    return ids.encode(payload), ids


def compact_selection_evidence(
    evidence: MemoryEvidence, aliases: dict[str, str]
) -> tuple[str, dict[str, str]]:
    """Share evidence once and shorten references without rewriting human text."""
    ids = RequestIds()
    ids.forward = {canonical: alias for alias, canonical in aliases.items()}
    ids.reverse = dict(aliases)
    single = {
        "record_id",
        "claim_id",
        "source_id",
        "segment_id",
        "entity_id",
        "subject_entity_id",
        "proposal_id",
        "evidence_segment_id",
        "anchor_segment_id",
    }
    multiple = {"claim_ids", "segment_ids", "incoming_claim_ids", "target_claim_ids"}
    direct = {r.record_id for r in evidence.records if r.record_type == "claim"}

    def encode(value):
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if item is None or item == [] or item == () or key == "revision":
                continue
            if key in single:
                result[key] = ids.reference(item)
            elif key in multiple:
                result[key] = [ids.reference(identifier) for identifier in item]
            elif key == "canonical_claims":
                # The full assertion is already present in its selectable record.
                remaining = [c for c in item if c["claim_id"] not in direct]
                if remaining:
                    result[key] = encode(remaining)
            else:
                result[key] = encode(item)
        return result

    return json.dumps(
        encode(asdict(evidence)), ensure_ascii=False, separators=(",", ":")
    ), ids.reverse


def serialize_claim_context(
    artifacts: ArtifactStore, claim: MemoryClaim
) -> dict[str, Any]:
    """Include cited attribution and bound speaker identity alongside a retained claim."""
    refs = artifacts.list_entity_references(claim_id=claim.claim_id, status="active")
    provenance = []
    for _, source, segments in cited_source_segments(artifacts, claim):
        for segment in segments:
            row = {
                "speaker": segment.speaker,
                "role": segment.role,
                "source_type": source.source_type,
                "source_time": segment.timestamp or source.occurred_at,
            }
            bound = identity_context.binding(
                artifacts, identity_context.participant_id(source, segment)
            )
            if bound:
                row["speaker_subject_id"] = bound["entity_id"]
            if row not in provenance:
                provenance.append(row)
    return {
        "id": claim.claim_id,
        "text": claim.text,
        "subject_ids": sorted({r.entity_id for r in refs if r.entity_id}),
        "provenance": provenance,
        "revisions": claim.links,
        "temporal": claim.facets.get("temporal", []),
    }
