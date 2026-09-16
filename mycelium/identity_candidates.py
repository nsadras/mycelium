"""Source-grounded identity records for a bounded semantic candidate index."""

import json


def identity_records(artifacts, entities, staged_decisions=()):
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
                claim = artifacts.get_claim(claim_id)
                if claim.status != "active":
                    continue
                sources = [artifacts.get_source(p.source_id) for p in claim.provenance]
                if any(source.status != "active" for source in sources):
                    continue
                if not claim.provenance or any(
                    not p.segment_ids for p in claim.provenance
                ):
                    raise ValueError(
                        f"Identity evidence {claim_id} has no source citations"
                    )
                for provenance, source in zip(claim.provenance, sources):
                    if not set(provenance.segment_ids) <= {
                        s.segment_id for s in source.segments
                    }:
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
