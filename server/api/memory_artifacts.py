"""Artifact inspection endpoints."""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from mycelium.artifact_integrity import artifact_integrity
from mycelium.ontology import ontology_response
from server.api.memory_contracts import _stored_memory_file
from server.runtime import get_mem, load_meta

router = APIRouter()


@router.get("/ontology")
async def get_ontology():
    return ontology_response()


@router.get("/artifacts/overview")
async def artifact_overview():
    mem = get_mem()
    claims = mem.artifacts.list_claims()
    coverage = mem.artifacts.coverage_report()
    coverage["suppressed_claims"] = len(claims) - coverage["active_claims"]
    placements = mem.artifacts.list_placements()
    assigned = [placement for placement in placements if placement.status == "placed"]
    disposition_counts: dict[str, int] = {}
    for claim in claims:
        disposition_counts[claim.dream_disposition] = (
            disposition_counts.get(claim.dream_disposition, 0) + 1
        )
    proposal_status_counts: dict[str, int] = {}
    for proposal in mem.artifacts.list_reconsolidation_proposals():
        proposal_status_counts[proposal.status] = (
            proposal_status_counts.get(proposal.status, 0) + 1
        )
    return {
        "coverage": coverage,
        "lifecycle": {
            "consolidated_facts": len(mem.artifacts.list_consolidated_facts()),
            "entities": len(mem.artifacts.list_entities()),
            "wiki_pages": len(mem.wiki.list_all()),
        },
        "short_term_memory": mem.short_term_memory_status().as_dict(),
        "projection": {
            "page_assignments": len(assigned),
            "assigned_claims": len(assigned),
            "multi_page_claims": 0,
            "average_pages_per_claim": (1.0 if assigned else 0.0),
            "max_pages_per_claim": 1 if assigned else 0,
        },
        "integrity": artifact_integrity(mem),
        "dream_audit": {
            "runs": len(mem.artifacts.list_dream_runs()),
            "claim_dispositions": disposition_counts,
        },
        "reconsolidation_proposals": proposal_status_counts,
        "organization_proposals": {
            status: sum(
                proposal.status == status
                for proposal in mem.artifacts.list_organization_proposals()
            )
            for status in {
                proposal.status
                for proposal in mem.artifacts.list_organization_proposals()
            }
        },
        "archived_pages": len(list(mem.wiki.archive_dir.glob("*.md"))),
    }


@router.get("/artifacts/chat-episodes")
async def list_chat_episode_state():
    return [
        {
            "session_id": session_id,
            "query": record.get("query", "New session"),
            "transcript_turns": len(record.get("transcript", [])),
            "episode_seq": record.get("episode_seq"),
            "active_episode": record.get("active_episode"),
            "encoded_episodes": record.get("encoded_episodes", []),
        }
        for session_id, record in load_meta().items()
    ]


@router.get("/artifacts/sources")
async def list_artifact_sources():
    return [
        {
            "source_id": source.source_id,
            "source_type": source.source_type,
            "session_id": source.session_id,
            "recorded_at": source.recorded_at,
            "occurred_at": source.occurred_at,
            "participants": source.participants,
            "segment_count": len(source.segments),
        }
        for source in get_mem().artifacts.list_sources()
    ]


@router.get("/artifacts/sources/{source_id}")
async def get_artifact_source(source_id: str):
    try:
        artifacts = get_mem().artifacts
        source = artifacts.get_source(source_id)
        claimed = {
            segment_id
            for claim in artifacts.claims_for_sources([source_id], active_only=False)
            for provenance in claim.provenance
            if provenance.source_id == source_id
            for segment_id in provenance.segment_ids
        }
        episode = next(
            (item for item in artifacts.list_episodes() if item.source_id == source_id),
            None,
        )
        source_only = {
            item.segment_id
            for item in episode.segment_dispositions
            if item.disposition == "source_only"
        } if episode else set()
        return {
            **asdict(source),
            "segment_accounting": {
                segment.segment_id: (
                    "claimed"
                    if segment.segment_id in claimed
                    else "source_only"
                    if segment.segment_id in source_only
                    else "unaccounted"
                )
                for segment in source.segments
            },
        }
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Source artifact not found"
        ) from exc


