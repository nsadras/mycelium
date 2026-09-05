"""Participant and stable endpoint artifacts produced during consolidation."""

from __future__ import annotations

import uuid

from mycelium.artifacts import (
    ClaimEntityReference,
    EntityRecord,
    SourceDocument,
)
from mycelium.consolidation_models import ClaimEvidence, ClaimRoute


class ResolutionArtifacts:
    @staticmethod
    def participants_for_evidence(
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple[SourceDocument, str, str | None]],
    ) -> dict[str, tuple[SourceDocument, str, str | None]]:
        source_ids = {item.source.source_id for item in aliases.values()}
        return {
            alias: occurrence
            for alias, occurrence in participants.items()
            if occurrence[0].source_id in source_ids
        }

    @staticmethod
    def participant_occurrences(
        evidence: list[ClaimEvidence],
        *,
        source_ids: set[str] | None = None,
    ) -> dict[str, tuple[SourceDocument, str, str | None]]:
        """Expose source-declared participant occurrences to the scope contract."""
        sources = {
            item.source.source_id: item.source
            for item in evidence
            if (source_ids is None or item.source.source_id in source_ids)
            if item.source.source_type
            in {"meeting_transcript", "multi_party_conversation"}
        }
        occurrences: list[tuple[SourceDocument, str, str | None]] = []
        for source in sources.values():
            speakers = dict.fromkeys(
                (
                    str(segment.speaker).strip(),
                    str(segment.role).strip().lower() if segment.role else None,
                )
                for segment in source.segments
                if str(segment.speaker or "").strip()
            )
            occurrences.extend((source, name, role) for name, role in speakers)
        return {
            f"P{index:03d}": occurrence
            for index, occurrence in enumerate(occurrences, start=1)
        }

    @staticmethod
    def claim_entity_references(
        aliases: dict[str, ClaimEvidence],
        routes: list[ClaimRoute],
        entities: dict[str, EntityRecord],
        dream_run_id: str,
        created_at: str,
    ) -> list[ClaimEntityReference]:
        """Preserve extracted surfaces and add stable scope endpoints without string matching."""
        routes_by_claim = {route.claim_id: route for route in routes}
        references: list[ClaimEntityReference] = []
        for item in aliases.values():
            claim = item.claim
            for mention in claim.about:
                surface = " ".join(str(mention.get("entity") or "").split()).strip()
                if not surface:
                    continue
                extracted_role = str(mention.get("role") or "").strip().lower()
                if extracted_role in {"subject", "speaker", "owner", "actor"}:
                    role = "subject"
                elif extracted_role in {"object", "value", "target", "recipient"}:
                    role = "object"
                else:
                    role = "context"
                references.append(
                    ClaimEntityReference(
                        reference_id=f"ref-{uuid.uuid4().hex[:12]}",
                        claim_id=claim.claim_id,
                        role=role,
                        surface=surface,
                        entity_id=None,
                        confidence=claim.confidence,
                        reason="Surface mention preserved from structured claim extraction.",
                        origin="extraction",
                        dream_run_id=dream_run_id,
                        status="active",
                        created_at=created_at,
                    )
                )
            route = routes_by_claim.get(claim.claim_id)
            if route is None:
                continue
            if route.owner_entity_id:
                references.append(
                    ClaimEntityReference(
                        reference_id=f"ref-{uuid.uuid4().hex[:12]}",
                        claim_id=claim.claim_id,
                        role="canonical_owner",
                        surface=None,
                        entity_id=route.owner_entity_id,
                        confidence=route.confidence,
                        reason=route.reason,
                        origin="scope",
                        dream_run_id=dream_run_id,
                        status="active",
                        created_at=created_at,
                    )
                )
            stable_roles = [
                *(
                    [("subject", route.subject_entity_id)]
                    if route.subject_entity_id
                    else []
                ),
                *(("object", entity_id) for entity_id in route.object_entity_ids),
                *(("context", entity_id) for entity_id in route.contextual_entity_ids),
            ]
            explicitly_typed_ids = {entity_id for _, entity_id in stable_roles}
            stable_roles.extend(
                ("context", entity_id)
                for entity_id in route.linked_entity_ids
                if entity_id not in explicitly_typed_ids
            )
            for role, entity_id in stable_roles:
                entity = entities.get(entity_id)
                references.append(
                    ClaimEntityReference(
                        reference_id=f"ref-{uuid.uuid4().hex[:12]}",
                        claim_id=claim.claim_id,
                        role=role,
                        surface=entity.title if entity else None,
                        entity_id=entity_id,
                        confidence=route.confidence,
                        reason="Stable semantic endpoint from the scope decision.",
                        origin="scope",
                        dream_run_id=dream_run_id,
                        status="active",
                        created_at=created_at,
                    )
                )
        return references
