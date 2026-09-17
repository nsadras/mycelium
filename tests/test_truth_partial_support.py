
from mycelium.config import Config
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from mycelium.artifacts import ClaimProvenance
from mycelium.truth_review import TruthReviewer
from tests.test_truth_scope import fixture
from tests.test_truth_staged_references import reference


def partially_retracted(artifacts):
    claim = artifacts.get_claim("left")
    prior = artifacts.get_source("source-left")
    active = replace(
        prior,
        source_id="remaining",
        segments=[replace(prior.segments[0], segment_id="remaining-line")],
    )
    artifacts.save_source(active)
    claim.provenance.append(ClaimProvenance("remaining", ["remaining-line"]))
    artifacts.save_claim(claim)
    artifacts.save_source(
        replace(
            prior,
            status="retracted",
            retracted_at="2031-01-03",
            retraction_reason="Withdrawn import",
        )
    )
    return claim, active


@pytest.mark.asyncio
async def test_partly_retracted_support_does_not_block_other_truth_review(tmp_path):
    artifacts, llm, placements, entities = fixture(tmp_path)
    claim, _ = partially_retracted(artifacts)
    artifacts.save_entity_reference(
        reference("automatic", "left", entity="person-mara")
    )
    artifacts.save_entity_reference(
        reference("reviewed", "left", origin="manual", entity="person-mara")
    )
    reviewer = TruthReviewer(llm, artifacts, Config())
    record = reviewer._records({"left": claim})["left"]
    assert record["text"] is None
    assert record["about"] == [] and record["temporal"] == []
    assert {c["source_id"] for c in record["citations"]} == {"remaining"}
    assert record["withdrawn_citations"] == [
        {
            "source_id": "source-left",
            "segment_id": claim.provenance[0].segment_ids[0],
            "status": "retracted",
        }
    ]
    assert [r["origin"] for r in record["identity_bindings"]] == ["manual"]
    result = await reviewer.review({"right"}, placements, entities, dream_run_id="test")
    assert not result.errors and len(result.proposals) == 1
    assert artifacts.get_claim("left") == claim
    assert len(artifacts.list_entity_references(claim_id="left", status="active")) == 2


@pytest.mark.asyncio
async def test_active_singleton_with_only_withdrawn_support_is_explicit_failure(
    tmp_path,
):
    artifacts, _, placements, entities = fixture(tmp_path)
    source = artifacts.get_source("source-left")
    artifacts.save_source(
        replace(
            source,
            status="retracted",
            retracted_at="2031-01-03",
            retraction_reason="Withdrawn import",
        )
    )
    llm = AsyncMock()
    result = await TruthReviewer(llm, artifacts, Config()).review(
        {"left"},
        placements,
        entities,
        dream_run_id="test",
        excluded_claim_ids={"right"},
    )
    assert result.failure_claim_ids == {"left"}
    assert "no active source support" in result.errors[0]
    assert artifacts.get_claim("left").status == "active"
    llm.call_structured.assert_not_awaited()
