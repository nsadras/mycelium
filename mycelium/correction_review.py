"""Durable, explicit date choices for relative-time corrections."""

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Literal
from uuid import uuid4

from mycelium.artifacts import ArtifactStore, MemoryClaim
from mycelium.structured_outputs import ReplacementMetadata
from mycelium.temporal import source_time_anchors
from mycelium.temporal_contract import resolve_annotation


@dataclass(frozen=True)
class CorrectionPreview:
    draft_id: str
    claim_id: str
    text: str
    times: list[dict]
    status: Literal["review_required"] = "review_required"


def fingerprint(record) -> str:
    return hashlib.sha256(
        json.dumps(asdict(record), sort_keys=True).encode()
    ).hexdigest()


def review_is_current(artifacts: ArtifactStore, draft: dict) -> bool:
    try:
        return draft["claim_fingerprint"] == fingerprint(
            artifacts.get_claim(draft["claim_id"])
        ) and all(
            fingerprint(artifacts.get_source(sid)) == stamp
            for sid, stamp in draft["source_fingerprints"].items()
        )
    except FileNotFoundError:
        return False


def relative_times(metadata: ReplacementMetadata) -> dict[str, object]:
    return {
        str(index): value
        for index, value in enumerate(metadata.facets.times)
        if value.meaning.kind in {"day_offset", "calendar_period"}
    }


def create_draft(
    artifacts: ArtifactStore,
    target: MemoryClaim,
    metadata: ReplacementMetadata,
    inputs: dict,
    now: str,
) -> CorrectionPreview:
    sources = {
        p.source_id: artifacts.get_source(p.source_id) for p in target.provenance
    }
    cited = {sid for p in target.provenance for sid in p.segment_ids}
    active = [source for source in sources.values() if source.status == "active"]
    anchors = source_time_anchors(active)
    source_for_segment = {
        s.segment_id: source.source_id for source in active for s in source.segments
    }
    references = {}
    for index, time in enumerate(target.facets.get("temporal", []), 1):
        sid = time["anchor_segment_id"]
        if sid is not None and sid in anchors:
            references[f"T{index:03d}"] = {
                "label": f"Stored reference for {time['target']} ({time['expression']})",
                "anchor": time["anchor"],
                "segment_id": sid,
                "source_id": source_for_segment[sid],
            }
    for index, (sid, anchor) in enumerate(anchors.items(), 1):
        if sid in cited:
            source = sources[source_for_segment[sid]]
            segment = next(s for s in source.segments if s.segment_id == sid)
            references[f"E{index:03d}"] = {
                "label": f"Message: {segment.content}",
                "anchor": anchor,
                "segment_id": sid,
                "source_id": source.source_id,
            }
    references["submission"] = {
        "label": "This correction's submission date",
        "anchor": now,
        "segment_id": "replacement",
        "source_id": None,
    }
    references["unresolved"] = {
        "label": "Leave the reference date unresolved",
        "anchor": None,
        "segment_id": None,
        "source_id": None,
    }
    draft = {
        "draft_id": f"correction-draft-{uuid4().hex}",
        "claim_id": target.claim_id,
        "inputs": inputs,
        "metadata": metadata.model_dump(),
        "created_at": now,
        "claim_fingerprint": fingerprint(target),
        "source_fingerprints": {
            key: fingerprint(source) for key, source in sources.items()
        },
        "references": references,
        "reference_order": list(references),
        "status": "pending",
    }
    artifacts.db.put("correction-drafts", draft["draft_id"], draft)
    return preview(draft)


def preview(draft: dict) -> CorrectionPreview:
    metadata = ReplacementMetadata.model_validate(draft["metadata"])
    times = []
    for key, value in relative_times(metadata).items():
        options = []
        for ref_id in draft["reference_order"]:
            ref = draft["references"][ref_id]
            resolved = resolve_annotation(value, ref["anchor"], ref["segment_id"])
            options.append(
                {
                    "reference_id": ref_id,
                    "label": ref["label"],
                    "anchor": ref["anchor"],
                    "start": resolved.start,
                    "end": resolved.end,
                    "status": resolved.status,
                    "resolution_error": resolved.resolution_error,
                    "source_id": ref["source_id"],
                    "segment_id": ref["segment_id"],
                }
            )
        times.append(
            {
                "time_id": key,
                "expression": value.expression,
                "target": value.target,
                "role": value.role,
                "options": options,
            }
        )
    return CorrectionPreview(
        draft["draft_id"], draft["claim_id"], draft["inputs"]["text"], times
    )


def load_review(
    artifacts: ArtifactStore,
    target: MemoryClaim,
    draft_id: str,
    inputs: dict,
    choices: dict[str, str] | None,
) -> dict:
    draft = artifacts.db.get("correction-drafts", draft_id)
    if draft["status"] != "pending" or draft["claim_id"] != target.claim_id:
        raise ValueError("This correction review is no longer applicable")
    if draft["inputs"] != inputs:
        raise ValueError("The replacement changed; prepare a new date preview")
    if not review_is_current(artifacts, draft):
        raise ValueError(
            "Memory changed while dates were being reviewed; prepare a new preview"
        )
    required = relative_times(ReplacementMetadata.model_validate(draft["metadata"]))
    if choices is None or set(choices) != set(required):
        raise ValueError("Choose a reference for every relative time in the preview")
    if any(value not in draft["references"] for value in choices.values()):
        raise ValueError("A selected time reference is not part of this preview")
    return draft


def resolved_correction_facets(
    metadata: ReplacementMetadata,
    segment_id: str,
    draft: dict | None,
    choices: dict[str, str] | None,
) -> tuple[dict, dict[str, set[str]]]:
    times, context = [], {}
    for index, value in enumerate(metadata.facets.times):
        annotation = value.model_copy(update={"evidence_segment_id": segment_id})
        anchor = anchor_id = reference_reason = None
        if value.meaning.kind in {"day_offset", "calendar_period"}:
            if draft is None or choices is None:
                raise ValueError("Relative correction dates require explicit review")
            ref = draft["references"][choices[str(index)]]
            anchor, anchor_id = ref["anchor"], ref["segment_id"]
            if anchor_id == "replacement":
                anchor_id = segment_id
            elif anchor_id is not None:
                context.setdefault(ref["source_id"], set()).add(anchor_id)
            reference_reason = "User selected: " + ref["label"]
            # Diagnostics retain the full source text in the preview, not in this bounded reason.
            if choices[str(index)].startswith("E"):
                reference_reason = "User selected the cited message's date"
            elif choices[str(index)].startswith("T"):
                reference_reason = "User selected the stored reference date"
        times.append(
            resolve_annotation(
                annotation, anchor, anchor_id, reference_reason=reference_reason
            ).model_dump()
        )
    return {
        "temporal": times,
        "inference_basis": metadata.facets.inference_basis,
    }, context
