"""Prompt-facing formatting for consolidation decisions."""

from __future__ import annotations

from typing import Iterable

from mycelium.artifacts import ArtifactStore, EntityRecord, SourceDocument
from mycelium.consolidation_models import ClaimEvidence
from mycelium.ontology import entity_type_prompt_catalog, section_prompt_catalog


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
    def format_resolved_entity_plan(
        nodes: dict[str, dict],
        decisions: dict[str, dict],
        candidates: dict[str, EntityRecord],
        entities: dict[str, EntityRecord],
        participants: dict[str, dict],
    ) -> str:
        lines = ["Subjects:"]
        for node_id, node in nodes.items():
            decision = decisions[node_id]
            entity = candidates.get(node_id) or entities.get(str(decision["entity_id"]))
            parent_ref = str(decision["parent_entity"])
            parent = candidates.get(parent_ref) or entities.get(parent_ref)
            scope = str(decision["scope"])
            page_state = (
                scope if scope in {"materialized", "provisional"} else "no_page"
            )
            lines.append(
                f"- {node_id}: type={node['entity_type']}; "
                f"evidence_title={node['title']!r}; "
                f"stable_id={entity.entity_id if entity else 'no_page'}; "
                f"stable_title={entity.title if entity else 'none'}; "
                f"page_state={page_state}; "
                f"scope={scope}; "
                f"parent={parent.entity_id if parent else parent_ref or 'none'}; "
                f"evidence={','.join(node['supporting_evidence'])}"
            )
        lines.append("Participants:")
        lines.extend(
            f"- {alias}: entity={decision['entity']}"
            for alias, decision in participants.items()
        )
        if not participants:
            lines.append("- none")
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

    @staticmethod
    def format_subject_graph(
        nodes: dict[str, dict],
        edges: list[dict],
    ) -> str:
        """Render the fixed census without adding semantic decisions."""
        lines = ["Nodes:"]
        for node_id, node in nodes.items():
            details = [
                f"type={node['entity_type']}",
                f"type_adjudication={node['type_adjudication']}",
                f"type_reason={node['type_reason']!r}",
                f"title={node['title']!r}",
                f"evidence={','.join(node['supporting_evidence'])}",
                f"participant_evidence={','.join(node['participant_evidence']) or 'none'}",
            ]
            lines.append(f"- {node_id}: {'; '.join(details)}")
        lines.append("Edges:")
        lines.extend(
            f"- {edge['source_node']} -[{edge['relation']}]-> "
            f"{edge['target_node']}; evidence="
            f"{','.join(edge['supporting_evidence'])}"
            for edge in edges
        )
        if not edges:
            lines.append("- none")
        return "\n".join(lines)

    @staticmethod
    def format_maturity_decisions(decisions: dict[str, dict]) -> str:
        lines = []
        for node_id, decision in decisions.items():
            basis = decision.get("basis") or {}
            details = [
                f"admission={decision['admission']}",
                f"reason={decision['reason']!r}",
            ]
            if basis:
                details.extend(
                    f"{key}={value!r}" for key, value in basis.items()
                )
            lines.append(f"- {node_id}: {'; '.join(details)}")
        return "\n".join(lines) or "none"

    def format_evidence(
        self,
        aliases: dict[str, ClaimEvidence],
        participants: dict[str, tuple[SourceDocument, str, str | None]],
    ) -> str:
        blocks = []
        for alias, item in aliases.items():
            claim = item.claim
            cited_segment_ids = {
                segment_id
                for provenance in claim.provenance
                if provenance.source_id == item.source.source_id
                for segment_id in provenance.segment_ids
            }
            source_evidence = (
                "\n".join(
                    f"[{segment.segment_id}] "
                    f"{f'{segment.speaker}: ' if segment.speaker else ''}{segment.content}"
                    for segment in item.source.segments
                    if segment.segment_id in cited_segment_ids
                )
                or "none"
            )
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
        return "\n\n".join(blocks)
