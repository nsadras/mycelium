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
            "raw_log_entry_id": source.raw_log_entry_id,
            "metadata": source.metadata,
            "segment_count": len(source.segments),
        }
        for source in get_mem().artifacts.list_sources()
    ]


@router.get("/artifacts/sources/{source_id}")
async def get_artifact_source(source_id: str):
    try:
        return asdict(get_mem().artifacts.get_source(source_id))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Source artifact not found"
        ) from exc


@router.get("/artifacts/episodes")
async def list_artifact_episodes():
    return [asdict(episode) for episode in get_mem().artifacts.list_episodes()]


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
            **asdict(claim),
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
        return {**asdict(claim), "placement": asdict(placement) if placement else None}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claim artifact not found") from exc


@router.get("/artifacts/dream-runs")
async def list_artifact_dream_runs():
    return [asdict(run) for run in get_mem().artifacts.list_dream_runs()]


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
        asdict(item)
        for item in get_mem().artifacts.list_consolidated_facts(
            owner_entity_id=owner_entity_id
        )
    ]


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
        "wiki_index": _stored_memory_file(index_path) if index_path.exists() else None,
        "archived_pages": [
            _stored_memory_file(path)
            for path in sorted(mem.wiki.archive_dir.glob("*.md"))
        ],
    }
