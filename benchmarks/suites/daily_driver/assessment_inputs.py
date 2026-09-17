"""Exact evidence scoping for benchmark-owned semantic assessments."""

from collections import defaultdict
import hashlib
import json
from datetime import date, datetime


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported assessment value: {type(value).__name__}")


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=json_default,
        ).encode()
    ).hexdigest()


def evidence_key(source_id, segment_id):
    return json.dumps(
        [source_id, segment_id], ensure_ascii=False, separators=(",", ":")
    )


def assessment_inputs(fixture, snapshot):
    """Prepare source-grounded inputs without lexical matching or product writes.

    Each target considers every generated claim that cites one of its declared
    evidence segments. Unmatched generated claims still receive a source audit.
    Lifecycle/page states are excluded so unchanged meaning can reuse judgments.
    """
    sources, segments, native_segments = {}, {}, {}
    label_members, label_sources, native_labels = defaultdict(set), {}, {}
    for source in snapshot.get("sources", []):
        sid = str(source["source_id"])
        if sid in sources:
            raise ValueError(f"Duplicate snapshot source ID: {sid}")
        sources[sid] = source
        for segment in source["segments"]:
            native_id = str(segment["segment_id"])
            key = (sid, native_id)
            eid = evidence_key(*key)
            label = segment.get("metadata", {}).get("fixture_segment_id")
            if key in native_segments:
                raise ValueError(f"Duplicate snapshot evidence ID: {key}")
            if label:
                label = str(label)
                if label_sources.get(label, sid) != sid:
                    raise ValueError(
                        f"Fixture label belongs to multiple sources: {label}"
                    )
                label_sources[label] = sid
                label_members[label].add(eid)
                native_labels[eid] = label
            native_segments[key] = eid
            segments[eid] = {
                "fixture_evidence_id": label,
                "source_id": sid,
                "segment_id": native_id,
                "source_type": source["source_type"],
                "occurred_at": source.get("occurred_at"),
                "timestamp": segment.get("timestamp"),
                "speaker": segment.get("speaker"),
                "role": segment.get("role"),
                "text": segment["content"],
            }
    generated = {}
    for claim in snapshot.get("claims", []):
        cid = str(claim["claim_id"])
        if cid in generated:
            raise ValueError(f"Duplicate generated claim ID: {cid}")
        evidence = set()
        for provenance in claim.get("provenance", []):
            sid = str(provenance["source_id"])
            for native_id in provenance["segment_ids"]:
                key = (sid, str(native_id))
                if key not in native_segments:
                    raise ValueError(
                        f"Claim {cid} cites missing source evidence: {key}"
                    )
                evidence.add(native_segments[key])
        if not evidence:
            raise ValueError(f"Claim {cid} has no inspectable source evidence")
        declared = set(map(str, claim.get("fixture_evidence", [])))
        if declared != {native_labels[eid] for eid in evidence if eid in native_labels}:
            raise ValueError(f"Claim {cid} has inconsistent fixture evidence labels")
        generated[cid] = {"text": claim["text"], "evidence_ids": sorted(evidence)}
    references = {}
    groups = defaultdict(list)
    unmatched_references = []
    for reference in fixture["gold_claims"].get("claims", []):
        rid = str(reference["id"])
        if rid in references:
            raise ValueError(f"Duplicate reference claim ID: {rid}")
        labels = set(map(str, reference.get("evidence", [])))
        evidence = sorted(
            {eid for label in labels for eid in label_members.get(label, ())}
        )
        candidates = sorted(
            cid
            for cid, row in generated.items()
            if set(evidence) & set(row["evidence_ids"])
        )
        references[rid] = {
            "text": reference["text"],
            "evidence_ids": evidence,
            "unavailable_evidence_ids": sorted(labels - label_members.keys()),
            "candidate_claim_ids": candidates,
        }
        if not candidates:
            unmatched_references.append(rid)
            continue
        # Group exact candidate domains. This never selects by words or metadata.
        groups[tuple(candidates)].append(rid)
    configured = fixture.get("scenario", {}).get("user", {})
    bindings = (
        {str(configured["speaker_label"]): str(configured["name"])}
        if configured
        else {}
    )
    requests, covered_claims = [], set()

    def request(reference_ids, claim_ids):
        chosen_references = {
            rid: {
                **references[rid],
            }
            for rid in sorted(reference_ids)
        }
        chosen_claims = {cid: generated[cid] for cid in sorted(claim_ids)}
        cited = {
            label
            for row in [*chosen_references.values(), *chosen_claims.values()]
            for label in row["evidence_ids"]
        }
        source_ids = {segments[label]["source_id"] for label in cited}
        payload = {
            "source_participants": bindings,
            "source_evidence": {
                label: row
                for label, row in sorted(segments.items())
                if row["source_id"] in source_ids
            },
            "references": chosen_references,
            "generated_claims": chosen_claims,
        }
        return {"input_digest": digest(payload), "payload": payload}

    for candidates, rids in sorted(groups.items()):
        # Bound decision count without dropping a target or candidate. Coverage
        # fragments for a reference are combined by exact IDs by the assessor.
        for offset in range(0, len(rids), 4):
            chunk = rids[offset : offset + 4]
            for cstart in range(0, len(candidates), 8):
                chosen = candidates[cstart : cstart + 8]
                item = request(chunk, chosen)
                item["payload"]["references"] = {
                    rid: {**row, "candidate_claim_ids": list(chosen)}
                    for rid, row in item["payload"]["references"].items()
                }
                item["input_digest"] = digest(item["payload"])
                requests.append(item)
            covered_claims.update(candidates)
    # Audit extra claims, including statements from source-only segments.
    remainder = sorted(generated.keys() - covered_claims)
    for start in range(0, len(remainder), 8):
        requests.append(request([], remainder[start : start + 8]))
    return {
        "input_digest": digest(
            {
                "references": references,
                "generated_claims": generated,
                "sources": segments,
                "source_participants": bindings,
            }
        ),
        "requests": requests,
        "unmatched_reference_ids": unmatched_references,
        "unavailable_reference_evidence": {
            rid: row["unavailable_evidence_ids"]
            for rid, row in references.items()
            if row["unavailable_evidence_ids"]
        },
        "reference_ids": sorted(references),
        "generated_claim_ids": sorted(generated),
    }
