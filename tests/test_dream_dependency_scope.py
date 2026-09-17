from dataclasses import replace
from unittest.mock import Mock

import pytest

from mycelium.artifacts import ClaimEntityReference, ClaimPlacement, ScopeCohort
from tests.test_dream import add_claim, add_source, build_dream


def placement(cid, *, deferred=False):
    return ClaimPlacement(
        cid,
        None if deferred else "you",
        None if deferred else "profile",
        [],
        "deferred" if deferred else "placed",
        "Explicit test placement",
        "now",
        "now",
    )


@pytest.mark.parametrize("include_deferred", [False, True])
@pytest.mark.parametrize("source_limited", [False, True])
def test_preparation_preserves_requested_deferred_and_source_scope(
    tmp_path, include_deferred, source_limited
):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, new_source = add_source(logs, artifacts, suffix="incoming")
    incoming = add_claim(artifacts, new_source, claim_id="incoming")
    _, old_source = add_source(logs, artifacts, suffix="deferred")
    old = add_claim(artifacts, old_source, claim_id="deferred")
    artifacts.save_claim(replace(old, dream_disposition="deferred"))
    artifacts.save_placement(placement(old.claim_id, deferred=True))

    prepared = dream.prepare(
        include_deferred=include_deferred,
        source_ids={new_source.source_id} if source_limited else None,
    )
    expected = {incoming.claim_id}
    if include_deferred and not source_limited:
        expected.add(old.claim_id)
    assert {c.claim_id for c in prepared.queued_claims} == expected
    assert prepared.incoming_claim_ids == expected


def test_page_promotion_revisits_only_exact_active_dependencies(tmp_path):
    dream, _, _, logs, artifacts = build_dream(tmp_path, llm_response={})
    _, source = add_source(logs, artifacts)
    changed = artifacts.create_entity("project", "Promoted subject")
    other = artifacts.create_entity("project", "Unchanged subject")
    claims = {
        cid: add_claim(artifacts, source, claim_id=cid)
        for cid in (
            "incoming",
            "promoted",
            "old_you",
            "old_cohort",
            "old_deferred",
            "queued_neighbor",
            "retired_ref",
            "withdrawn",
            "excluded",
        )
    }
    for cid, claim in claims.items():
        artifacts.save_claim(replace(claim, dream_disposition="routed"))
        artifacts.save_placement(placement(cid))
    artifacts.save_claim(replace(claims["old_deferred"], dream_disposition="deferred"))
    artifacts.save_placement(placement("old_deferred", deferred=True))
    artifacts.save_claim(replace(claims["withdrawn"], status="retracted"))
    artifacts.save_claim(
        replace(claims["excluded"], dream_disposition="excluded_source_policy")
    )
    artifacts.save_scope_cohort(
        ScopeCohort(
            "prior",
            "prior-build",
            ["old_cohort"],
            [source.source_id],
            [],
            "now",
        )
    )
    for cid, eid in (
        ("promoted", changed.entity_id),
        ("withdrawn", changed.entity_id),
        ("excluded", changed.entity_id),
        ("retired_ref", changed.entity_id),
        ("incoming", other.entity_id),
        ("queued_neighbor", other.entity_id),
    ):
        artifacts.save_entity_reference(
            ClaimEntityReference(
                "ref-" + cid,
                cid,
                "subject",
                None,
                eid,
                1.0,
                "Explicit test dependency",
                "scope",
                "old-build",
                "retired" if cid == "retired_ref" else "active",
                "now",
                retired_by_dream_run_id="later" if cid == "retired_ref" else None,
            )
        )

    # Promotion lookup uses the existing entity index; it must not scan every
    # claim, owner, deferred placement or previous batch in the store.
    artifacts.list_claims = Mock(side_effect=AssertionError("Unbounded claim scan"))
    artifacts.list_placements = Mock(side_effect=AssertionError("Unrelated owner scan"))
    result = dream.policy.scope_revision_claims([claims["incoming"]], [changed])
    assert {c.claim_id for c in result} == {"incoming", "promoted"}
    assert dream.policy.scope_revision_claims([], [changed]) == []
