"""Opt-in direct probes of the production identity/page contract."""

import json
import os
from pathlib import Path

import pytest

from mycelium import Mycelium
from mycelium.artifacts import (
    ClaimProvenance,
    EntityRecord,
    MemoryClaim,
    SourceDocument,
    SourceSegment,
)
from mycelium.consolidation_models import ClaimEvidence
from mycelium.consolidation import ClaimRouter


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("MYCELIUM_RUN_IDENTITY_REPLAYS") != "1", reason="Opt-in host model probes"
)
async def test_staged_unnamed_identity_survives_revisit(tmp_path, monkeypatch):
    from dataclasses import asdict
    from mycelium.artifacts import EntityResolutionDecision

    monkeypatch.setenv("MYCELIUM_LLM_DEBUG_DIR", str(tmp_path / "llm"))
    memory = Mycelium(
        tmp_path / "store",
        config_path=Path(__file__).resolve().parents[1] / "mycelium.toml",
    )
    entity = EntityRecord(
        "person-traveler",
        "person",
        "The traveler",
        "traveler",
        [],
        "active",
        "2026-09-08",
        "2026-09-08",
    )
    source = SourceDocument(
        "s1",
        "tool_observation",
        "s",
        "2026-09-08",
        None,
        [],
        [
            SourceSegment(
                "s1#1",
                0,
                "A traveler at the station repaired a radio on Monday.",
                role="tool",
            ),
            SourceSegment(
                "s1#2",
                1,
                "That traveler also explained how the radio antenna works.",
                role="tool",
            ),
        ],
    )
    claims = [
        MemoryClaim(
            f"c{i}",
            seg.content,
            [],
            [ClaimProvenance("s1", [seg.segment_id])],
            "2026-09-08",
        )
        for i, seg in enumerate(source.segments, 1)
    ]
    memory.artifacts.save_source(source)
    for claim in claims:
        memory.artifacts.save_claim(claim)
    decision = EntityResolutionDecision(
        "d1",
        "entity_creation",
        entity.entity_id,
        "person",
        entity.title,
        ["s1"],
        [c.claim_id for c in claims],
        [s.segment_id for s in source.segments],
        0.9,
        "A particular traveler who repaired and explained a radio at the station.",
        "accepted",
        "first",
        "2026-09-08",
        identity_evidence_claim_ids=[c.claim_id for c in claims],
    )
    router = ClaimRouter(memory.llm, memory.artifacts, memory.config)
    result = await router.route(
        [ClaimEvidence(claims[1], source)],
        dream_run_id="revisit",
        seed_entities=[entity],
        seed_identity_decisions=[decision],
    )
    (tmp_path / "routing.json").write_text(
        json.dumps(asdict(result), indent=2, default=str)
    )
    assert not result.failures
    assert {e.entity_id for e in result.new_entities} <= {entity.entity_id}
    assert result.routes[0].owner_entity_id == entity.entity_id
    assert result.routes[0].placed
    assert all(d.entity_id == entity.entity_id for d in result.entity_decisions)
