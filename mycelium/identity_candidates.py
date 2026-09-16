"""Source-grounded identity records for a bounded semantic candidate index."""

import json


def identity_records(artifacts, entities, staged_decisions=()):
    # Preparation is synchronous under the store's writer lease. Reuse exact
    # records only within this call; the next build sees every edit/retraction.
    claims, sources, segment_ids = {}, {}, {}
    decisions = {d.decision_id: d for d in artifacts.list_entity_resolution_decisions()}
    decisions.update({d.decision_id: d for d in staged_decisions})
    by_entity = {}
    for decision in decisions.values():
        if decision.review_state in {"accepted", "review_required"}:
            by_entity.setdefault(decision.entity_id, []).append(decision)
    records = {}
    for entity in entities:
        if entity.status != "active":
            continue
        accepted = sorted(
            by_entity.get(entity.entity_id, []),
            key=lambda d: (d.created_at, d.decision_id),
        )
        selected = {d.decision_id: d for d in [*accepted[:1], *accepted[-3:]]}
        evidence = {}
        for decision in selected.values():
            for claim_id in decision.identity_evidence_claim_ids:
                if claim_id not in claims:
                    claims[claim_id] = artifacts.get_claim(claim_id)
                claim = claims[claim_id]
                if claim.status != "active":
                    continue
                for provenance in claim.provenance:
                    sid = provenance.source_id
                    if sid not in sources:
                        sources[sid] = artifacts.get_source(sid)
                        segment_ids[sid] = {s.segment_id for s in sources[sid].segments}
                if any(
                    sources[p.source_id].status != "active" for p in claim.provenance
                ):
                    continue
                if not claim.provenance or any(
                    not p.segment_ids for p in claim.provenance
                ):
                    raise ValueError(
                        f"Identity evidence {claim_id} has no source citations"
                    )
                for provenance in claim.provenance:
                    if (
                        not set(provenance.segment_ids)
                        <= segment_ids[provenance.source_id]
                    ):
                        raise ValueError(
                            f"Identity evidence {claim_id} cites missing source segments"
                        )
                evidence[claim_id] = {
                    "claim_id": claim_id,
                    "text": claim.text,
                    "citations": [
                        {"source_id": p.source_id, "segment_ids": p.segment_ids}
                        for p in claim.provenance
                    ],
                }
        records[entity.entity_id] = {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
            "title": entity.title,
            "aliases": entity.aliases,
            "page_state": entity.materialization_state,
            "identity_evidence": list(evidence.values()),
            "reviewer_notes": [
                d.reviewer_note for d in selected.values() if d.reviewer_note
            ],
            "pending_reviews": [
                {
                    "decision_id": d.decision_id,
                    "candidate_entity_ids": d.candidate_entity_ids,
                }
                for d in accepted
                if d.review_state == "review_required"
            ],
        }
    return records


def identity_documents(records):
    # Document ranking sees identity metadata and grounded statements, not
    # ownership-derived presentation summaries or opaque record IDs.
    return {
        eid: json.dumps(
            {
                "type": record["entity_type"],
                "title": record["title"],
                "aliases": record["aliases"],
                "evidence": [item["text"] for item in record["identity_evidence"]],
            },
            ensure_ascii=False,
        )
        for eid, record in records.items()
    }
