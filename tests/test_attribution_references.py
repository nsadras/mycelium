from dataclasses import replace

import pytest

from mycelium.artifacts import ArtifactStore, ClaimEntityReference, MemoryClaim
from mycelium.consolidation_models import ClaimRoute, RoutingFailure, RoutingResult
from mycelium.dream_policy import DreamPolicy


NOW = "2031-05-06T10:00:00+00:00"


@pytest.fixture
def store(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    for cid in ("c1", "c2"):
        artifacts.save_claim(
            MemoryClaim(cid, "Two people share a display name.", [], [], NOW)
        )
    return artifacts


def ref(rid, *, claim="c1", entity=None, origin="scope", run="old", role="subject"):
    return ClaimEntityReference(
        rid,
        claim,
        role,
        "Taylor",
        entity,
        0.9,
        "Source-backed attribution.",
        origin,
        run,
        "active",
        NOW,
        identity_decision_id="review-1" if origin == "manual" else None,
    )


def test_distinct_people_with_same_surface_survive_save_and_reopen(store):
    people = [store.create_entity("person", "Taylor") for _ in range(2)]
    for i, person in enumerate(people):
        store.save_entity_reference(ref(f"r{i}", entity=person.entity_id))
    reopened = ArtifactStore(store.root)
    assert {r.entity_id for r in reopened.list_entity_references(status="active")} == {
        p.entity_id for p in people
    }


def test_replacement_retires_old_roles_and_preserves_manual_and_other_claims(store):
    rows = [
        ref("old"),
        ref("extracted", origin="extraction"),
        ref("reviewed", origin="manual", role="identity_subject"),
        ref("other", claim="c2"),
    ]
    for row in rows:
        store.save_entity_reference(row)
    incoming = ref("new", run="build-2", role="context")
    store.replace_automatic_entity_references(
        ["c1"], [incoming], dream_run_id="build-2"
    )
    assert {r.reference_id for r in store.list_entity_references(status="active")} == {
        "reviewed",
        "other",
        "new",
    }
    for rid in ("old", "extracted"):
        old = store.get_entity_reference(rid)
        assert old.status == "retired"
        assert old.retired_by_dream_run_id == "build-2"


def test_empty_successful_attribution_retires_previous_automatic_references(store):
    store.save_entity_reference(ref("old"))
    store.replace_automatic_entity_references(["c1"], [], dream_run_id="build-2")
    assert store.list_entity_references(status="active") == []
    assert store.get_entity_reference("old").status == "retired"


def test_failed_write_rolls_back_retirement_and_earlier_replacements(
    store, monkeypatch
):
    store.save_entity_reference(ref("old"))
    put = store.db.put

    def fail_second(kind, key, value):
        if kind == "entity-references" and key == "new-2":
            raise OSError("simulated disk failure")
        return put(kind, key, value)

    monkeypatch.setattr(store.db, "put", fail_second)
    with pytest.raises(OSError, match="disk failure"):
        store.replace_automatic_entity_references(
            ["c1"],
            [ref("new-1", run="new"), ref("new-2", run="new")],
            dream_run_id="new",
        )
    assert [r.reference_id for r in store.list_entity_references()] == ["old"]
    assert store.get_entity_reference("old").status == "active"


@pytest.mark.parametrize(
    "bad",
    [
        ref("wrong-claim", claim="c2", run="new"),
        ref("wrong-run"),
        ref("manual", run="new", origin="manual"),
        replace(
            ref("retired", run="new"), status="retired", retired_by_dream_run_id="later"
        ),
    ],
)
def test_replacement_scope_rejected_without_retiring_old_reference(store, bad):
    store.save_entity_reference(ref("old"))
    with pytest.raises(ValueError, match="active automatic decisions"):
        store.replace_automatic_entity_references(["c1"], [bad], dream_run_id="new")
    assert store.get_entity_reference("old").status == "active"


def test_replacement_replay_is_idempotent_and_cannot_overwrite_manual_ids(store):
    incoming = ref("new", run="build-2")
    for _ in range(2):
        store.replace_automatic_entity_references(
            ["c1"], [incoming], dream_run_id="build-2"
        )
    assert store.list_entity_references() == [incoming]
    store.save_entity_reference(ref("human", origin="manual"))
    with pytest.raises(ValueError, match="manual reference"):
        store.replace_automatic_entity_references(
            ["c1"], [ref("human", run="build-3")], dream_run_id="build-3"
        )
    assert store.get_entity_reference("new").status == "active"
    assert store.get_entity_reference("human").origin == "manual"


def test_duplicate_replacement_ids_rejected(store):
    row = ref("new", run="build-2")
    with pytest.raises(ValueError, match="unique"):
        store.replace_automatic_entity_references(
            ["c1"], [row, row], dream_run_id="build-2"
        )


def test_retired_reference_requires_replacing_build():
    with pytest.raises(ValueError, match="replacing build"):
        replace(ref("retired"), status="retired")


def test_revision_preserves_only_attribution_from_successful_routes():
    route = ClaimRoute(
        "c1", None, None, (), "source", "No page.", disposition="deferred"
    )
    initial = RoutingResult(routes=[route], entity_references=[ref("initial")])
    failed = RoutingResult(
        failures=[RoutingFailure("c1", "source", "Invalid model response")],
        entity_references=[ref("failed")],
    )
    result = DreamPolicy.merge_revision_routing(initial, failed)
    assert result.entity_references == initial.entity_references
    successful = RoutingResult(routes=[route], entity_references=[])
    result = DreamPolicy.merge_revision_routing(initial, successful)
    assert result.entity_references == []
