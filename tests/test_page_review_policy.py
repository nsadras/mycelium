from dataclasses import asdict
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from mycelium.artifacts import ArtifactStore, EntityResolutionDecision
from mycelium.organization import IdentityReviewService
from mycelium.page_admission import (
    NO_PAGE_BASIS,
    page_admission_model,
)
from mycelium.page_plan import page_plan_model
from mycelium.source_attribution import attributed_pages
from mycelium.page_reviews import reviewed_page_exclusions
from tests.memory_helpers import claim, place
from tests.test_page_admission import entity


def review(artifacts, entity_id=None):
    record = EntityResolutionDecision(
        "review",
        "entity_creation",
        entity_id,
        "artifact",
        "Hand drill",
        ["source-c1"],
        ["c1"],
        ["source-c1#seg-0001"],
        0.8,
        "An incidental identity",
        "review_required",
        "test",
        "2031-05-06",
        proposed_scope="context",
        proposed_page_state="no_page",
    )
    artifacts.save_entity_resolution_decision(record)
    return IdentityReviewService(artifacts).review("review", "approve")


@pytest.mark.parametrize("existing", [False, True])
def test_no_page_review_binds_identity_and_only_its_evidence(tmp_path, existing):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.create_entity("you", "You")
    for cid in ["c1", "c2"]:
        place(artifacts, claim(cid, "Source-backed statement", "2031-05-06"))
    untouched = asdict(artifacts.get_claim("c2"))
    subject = artifacts.create_entity("artifact", "Hand drill") if existing else None
    prior = asdict(subject) if subject else None
    decision = review(artifacts, subject.entity_id if subject else None)
    bound = artifacts.get_entity(decision.entity_id)
    assert bound.materialization_state == (
        "materialized" if existing else "provisional"
    )
    if existing:
        assert bound.title == prior["title"] and bound.aliases == prior["aliases"]
    aliases = {
        a: SimpleNamespace(claim=artifacts.get_claim(cid))
        for a, cid in [("C001", "c1"), ("C002", "c2")]
    }
    excluded, reviews = reviewed_page_exclusions(artifacts, aliases)
    assert excluded == {"C001": {bound.entity_id}}
    assert reviews[0]["decision_id"] == "review" and reviews[0]["claim_ids"] == ["C001"]
    assert artifacts.get_claim("c1").dream_disposition == "pending"
    assert asdict(artifacts.get_claim("c2")) == untouched


def test_admission_cannot_use_excluded_support_but_can_use_other_claims():
    subject = entity("artifact")
    schema = page_admission_model(
        ["C001", "C002"], {"artifact": subject}, excluded_pages={"C001": {"artifact"}}
    )
    choice = {
        "basis": "independent_artifact_context",
        "reason": "Independent documented use",
        "supporting_claims": ["C002"],
    }
    schema.model_validate({"page_admissions": {"artifact": choice}})
    with pytest.raises(ValidationError):
        schema.model_validate(
            {"page_admissions": {"artifact": {**choice, "supporting_claims": ["C001"]}}}
        )
    schema = page_admission_model(
        ["C001"], {"artifact": subject}, excluded_pages={"C001": {"artifact"}}
    )
    schema.model_validate(
        {
            "page_admissions": {
                "artifact": {**choice, "basis": NO_PAGE_BASIS, "supporting_claims": []}
            }
        }
    )
    with pytest.raises(ValidationError):
        schema.model_validate(
            {"page_admissions": {"artifact": {**choice, "supporting_claims": []}}}
        )


def test_placement_restricts_exact_claim_page_pair_and_retains_other_subjects():
    attributions = {
        "C001": {
            "artifact": {"relation_to_claim": "described"},
            "you": {"relation_to_claim": "described"},
        },
        "C002": {"artifact": {"relation_to_claim": "described"}},
    }
    pages = attributed_pages(attributions, {"artifact", "you"}, {"C001": {"artifact"}})
    assert pages == {"C001": ["you"], "C002": ["artifact"]}
    schema = page_plan_model(pages, {"artifact": "artifact", "you": "you"})

    def decision(owner):
        return {
            "primary_subject": owner,
            "primary_reason": "Source context",
            "pages": {owner: "overview" if owner == "artifact" else "current_context"},
            "uncertainty": None,
            "prominence": "detail",
        }

    schema.model_validate(
        {"decisions": {"C001": decision("you"), "C002": decision("artifact")}}
    )
    with pytest.raises(ValidationError):
        schema.model_validate(
            {"decisions": {"C001": decision("artifact"), "C002": decision("artifact")}}
        )


def test_unbound_page_review_fails_explicitly(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    artifacts.create_entity("you", "You")
    place(artifacts, claim("c1", "A source statement", "2031-05-06"))
    record = EntityResolutionDecision(
        "review",
        "entity_creation",
        None,
        "artifact",
        "Hand drill",
        ["source-c1"],
        ["c1"],
        ["source-c1#seg-0001"],
        0.8,
        "Incidental",
        "accepted",
        "test",
        "2031-05-06",
        reviewed_at="2031-05-07",
        proposed_scope="context",
        proposed_page_state="no_page",
    )
    artifacts.save_entity_resolution_decision(record)
    with pytest.raises(ValueError, match="exact subject"):
        reviewed_page_exclusions(
            artifacts, {"C001": SimpleNamespace(claim=artifacts.get_claim("c1"))}
        )


def test_changed_page_eligibility_does_not_leak_through_an_existing_group():
    from dataclasses import replace
    from mycelium.artifacts import ClaimPlacement, ConsolidatedFact
    from mycelium.materialization import PageMaterializer

    claims = {
        cid: claim(cid, text, "2031-05-06")
        for cid, text in [
            ("c1", "Reviewed incidental detail"),
            ("c2", "Independent useful context"),
        ]
    }
    old = ConsolidatedFact(
        "fact",
        "Old prose combines both details.",
        ["c1", "c2"],
        "artifact",
        "overview",
        "current",
        [],
        "model",
        0.8,
        "Earlier grouping",
        "2031-05-06",
        "2031-05-06",
    )
    prior = ClaimPlacement(
        "c1",
        "artifact",
        "overview",
        [],
        "placed",
        "Original assignment",
        "2031-05-06",
        "2031-05-06",
    )
    placements = {
        "c1": replace(prior, owner_entity_id="you", section_key="current_context"),
        "c2": replace(prior, claim_id="c2"),
    }
    views = PageMaterializer._page_facts("artifact", old, claims, placements, {})
    assert len(views) == 1 and views[0].member_claim_ids == ["c2"]
    assert views[0].text == claims["c2"].text
    assert views[0].synthesis_origin == "claim"
