"""Coverage and cross-store integrity reports for memory artifacts."""

from typing import Any
from collections import Counter


def cited_source_segments(store, claim, *, source_cache=None):
    """Resolve every exact citation before using any of a claim's evidence.

    Source status is returned intact; callers choose whether retracted evidence
    can be shown as history. Missing citations must never look like complete
    evidence merely because another citation was valid.
    """
    cache = {} if source_cache is None else source_cache
    if not claim.provenance:
        raise ValueError(f"Claim {claim.claim_id} has no cited source segments")
    resolved = []
    for provenance in claim.provenance:
        if not provenance.segment_ids:
            raise ValueError(f"Claim {claim.claim_id} has an empty source citation")
        if provenance.source_id not in cache:
            try:
                source = store.get_source(provenance.source_id)
            except FileNotFoundError as exc:
                raise ValueError(
                    f"Claim {claim.claim_id} cites missing source {provenance.source_id}"
                ) from exc
            cache[provenance.source_id] = (
                source, {segment.segment_id: segment for segment in source.segments}
            )
        source, by_id = cache[provenance.source_id]
        missing = set(provenance.segment_ids) - by_id.keys()
        if missing:
            raise ValueError(
                f"Claim {claim.claim_id} cites missing segments in source "
                f"{source.source_id}: {sorted(missing)}"
            )
        resolved.append((provenance, source, [by_id[sid] for sid in provenance.segment_ids]))
    return resolved


def coverage_report(store) -> dict[str, Any]:
    sources = store.list_sources()
    claims = store.list_claims()
    episodes = store.list_episodes()
    active_ids = {claim.claim_id for claim in claims if claim.status == "active"}
    facts = store.list_consolidated_facts()
    memberships = Counter((cid for fact in facts for cid in fact.member_claim_ids))
    represented = active_ids & memberships.keys()
    held = active_ids & {
        cid
        for proposal in store.list_reconsolidation_proposals(status="pending")
        for cid in proposal.incoming_claim_ids
    }
    placed = {c.claim_id for c in claims if c.status == "active" and c.dream_disposition == "routed"}
    all_segments = {
        (source.source_id, segment.segment_id)
        for source in sources for segment in source.segments
    }
    claimed_segments = {
        (provenance.source_id, segment_id)
        for claim in claims
        for provenance in claim.provenance
        for segment_id in provenance.segment_ids
    }
    source_only_segments = {
        (episode.source_id, disposition.segment_id)
        for episode in episodes
        for disposition in episode.segment_dispositions
        if disposition.disposition == "source_only"
    }
    pending_segments = {
        (episode.source_id, segment_id)
        for episode in episodes
        for batch in episode.extraction_batches
        if batch.status != "complete"
        for segment_id in batch.segment_ids
    }
    unresolved = claimed_segments - all_segments
    accounted_segments = (claimed_segments | source_only_segments) & all_segments
    return {
        "sources": len(sources),
        "episodes": len(episodes),
        "claims": len(claims),
        "active_claims": sum((claim.status == "active" for claim in claims)),
        "consolidated_facts": len(facts),
        "represented_active_claims": len(represented),
        "active_claims_without_facts": sorted(active_ids - represented),
        "review_held_claim_ids": sorted(held),
        "placed_claims_without_facts": sorted(placed - held - represented),
        "repeated_fact_claim_ids": sorted(
            (cid for cid, count in memberships.items() if count > 1)
        ),
        "segments": len(all_segments),
        "claimed_segments": len(all_segments & claimed_segments),
        "segment_coverage": len(all_segments & claimed_segments) / len(all_segments)
        if all_segments
        else 1.0,
        "source_only_segments": len(all_segments & source_only_segments),
        "pending_extraction_segments": len(all_segments & pending_segments),
        "accounted_segments": len(accounted_segments),
        "accounted_coverage": len(accounted_segments) / len(all_segments)
        if all_segments
        else 1.0,
        "unassigned_segment_ids": sorted(sid for _, sid in all_segments - claimed_segments),
        "unaccounted_segment_ids": sorted(
            sid for _, sid in all_segments - claimed_segments - source_only_segments - pending_segments
        ),
        "pending_extraction_segment_ids": sorted(sid for _, sid in all_segments & pending_segments),
        "unplaced_claim_ids": sorted(active_ids - represented),
        "unresolved_provenance_ids": sorted({sid for _, sid in unresolved}),
        "unresolved_citations": [
            {"source_id": source_id, "segment_id": segment_id}
            for source_id, segment_id in sorted(unresolved)
        ],
        "failed_episode_ids": sorted(
            (ep.episode_id for ep in episodes if ep.extraction_status == "failed")
        ),
        "partial_episode_ids": sorted(
            (ep.episode_id for ep in episodes if ep.extraction_status == "partial")
        ),
    }


