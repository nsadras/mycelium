from unittest.mock import AsyncMock

import pytest

from mycelium.artifacts import (
    ArtifactStore,
    ClaimPlacement,
    ClaimProvenance,
    ConsolidatedFact,
    EpisodeManifest,
    ExtractionSegmentDisposition,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.claim_lifecycle import (
    ClaimLifecycleConflictError,
    ClaimLifecycleService,
)
from mycelium.config import Config
from mycelium.facts import FactResolver
from mycelium.materialization import PageMaterializer
from mycelium.store import WikiStore


NOW = "2026-08-31T10:00:00-07:00"


def setup_service(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    wiki = WikiStore(tmp_path / "wiki")
    materializer = PageMaterializer(wiki, artifacts, Config.defaults())
    artifacts.create_entity("you", "You")
    llm = AsyncMock()
    llm.call_structured.side_effect = AssertionError(
        "These lifecycle fixtures should resolve structurally"
    )
    return (
        artifacts,
        wiki,
        ClaimLifecycleService(
            artifacts, materializer, FactResolver(llm, artifacts)
        ),
    )


def add_source(artifacts: ArtifactStore, source_id: str) -> str:
    segment_id = f"{source_id}#seg-0001"
    artifacts.save_source(SourceDocument(
        source_id=source_id,
        source_type="chat",
        session_id=f"session-{source_id}",
        recorded_at=NOW,
        occurred_at=NOW,
        participants=["user"],
        segments=[SourceSegment(segment_id, 0, "Source evidence")],
    ))
    artifacts.save_episode(EpisodeManifest(
        episode_id=f"episode-{source_id}",
        source_id=source_id,
        source_type="chat",
        occurred_at=NOW,
        participants=["user"],
        segment_ids=[segment_id],
        claim_ids=[],
        segment_dispositions=[ExtractionSegmentDisposition(
            segment_id=segment_id,
            disposition="source_only",
            reason="Fixture source is registered before its claim.",
        )],
        extraction_status="complete",
    ))
    return segment_id


def add_claim(
    artifacts: ArtifactStore,
    claim_id: str,
    provenance: list[ClaimProvenance],
    *,
    with_fact: bool = False,
) -> MemoryClaim:
    claim = MemoryClaim(
        claim_id=claim_id,
        text="The user prefers morning meetings.",
        about=[{"entity": "user"}],
        provenance=provenance,
        recorded_at=NOW,
        claim_type="preference",
        predicate="prefers",
        temporal_status="current",
        dream_disposition="routed",
    )
    artifacts.save_claim(claim)
    artifacts.save_placement(ClaimPlacement(
        claim_id=claim_id,
        owner_entity_id="you",
        section_key="preferences_working_style",
        linked_entity_ids=[],
        status="placed",
        reason="fixture",
        created_at=NOW,
        updated_at=NOW,
    ))
    if with_fact:
        artifacts.save_consolidated_fact(ConsolidatedFact(
            fact_id=f"fact-{claim_id}",
            text=claim.text,
            member_claim_ids=[claim_id],
            owner_entity_id="you",
            section_key="preferences_working_style",
            state="current",
            linked_entity_ids=[],
            synthesis_origin="claim",
            confidence=claim.confidence,
            reason="fixture",
            created_at=NOW,
            updated_at=NOW,
        ))
    return claim


@pytest.mark.asyncio
async def test_claim_correction_creates_explicit_evidence_and_rebuilds_projection(
    tmp_path,
):
    artifacts, wiki, service = setup_service(tmp_path)
    segment_id = add_source(artifacts, "source-original")
    original = add_claim(artifacts, "claim-original", [ClaimProvenance(
        source_id="source-original", segment_ids=[segment_id], speaker="user"
    )])

    result = await service.correct_claim(
        original.claim_id,
        "The user prefers afternoon meetings.",
        reason="The original time was incorrect.",
    )

    replacement = artifacts.get_claim(result.claim_ids[0])
    corrected_source = artifacts.get_source(result.source_ids[0])
    assert artifacts.get_claim(original.claim_id).status == "superseded"
    assert replacement.status == "active"
    assert replacement.text == "The user prefers afternoon meetings."
    assert replacement.confidence == 1.0
    assert {"relation": "supersedes", "target": original.claim_id} in replacement.links
    assert replacement.provenance[0].source_id == corrected_source.source_id
    assert corrected_source.source_type == "manual_correction"
    assert corrected_source.metadata["correction_reason"] == (
        "The original time was incorrect."
    )
    assert artifacts.get_episode(
        corrected_source.source_id.replace("source-", "episode-", 1)
    ).claim_ids == [replacement.claim_id]
    assert artifacts.placement_for_claim(replacement.claim_id).owner_entity_id == "you"
    facts = artifacts.facts_for_claim(replacement.claim_id)
    assert len(facts) == 1
    assert facts[0].text == replacement.text
    assert wiki.get("you").content.find(replacement.text) >= 0


@pytest.mark.asyncio
async def test_claim_correction_rejects_an_inactive_target(tmp_path):
    artifacts, _, service = setup_service(tmp_path)
    segment_id = add_source(artifacts, "source-original")
    original = add_claim(artifacts, "claim-original", [ClaimProvenance(
        source_id="source-original", segment_ids=[segment_id]
    )])
    original.status = "superseded"
    artifacts.save_claim(original)

    with pytest.raises(ClaimLifecycleConflictError):
        await service.correct_claim(
            original.claim_id, "Replacement", reason="Already replaced"
        )


@pytest.mark.asyncio
async def test_source_retraction_removes_claim_fact_and_page_projection(tmp_path):
    artifacts, wiki, service = setup_service(tmp_path)
    segment_id = add_source(artifacts, "source-only-support")
    claim = add_claim(
        artifacts,
        "claim-only-support",
        [ClaimProvenance("source-only-support", [segment_id])],
        with_fact=True,
    )
    service.materializer.regenerate({"you"})

    result = await service.retract_source(
        "source-only-support", reason="The transcript was imported in error."
    )

    source = artifacts.get_source("source-only-support")
    assert source.status == "retracted"
    assert source.retracted_at
    assert source.retraction_reason == "The transcript was imported in error."
    assert artifacts.get_claim(claim.claim_id).status == "retracted"
    assert result.claim_ids == [claim.claim_id]
    assert artifacts.facts_for_claim(claim.claim_id) == []
    assert claim.text not in wiki.get("you").content


@pytest.mark.asyncio
async def test_source_retraction_preserves_claim_with_other_active_support(tmp_path):
    artifacts, _, service = setup_service(tmp_path)
    first_segment = add_source(artifacts, "source-first")
    second_segment = add_source(artifacts, "source-second")
    claim = add_claim(
        artifacts,
        "claim-multi-source",
        [
            ClaimProvenance("source-first", [first_segment]),
            ClaimProvenance("source-second", [second_segment]),
        ],
        with_fact=True,
    )

    result = await service.retract_source(
        "source-first", reason="This copy of the transcript is invalid."
    )

    assert result.claim_ids == []
    assert artifacts.get_claim(claim.claim_id).status == "active"
    assert len(artifacts.facts_for_claim(claim.claim_id)) == 1


def test_source_lifecycle_fields_are_structurally_validated():
    with pytest.raises(ValueError, match="timestamp and reason"):
        SourceDocument(
            source_id="source-invalid",
            source_type="chat",
            session_id="session-invalid",
            recorded_at=NOW,
            occurred_at=NOW,
            participants=[],
            segments=[],
            status="retracted",
        )