@router.get("/artifacts/episodes")
async def list_artifact_episodes():
    episodes = get_mem().artifacts.list_episodes()
    return [
        {
            "episode_id": episode.episode_id,
            "source_id": episode.source_id,
            "source_type": episode.source_type,
            "occurred_at": episode.occurred_at,
            "participants": episode.participants,
            "extraction_status": episode.extraction_status,
            "extraction_error": episode.extraction_error,
            "segment_count": len(episode.segment_ids),
            "claim_count": len(episode.claim_ids),
            "source_only_segment_count": sum(
                item.disposition == "source_only"
                for item in episode.segment_dispositions
            ),
        }
        for episode in episodes
    ]


@router.get("/artifacts/episodes/{episode_id}")
async def get_artifact_episode(episode_id: str):
    try:
        return asdict(get_mem().artifacts.get_episode(episode_id))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Episode artifact not found"
        ) from exc


@router.get("/artifacts/claims")
async def list_artifact_claims():
    artifacts = get_mem().artifacts
    return [
        {
            "claim_id": claim.claim_id,
            "text": claim.text,
            "recorded_at": claim.recorded_at,
            "status": claim.status,
            "claim_type": claim.claim_type,
            "evidence_modality": claim.evidence_modality,
            "dream_disposition": claim.dream_disposition,
            "placement": (
                asdict(placement)
                if (placement := artifacts.placement_for_claim(claim.claim_id))
                else None
            ),
        }
        for claim in artifacts.list_claims()
    ]


@router.get("/artifacts/claims/{claim_id}")
async def get_artifact_claim(claim_id: str):
    try:
        artifacts = get_mem().artifacts
        claim = artifacts.get_claim(claim_id)
        placement = artifacts.placement_for_claim(claim_id)
        return {
            **asdict(claim),
            "placement": asdict(placement) if placement else None,
            "facts": [
                asdict(fact) for fact in artifacts.facts_for_claim(claim_id)
            ],
            "scope_decisions": [
                asdict(item)
                for item in artifacts.list_scope_decisions(claim_id=claim_id)
            ],
            "entity_references": [
                asdict(item)
                for item in artifacts.list_entity_references(claim_id=claim_id)
            ],
            "reconsolidation_proposals": [
                asdict(item)
                for item in artifacts.list_reconsolidation_proposals()
                if claim_id in {*item.incoming_claim_ids, *item.target_claim_ids}
            ],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claim artifact not found") from exc


@router.get("/artifacts/dream-runs")
async def list_artifact_dream_runs():
    runs = get_mem().artifacts.list_dream_runs()
    return [
        {
            "run_id": run.run_id,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "status": run.status,
            "source_count": len(run.source_ids),
            "decision_count": len(run.claim_decisions),
            "failure_count": len(run.failures),
            "pages_created": run.pages_created,
            "pages_updated": run.pages_updated,
        }
        for run in runs
    ]


@router.get("/artifacts/dream-runs/{run_id}")
async def get_artifact_dream_run(run_id: str):
    try:
        return asdict(get_mem().artifacts.get_dream_run(run_id))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Dream run artifact not found"
        ) from exc


@router.get("/artifacts/reconsolidation-proposals")
async def list_reconsolidation_proposals():
    return [
        asdict(proposal)
        for proposal in get_mem().artifacts.list_reconsolidation_proposals()
    ]


@router.get("/artifacts/reconsolidation-proposals/{proposal_id}")
async def get_reconsolidation_proposal(proposal_id: str):
    try:
        return asdict(get_mem().artifacts.get_reconsolidation_proposal(proposal_id))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Reconsolidation proposal not found"
        ) from exc


@router.get("/artifacts/entities")
async def list_artifact_entities(status: str | None = None):
    return [
        asdict(entity) for entity in get_mem().artifacts.list_entities(status=status)
    ]


@router.get("/artifacts/entity-resolution-decisions")
async def list_entity_resolution_decisions(review_state: str | None = None):
    return [
        asdict(item)
        for item in get_mem().artifacts.list_entity_resolution_decisions(
            review_state=review_state
        )
    ]


