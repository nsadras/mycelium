"""Coverage and cross-store integrity reports for memory artifacts."""

from typing import Any

def coverage_report(store) -> dict[str, Any]:
    sources = store.list_sources()
    claims = store.list_claims()
    episodes = store.list_episodes()
    all_segments = {segment.segment_id for source in sources for segment in source.segments}
    claimed_segments = {
        segment_id for claim in claims for provenance in claim.provenance
        for segment_id in provenance.segment_ids
    }
    source_only_segments = {
        disposition.segment_id
        for episode in episodes
        for disposition in episode.segment_dispositions
        if disposition.disposition == "source_only"
    }
    pending_segments = {
        segment_id for episode in episodes for batch in episode.extraction_batches
        if batch.status != "complete" for segment_id in batch.segment_ids
    }
    unresolved = claimed_segments - all_segments
    accounted_segments = (claimed_segments | source_only_segments) & all_segments
    return {
        "sources": len(sources),
        "episodes": len(episodes),
        "claims": len(claims),
        "active_claims": sum(claim.status == "active" for claim in claims),
        "segments": len(all_segments),
        "claimed_segments": len(all_segments & claimed_segments),
        "segment_coverage": (len(all_segments & claimed_segments) / len(all_segments)) if all_segments else 1.0,
        "source_only_segments": len(all_segments & source_only_segments),
        "pending_extraction_segments": len(all_segments & pending_segments),
        "accounted_segments": len(accounted_segments),
        "accounted_coverage": (len(accounted_segments) / len(all_segments)) if all_segments else 1.0,
        "unassigned_segment_ids": sorted(all_segments - claimed_segments),
        "unaccounted_segment_ids": sorted(
            all_segments - claimed_segments - source_only_segments - pending_segments
        ),
        "pending_extraction_segment_ids": sorted(all_segments & pending_segments),
        "unplaced_claim_ids": sorted(
            claim.claim_id for claim in claims
            if not (
                (placement := store.placement_for_claim(claim.claim_id))
                and placement.owner_entity_id
            )
        ),
        "unresolved_provenance_ids": sorted(unresolved),
        "failed_episode_ids": sorted(ep.episode_id for ep in episodes if ep.extraction_status == "failed"),
        "partial_episode_ids": sorted(ep.episode_id for ep in episodes if ep.extraction_status == "partial"),
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
        entity_id for entity_id, entity in entities.items()
        if entity.status == "active"
    }
    active_scope_decisions = mem.artifacts.list_scope_decisions(status="active")
    active_references = mem.artifacts.list_entity_references(status="active")

    issues = {
        "sources_without_episode": sorted(
            source_id for source_id in source_by_id if source_id not in episode_source_ids
        ),
        "episodes_missing_source": sorted(
            episode.episode_id for episode in episodes if episode.source_id not in source_by_id
        ),
        "episodes_missing_claims": sorted(
            f"{episode.episode_id}:{claim_id}"
            for episode in episodes
            for claim_id in episode.claim_ids
            if claim_id not in claim_by_id
        ),
        "claims_missing_episode": sorted(
            claim.claim_id
            for claim in claims
            if claim.provenance
            and not any(provenance.source_id in episode_source_ids for provenance in claim.provenance)
        ),
        "claims_missing_provenance": sorted(
            claim.claim_id for claim in claims if not claim.provenance
        ),
        "claims_missing_source": sorted(
            f"{claim.claim_id}:{provenance.source_id}"
            for claim in claims
            for provenance in claim.provenance
            if provenance.source_id not in source_by_id
        ),
        "claims_missing_segments": sorted(
            f"{claim.claim_id}:{segment_id}"
            for claim in claims
            for provenance in claim.provenance
            if provenance.source_id in source_by_id
            for segment_id in provenance.segment_ids
            if segment_id
            not in {
                segment.segment_id for segment in source_by_id[provenance.source_id].segments
            }
        ),
        "placements_missing_claims": sorted(
            claim_id for claim_id in placements if claim_id not in claim_by_id
        ),
        "placements_missing_entities": sorted(
            f"{placement.claim_id}:{placement.owner_entity_id}"
            for placement in placements.values()
            if placement.owner_entity_id and placement.owner_entity_id not in entities
        ),
        "facts_missing_claims": sorted(
            f"{fact.fact_id}:{claim_id}"
            for fact in facts
            for claim_id in fact.member_claim_ids
            if claim_id not in claim_by_id
        ),
        "facts_missing_entities": sorted(
            f"{fact.fact_id}:{fact.owner_entity_id}"
            for fact in facts
            if fact.owner_entity_id not in entities
        ),
        "placements_with_inactive_entities": sorted(
            f"{placement.claim_id}:{entity_id}"
            for placement in placements.values()
            if placement.status == "placed"
            for entity_id in [
                placement.owner_entity_id,
                *placement.linked_entity_ids,
            ]
            if entity_id and entity_id not in active_entity_ids
        ),
        "facts_with_inactive_entities": sorted(
            f"{fact.fact_id}:{entity_id}"
            for fact in facts
            for entity_id in [fact.owner_entity_id, *fact.linked_entity_ids]
            if entity_id not in active_entity_ids
        ),
        "active_references_with_inactive_entities": sorted(
            f"{reference.reference_id}:{reference.entity_id}"
            for reference in active_references
            if reference.entity_id and reference.entity_id not in active_entity_ids
        ),
        "active_scope_with_inactive_entities": sorted(
            f"{decision.decision_id}:{entity_id}"
            for decision in active_scope_decisions
            for entity_id in [
                decision.owner_entity_id,
                *decision.linked_entity_ids,
            ]
            if entity_id and entity_id not in active_entity_ids
        ),
        "encounters_with_inactive_entities": sorted(
            f"{encounter.encounter_id}:{encounter.entity_id}"
            for encounter in mem.artifacts.list_encounters()
            if encounter.entity_id not in active_entity_ids
        ),
        "live_identity_decisions_with_inactive_entities": sorted(
            f"{decision.decision_id}:{decision.entity_id}"
            for decision in mem.artifacts.list_entity_resolution_decisions()
            if decision.review_state != "rejected"
            and decision.entity_id
            and decision.entity_id not in active_entity_ids
        ),
        "maturity_assessments_with_inactive_entities": sorted(
            f"{assessment.assessment_id}:{assessment.entity_id}"
            for assessment in mem.artifacts.list_identity_maturity_assessments()
            if assessment.entity_id
            and assessment.entity_id not in active_entity_ids
        ),
        "cohorts_with_inactive_entities": sorted(
            f"{cohort.cohort_id}:{entity_id}"
            for cohort in mem.artifacts.list_scope_cohorts()
            for entity_id in cohort.revision_entity_ids
            if entity_id not in active_entity_ids
        ),
        "entities_missing_pages": sorted(
            f"{entity.entity_id}:{entity.slug}"
            for entity in entities.values()
            if entity.status == "active"
            and entity.materialization_state == "materialized"
            and entity.slug not in pages
        ),
        "sources_missing_raw_log": sorted(
            source.source_id
            for source in sources
            if source.raw_log_entry_id and source.raw_log_entry_id not in logs
        ),
        "proposals_missing_claims": sorted(
            f"{proposal.proposal_id}:{claim_id}"
            for proposal in proposals
            for claim_id in (*proposal.incoming_claim_ids, *proposal.target_claim_ids)
            if claim_id not in claim_by_id
        ),
        "pages_unclassified": sorted(
            page.slug for page in wiki_pages if page.page_type is None
        ),
    }
    return {
        "healthy": not any(issues.values()),
        "issues": issues,
    }
