"""Prompt-facing formatting for consolidation decisions."""

from __future__ import annotations

from typing import Iterable
import json

from mycelium.artifacts import (
    ArtifactStore,
    EntityRecord,
    EntityResolutionDecision,
    SourceDocument,
)
from mycelium.consolidation_models import ClaimEvidence
from mycelium.ontology import entity_type_definition


class RoutingFormatter:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    @staticmethod
    def entity_catalog(
        entities: Iterable[EntityRecord], *, include_sections: bool
    ) -> str:
        active = sorted(
            (e for e in entities if e.status == "active"), key=lambda e: e.entity_id
        )
        payload = {
            "pages": {
                e.entity_id: {
                    "subject": e.title,
                    "entity_type": e.entity_type,
                    "aliases": e.aliases,
                    "page_state": e.materialization_state,
                }
                for e in active
            }
        }
        if include_sections:
            payload["section_definitions"] = {
                kind: {
                    s.key: s.description for s in entity_type_definition(kind).sections
                }
                for kind in sorted({e.entity_type for e in active})
            }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def entity_planning_catalog(
        self, entities: Iterable[EntityRecord], staged_decisions: Iterable[EntityResolutionDecision] = (),
    ) -> str:
        decisions = {d.decision_id: d for d in self.artifacts.list_entity_resolution_decisions()}
        decisions.update({d.decision_id: d for d in staged_decisions})
        lines = ["Existing canonical entities and grounded page facts:"]
        found = False
        for entity in sorted(entities, key=lambda item: item.entity_id):
            if entity.status != "active":
                continue
            found = True
            aliases = ", ".join(entity.aliases) or "none"
            lines.append(
                f"- id={entity.entity_id}; type={entity.entity_type}; "
                f"title={entity.title!r}; aliases={aliases}; "
                f"page_state={entity.materialization_state}"
            )
            accepted = sorted(
                (d for d in decisions.values() if d.entity_id == entity.entity_id and d.review_state == "accepted"),
                key=lambda d: (d.created_at, d.decision_id),
            )
            # Bound presentation while retaining founding evidence and recent resolutions.
            selected = {d.decision_id: d for d in [*accepted[:1], *accepted[-3:]]}
            grounding = []
            for decision in selected.values():
                claims = []
                for claim_id in decision.identity_evidence_claim_ids:
                    claim = self.artifacts.get_claim(claim_id)
                    if claim.status != "active" or any(self.artifacts.get_source(p.source_id).status != "active" for p in claim.provenance):
                        continue
                    claims.append({"claim_id": claim.claim_id, "text": claim.text,
                                   "provenance": [{"source_id": p.source_id, "segment_ids": p.segment_ids}
                                                  for p in claim.provenance]})
                # Model explanations contain call-local aliases; retain them in the
                # audit record, not in evidence for a later alias namespace.
                grounding.append({"decision_id": decision.decision_id,
                                  "claims": claims,
                                  **({"reviewer_note": decision.reviewer_note} if decision.reviewer_note else {})})
            if grounding:
                lines.append("  identity_grounding=" + json.dumps(grounding, ensure_ascii=False))
            facts = self.artifacts.list_consolidated_facts(
                owner_entity_id=entity.entity_id,
            )
            lines.extend(f"  - fact: {fact.text}" for fact in facts[:6])
        if not found:
            lines.append("- none yet")
        return "\n".join(lines)

    def identity_review_catalog(
        self, aliases: dict[str, ClaimEvidence]
    ) -> str:
        """Expose prior user adjudications that overlap the exact claim cohort."""
        claim_ids = {item.claim.claim_id for item in aliases.values()}
        lines = []
        for decision in self.artifacts.list_entity_resolution_decisions():
            if decision.review_state not in {"accepted", "rejected"}:
                continue
            if decision.reviewed_at is None:
                continue
            overlap = claim_ids.intersection(decision.supporting_claim_ids)
            if not overlap:
                continue
            lines.append(
                f"- review_state={decision.review_state}; "
                f"entity={decision.entity_id or 'none'}; "
                f"type={decision.proposed_entity_type}; "
                f"title={decision.proposed_title!r}; "
                f"scope={decision.proposed_scope or 'unspecified'}; "
                f"parent={decision.proposed_parent_entity_id or 'none'}; "
                f"page_state={decision.proposed_page_state or 'unspecified'}; "
                f"claim_ids={','.join(sorted(overlap))}; "
                f"reviewer_note={decision.reviewer_note or 'none'}"
            )
        return "\n".join(lines) or "none"

    def format_pending_identity_proposals(
        self, decisions: Iterable[EntityResolutionDecision]
    ) -> str:
        """Render unresolved proposals as review candidates, not canonical entities."""
        blocks = []
        for decision in decisions:
            claims = []
            for claim_id in decision.identity_evidence_claim_ids:
                try:
                    claim = self.artifacts.get_claim(claim_id)
                except FileNotFoundError:
                    continue
                claims.append(f"{claim.claim_id}: {claim.text}")
            reviewer_note = f"reviewer_note={decision.reviewer_note}; " if decision.reviewer_note else ""
            blocks.append(
                f"[{decision.decision_id}] type={decision.proposed_entity_type}; "
                f"title={decision.proposed_title!r}; "
                f"candidate_entity_ids={','.join(decision.candidate_entity_ids) or 'none'}; "
                f"{reviewer_note}"
                f"scope={decision.proposed_scope or 'unspecified'}; "
                f"identity_defining_evidence={' | '.join(claims) or 'none'}"
            )
        return "\n".join(blocks) or "none"

    def format_evidence(
        self,
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple[SourceDocument, str, str | None]],
    ) -> str:
        claims, sources = {}, {}
        for alias, item in aliases.items():
            claim = item.claim
            citations = []
            for provenance in claim.provenance:
                citations.extend(
                    {"source_id": provenance.source_id, "segment_id": sid}
                    for sid in provenance.segment_ids
                )
                try:
                    source = (
                        item.source
                        if provenance.source_id == item.source.source_id
                        else self.artifacts.get_source(provenance.source_id)
                    )
                except FileNotFoundError:
                    continue
                entry = sources.setdefault(
                    source.source_id,
                    {
                        "source_type": source.source_type,
                        "occurred_at": source.occurred_at,
                        "segments": {},
                    },
                )
                if source.metadata.get("title"):
                    entry["title"] = source.metadata["title"]
                by_id = {s.segment_id: s for s in source.segments}
                for sid in provenance.segment_ids:
                    if sid in by_id:
                        seg = by_id[sid]
                        entry["segments"][sid] = {
                            "speaker": seg.speaker,
                            "role": seg.role,
                            "timestamp": seg.timestamp,
                            "text": seg.content,
                        }
            claims[alias] = {
                "text": claim.text,
                "claim_id": claim.claim_id,
                "claim_type": claim.claim_type,
                "about": claim.about,
                "temporal_status": claim.temporal_status,
                "facets": claim.facets,
                "evidence_modality": claim.evidence_modality,
                "citations": citations,
                "identity_references": [
                    {"role": r.role, "entity_id": r.entity_id, "origin": r.origin}
                    for r in self.artifacts.list_entity_references(
                        claim_id=claim.claim_id, status="active"
                    )
                ],
            }
        return json.dumps(
            {
                "claims": claims,
                "participants": {
                    a: {"name": name, "role": role, "source_id": s.source_id}
                    for a, (s, name, role) in participants.items()
                },
                "sources": sources,
            },
            ensure_ascii=False,
            indent=2,
        )