@router.get("/artifacts/entities/{entity_id}")
async def get_artifact_entity(entity_id: str):
    try:
        mem = get_mem()
        artifacts = mem.artifacts
        entity = artifacts.get_entity(entity_id)
        page_exists = (mem.wiki.wiki_dir / f"{entity.slug}.md").exists()
        return {
            **asdict(entity),
            "placements": [
                asdict(item) for item in artifacts.placements_for_entity(entity_id)
            ],
            "facts": [
                asdict(item)
                for item in artifacts.list_consolidated_facts(
                    owner_entity_id=entity_id
                )
            ],
            "encounters": [
                asdict(item) for item in artifacts.list_encounters(entity_id=entity_id)
            ],
            "resolution_decisions": [
                asdict(item)
                for item in artifacts.list_entity_resolution_decisions(
                    entity_id=entity_id
                )
            ],
            "page": (
                {"slug": entity.slug, "exists": True}
                if page_exists
                else None
            ),
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Entity artifact not found") from exc


@router.get("/artifacts/placements")
async def list_artifact_placements(status: str | None = None):
    return [asdict(item) for item in get_mem().artifacts.list_placements(status=status)]


@router.get("/artifacts/scope-decisions")
async def list_scope_decisions(claim_id: str | None = None, status: str | None = None):
    return [
        asdict(item)
        for item in get_mem().artifacts.list_scope_decisions(
            claim_id=claim_id, status=status
        )
    ]


@router.get("/artifacts/consolidated-facts")
async def list_consolidated_facts(
    owner_entity_id: str | None = None,
):
    return [
        {
            "fact_id": item.fact_id,
            "text": item.text,
            "owner_entity_id": item.owner_entity_id,
            "section_key": item.section_key,
            "state": item.state,
            "synthesis_origin": item.synthesis_origin,
            "confidence": item.confidence,
            "manual_text": item.manual_text,
            "member_claim_count": len(item.member_claim_ids),
            "linked_entity_count": len(item.linked_entity_ids),
        }
        for item in get_mem().artifacts.list_consolidated_facts(
            owner_entity_id=owner_entity_id
        )
    ]


@router.get("/artifacts/consolidated-facts/{fact_id}")
async def get_consolidated_fact(fact_id: str):
    try:
        artifacts = get_mem().artifacts
        fact = artifacts.get_consolidated_fact(fact_id)
        return {
            **asdict(fact),
            "claims": [
                asdict(artifacts.get_claim(claim_id))
                for claim_id in fact.member_claim_ids
            ],
            "owner": asdict(artifacts.get_entity(fact.owner_entity_id)),
            "linked_entities": [
                asdict(artifacts.get_entity(entity_id))
                for entity_id in fact.linked_entity_ids
            ],
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Fact artifact not found") from exc


@router.get("/artifacts/organization-proposals")
async def list_organization_proposals(status: str | None = None):
    return [
        asdict(item)
        for item in get_mem().artifacts.list_organization_proposals(status=status)
    ]


@router.get("/artifacts/files")
async def list_stored_memory_files():
    mem = get_mem()
    index_path = mem.wiki.wiki_dir / "_index.md"
    return {
        "wiki_index": (
            {"filename": index_path.name, "size": index_path.stat().st_size}
            if index_path.exists()
            else None
        ),
        "archived_pages": [
            {"filename": path.name, "size": path.stat().st_size}
            for path in sorted(mem.wiki.archive_dir.glob("*.md"))
        ],
    }


@router.get("/artifacts/files/{group}/{filename}")
async def get_stored_memory_file(group: str, filename: str):
    if "/" in filename or "\\" in filename or not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Invalid stored filename")
    mem = get_mem()
    if group == "index" and filename == "_index.md":
        path = mem.wiki.wiki_dir / filename
    elif group == "archive":
        path = mem.wiki.archive_dir / filename
    else:
        raise HTTPException(status_code=400, detail="Invalid stored file group")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Stored memory file not found")
    return _stored_memory_file(path)
