"""Participant and stable endpoint artifacts produced during consolidation."""

from __future__ import annotations

import uuid
from datetime import datetime

from mycelium.artifacts import (
    ClaimEntityReference,
    EntityEncounter,
    EntityRecord,
    EntityResolutionDecision,
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
    def participant_encounters(
        occurrences: dict[str, tuple[SourceDocument, str, str | None]],
        resolutions: dict[str, dict],
        entities: dict[str, EntityRecord],
        candidates: dict[str, EntityRecord],
    ) -> list[EntityEncounter]:
        created_at = datetime.now().astimezone().isoformat()
        encounters: dict[str, EntityEncounter] = {}
        for alias, (source, _, _) in occurrences.items():
            resolution = resolutions[alias]
            entity = candidates.get(resolution["entity"]) or entities.get(
                resolution["entity"]
            )
            if entity is None or entity.entity_type != "person":
                continue
            title = str(source.metadata.get("title") or "").strip() or None
            encounter_id = f"encounter-{entity.entity_id}-{source.source_id}"
            encounters[encounter_id] = EntityEncounter(
                encounter_id=encounter_id,
                entity_id=entity.entity_id,
                source_id=source.source_id,
                raw_log_entry_id=source.raw_log_entry_id,
                occurred_at=source.occurred_at,
                title=title,
                created_at=created_at,
            )
        return sorted(encounters.values(), key=lambda item: item.encounter_id)

    @staticmethod
    def participant_decisions(
        occurrences: dict[str, tuple[SourceDocument, str, str | None]],
        resolutions: dict[str, dict],
        entities: dict[str, EntityRecord],
        candidates: dict[str, EntityRecord],
        dream_run_id: str,
        created_at: str,
    ) -> list[EntityResolutionDecision]:
        decisions = []
        for alias, (source, surface, _) in occurrences.items():
            resolution = resolutions[alias]
            entity = candidates.get(resolution["entity"]) or entities.get(
                resolution["entity"]
            )
            confidence = float(resolution["confidence"])
            if entity is None:
                decisions.append(
                    EntityResolutionDecision(
                        decision_id=f"identity-{uuid.uuid4().hex[:12]}",
                        decision_type="participant_resolution",
                        entity_id=None,
                        proposed_entity_type="person",
                        proposed_title=surface,
                        source_ids=[source.source_id],
                        supporting_claim_ids=[],
                        supporting_segment_ids=[
                            segment.segment_id
                            for segment in source.segments
                            if str(segment.speaker or "").strip() == surface
                        ],
                        confidence=confidence,
                        reason=(
                            "Review required because the model referenced an undeclared "
                            f"participant entity {resolution['entity']!r}. "
                            f"{resolution['reason']}"
                        ),
                        review_state="review_required",
                        dream_run_id=dream_run_id,
                        created_at=created_at,
                        participant_surface=surface,
                    )
                )
                continue
            decisions.append(
                EntityResolutionDecision(
                    decision_id=f"identity-{uuid.uuid4().hex[:12]}",
                    decision_type="participant_resolution",
                    entity_id=entity.entity_id,
                    proposed_entity_type=entity.entity_type,
                    proposed_title=entity.title,
                    source_ids=[source.source_id],
                    supporting_claim_ids=[],
                    supporting_segment_ids=[
                        segment.segment_id
                        for segment in source.segments
                        if str(segment.speaker or "").strip() == surface
                    ],
                    confidence=confidence,
                    reason=str(resolution["reason"]),
                    review_state=(
                        "accepted" if confidence >= 0.7 else "review_required"
                    ),
                    dream_run_id=dream_run_id,
                    created_at=created_at,
                    participant_surface=surface,
                )
            )
        return decisions

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