def artifact_integrity(mem) -> dict:
    sources = mem.artifacts.list_sources()
    episodes = mem.artifacts.list_episodes()
    claims = mem.artifacts.list_claims()
    wiki_pages = mem.wiki.list_all()
    pages = {page.slug for page in wiki_pages}
    logs = {entry.entry_id for entry in mem.log_store.list_entries(days=None)}
    source_by_id = {source.source_id: source for source in sources}
    episode_source_ids = {episode.source_id for episode in episodes}
    claim_by_id = {claim.claim_id: claim for claim in claims}
    proposals = mem.artifacts.list_reconsolidation_proposals()
    entities = {entity.entity_id: entity for entity in mem.artifacts.list_entities()}
    placements = {item.claim_id: item for item in mem.artifacts.list_placements()}
    facts = mem.artifacts.list_consolidated_facts()
    active_entity_ids = {
        entity_id for entity_id, entity in entities.items() if entity.status == "active"
    }
    active_scope_decisions = mem.artifacts.list_scope_decisions(status="active")
    active_references = mem.artifacts.list_entity_references(status="active")
    issues = {
        "sources_without_episode": sorted(
            (
                source_id
                for source_id in source_by_id
                if source_id not in episode_source_ids
            )
        ),
        "episodes_missing_source": sorted(
            (
                episode.episode_id
                for episode in episodes
                if episode.source_id not in source_by_id
            )
        ),
        "episodes_missing_claims": sorted(
            (
                f"{episode.episode_id}:{claim_id}"
                for episode in episodes
                for claim_id in episode.claim_ids
                if claim_id not in claim_by_id
            )
        ),
        "claims_missing_episode": sorted(
            (
                claim.claim_id
                for claim in claims
                if claim.provenance
                and (
                    not any(
                        (
                            provenance.source_id in episode_source_ids
                            for provenance in claim.provenance
                        )
                    )
                )
            )
        ),
        "claims_missing_provenance": sorted(
            (claim.claim_id for claim in claims
             if not claim.provenance or any(not p.segment_ids for p in claim.provenance))
        ),
        "claims_missing_source": sorted(
            (
                f"{claim.claim_id}:{provenance.source_id}"
                for claim in claims
                for provenance in claim.provenance
                if provenance.source_id not in source_by_id
            )
        ),
        "claims_missing_segments": sorted(
            (
                f"{claim.claim_id}:{segment_id}"
                for claim in claims
                for provenance in claim.provenance
                if provenance.source_id in source_by_id
                for segment_id in provenance.segment_ids
                if segment_id
                not in {
                    segment.segment_id
                    for segment in source_by_id[provenance.source_id].segments
                }
            )
        ),
        "placements_missing_claims": sorted(
            (claim_id for claim_id in placements if claim_id not in claim_by_id)
        ),
        "placements_missing_entities": sorted(
            (
                f"{placement.claim_id}:{placement.owner_entity_id}"
                for placement in placements.values()
                if placement.owner_entity_id
                and placement.owner_entity_id not in entities
            )
        ),
        "facts_missing_claims": sorted(
            (
                f"{fact.fact_id}:{claim_id}"
                for fact in facts
                for claim_id in fact.member_claim_ids
                if claim_id not in claim_by_id
            )
        ),
        "facts_missing_entities": sorted(
            (
                f"{fact.fact_id}:{fact.owner_entity_id}"
                for fact in facts
                if fact.owner_entity_id not in entities
            )
        ),
        "placements_with_inactive_entities": sorted(
            (
                f"{placement.claim_id}:{entity_id}"
                for placement in placements.values()
                if placement.status == "placed"
                for entity_id in [
                    placement.owner_entity_id,
                    *placement.linked_entity_ids,
                ]
                if entity_id and entity_id not in active_entity_ids
            )
        ),
        "facts_with_inactive_entities": sorted(
            (
                f"{fact.fact_id}:{entity_id}"
                for fact in facts
                for entity_id in [fact.owner_entity_id, *fact.linked_entity_ids]
                if entity_id not in active_entity_ids
            )
        ),
        "active_references_with_inactive_entities": sorted(
            (
                f"{reference.reference_id}:{reference.entity_id}"
                for reference in active_references
                if reference.entity_id and reference.entity_id not in active_entity_ids
            )
        ),
        "active_scope_with_inactive_entities": sorted(
            (
                f"{decision.decision_id}:{entity_id}"
                for decision in active_scope_decisions
                for entity_id in [decision.owner_entity_id, *decision.linked_entity_ids]
                if entity_id and entity_id not in active_entity_ids
            )
        ),
        "encounters_with_inactive_entities": sorted(
            (
                f"{encounter.encounter_id}:{encounter.entity_id}"
                for encounter in mem.artifacts.list_encounters()
                if encounter.entity_id not in active_entity_ids
            )
        ),
        "live_identity_decisions_with_inactive_entities": sorted(
            (
                f"{decision.decision_id}:{decision.entity_id}"
                for decision in mem.artifacts.list_entity_resolution_decisions()
                if decision.review_state != "rejected"
                and decision.entity_id
                and (decision.entity_id not in active_entity_ids)
            )
        ),
        "cohorts_with_inactive_entities": sorted(
            (
                f"{cohort.cohort_id}:{entity_id}"
                for cohort in mem.artifacts.list_scope_cohorts()
                for entity_id in cohort.revision_entity_ids
                if entity_id not in active_entity_ids
            )
        ),
        "entities_missing_pages": sorted(
            (
                f"{entity.entity_id}:{entity.slug}"
                for entity in entities.values()
                if entity.status == "active"
                and entity.materialization_state == "materialized"
                and (entity.slug not in pages)
            )
        ),
        "sources_missing_raw_log": sorted(
            (
                source.source_id
                for source in sources
                if source.raw_log_entry_id and source.raw_log_entry_id not in logs
            )
        ),
        "proposals_missing_claims": sorted(
            (
                f"{proposal.proposal_id}:{claim_id}"
                for proposal in proposals
                for claim_id in (
                    *proposal.incoming_claim_ids,
                    *proposal.target_claim_ids,
                )
                if claim_id not in claim_by_id
            )
        ),
        "pages_unclassified": sorted(
            (page.slug for page in wiki_pages if page.page_type is None)
        ),
        "pages_with_repeated_items": sorted(
            (
                f"{page.slug}:{fact_id}"
                for page in wiki_pages
                for fact_id, count in Counter(
                    (
                        item["fact_id"]
                        for section in page.sections
                        for item in section.get("items", [])
                        if item.get("kind") == "fact" and item.get("fact_id")
                    )
                ).items()
                if count > 1
            )
        ),
    }
    return {"healthy": not any(issues.values()), "issues": issues}
