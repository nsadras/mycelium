"""Prompt-facing formatting for consolidation decisions."""

from __future__ import annotations

from typing import Iterable

from mycelium.artifacts import (
    ArtifactStore,
    EntityRecord,
    EntityResolutionDecision,
    SourceDocument,
)
from mycelium.consolidation_models import ClaimEvidence
from mycelium.ontology import (
    entity_type_prompt_catalog,
    section_prompt_catalog,
)


class RoutingFormatter:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.artifacts = artifacts

    @staticmethod
    def entity_catalog(
        entities: Iterable[EntityRecord], *, include_sections: bool
    ) -> str:
        if include_sections:
            lines = ["Typed page ontology:", section_prompt_catalog()]
        else:
            lines = [
                "Typed entity ontology:",
                entity_type_prompt_catalog(discoverable_only=True),
            ]
        lines.extend(["", "Existing canonical entities:"])
        found = False
        for entity in sorted(entities, key=lambda item: item.entity_id):
            if entity.status != "active":
                continue
            found = True
            aliases = ", ".join(entity.aliases) or "none"
            lines.append(
                f"- id={entity.entity_id}; type={entity.entity_type}; title={entity.title!r}; "
                f"aliases={aliases}; page_state={entity.materialization_state}"
            )
        if not found:
            lines.append("- none yet")
        return "\n".join(lines)

    def entity_planning_catalog(self, entities: Iterable[EntityRecord]) -> str:
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
            facts = self.artifacts.list_consolidated_facts(
                owner_entity_id=entity.entity_id,
            )
            lines.extend(f"  - fact: {fact.text}" for fact in facts[:6])
        if not found:
            lines.append("- none yet")
        return "\n".join(lines)

    @staticmethod
    def format_subject_candidates(
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple[SourceDocument, str, str | None]],
    ) -> str:
        """Expose extraction-declared referents without making a new decision."""
        lines = [
            f"- {alias}: name={str(mention.get('entity'))!r}; "
            f"role={str(mention.get('role') or 'unspecified')}"
            for alias, item in aliases.items()
            for mention in item.claim.about
            if mention.get("entity")
        ]
        lines.extend(
            f"- {alias}: name={name!r}; role=source_participant"
            for alias, (_, name, _) in participants.items()
        )
        return "\n".join(lines) or "- none"

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
            blocks.append(
                f"[{decision.decision_id}] type={decision.proposed_entity_type}; "
                f"title={decision.proposed_title!r}; "
                f"scope={decision.proposed_scope or 'unspecified'}; "
                f"identity_defining_evidence={' | '.join(claims) or 'none'}"
            )
        return "\n".join(blocks) or "none"

    def format_evidence(
        self,
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple[SourceDocument, str, str | None]],
    ) -> str:
        blocks = []
        source_blocks = {}
        for alias, item in aliases.items():
            claim = item.claim
            cited_segment_ids = {
                segment_id
                for provenance in claim.provenance
                if provenance.source_id == item.source.source_id
                for segment_id in provenance.segment_ids
            }
            references = []
            for segment in item.source.segments:
                if segment.segment_id not in cited_segment_ids:
                    continue
                key = (item.source.source_id, segment.segment_id)
                label = f"source_id={key[0]}; segment_id={key[1]}"
                text = (f"[{segment.segment_id}] role={segment.role or 'unknown'}; "
                        f"{f'{segment.speaker}: ' if segment.speaker else ''}{segment.content}")
                source_blocks[key] = f"[{label}]\n{text}"
                references.append(label)
            source_evidence = " | ".join(references) or "none"
            source_title = str(item.source.metadata.get("title") or "").strip()
            entities = (
                ", ".join(
                    f"{str(value.get('entity'))!r}[role={str(value.get('role') or 'unspecified')}]"
                    for value in claim.about
                    if value.get("entity")
                )
                or "unknown"
            )
            stable_references = (
                ", ".join(
                    f"{reference.role}:{reference.entity_id or 'unresolved'}"
                    for reference in self.artifacts.list_entity_references(
                        claim_id=claim.claim_id, status="active"
                    )
                )
                or "none"
            )
            facets = "; ".join(
                f"{key}={value}"
                for key, value in sorted(claim.facets.items())
                if value not in (None, "", [], {})
            )
            blocks.append(
                f"[EVIDENCE {alias}]\nclaim_type={claim.claim_type}; "
                f"extracted_entity_mentions={entities}; stable_entity_references={stable_references}; "
                f"temporal_status={claim.temporal_status}; source_id={item.source.source_id}; "
                f"source_type={item.source.source_type}; occurred_at={item.source.occurred_at or 'unknown'}; "
                f"participants={','.join(item.source.participants) or 'none'}; "
                f"source_title={source_title or 'none'}; "
                f"evidence_modality={claim.evidence_modality}\nclaim={claim.text}\n"
                f"cited_source_evidence={source_evidence}\n"
                f"qualifiers={facets or 'none'}"
            )
        if participants:
            blocks.append("[SOURCE-DECLARED PARTICIPANTS]")
            blocks.extend(
                f"[{alias}] name={name!r}; source_id={source.source_id}; "
                f"speaker_role={role or 'participant'}; "
                f"occurred_at={source.occurred_at or 'unknown'}"
                for alias, (source, name, role) in participants.items()
            )
        if source_blocks:
            blocks.append("[CITED SOURCE SEGMENTS: shared evidence, included once per exact source/segment ID]")
            blocks.extend(source_blocks.values())
        return "\n\n".join(blocks)
