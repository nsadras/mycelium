"""Structural admission and recovery preserve independently valid work."""

from copy import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from mycelium import Mycelium, memory_contract
from mycelium.artifacts import ArtifactStore
from mycelium.database import UnitOfWork
from mycelium.memory_admission import retention
from mycelium.memory_inputs import compact_retention
from mycelium.retention import Retainer, related_claim_ids
from tests.test_conversation_build import capture, configured


def identity_payload():
    return {"participants": [{"id": "p", "subject_id": None}],
            "segments": [{"id": "s", "text": "A statement"}], "context_segments": [],
            "existing_subjects": [{"id": "you", "entity_type": "you", "title": "You"}],
            "new_subject_ids": ["person", "project", "other"], "prior_memories": []}


def subject(identifier, kind="person", participants=("p",)):
    return {"id": identifier, "title": identifier, "entity_type": kind, "participant_ids": list(participants)}


def test_ineligible_bindings_do_not_poison_valid_identity():
    payload = identity_payload()
    result, rejected = retention(payload, {"subjects": [subject("project", "project"), subject("person")],
        "memories": [], "changes": []})
    assert result["subjects"][0]["participant_ids"] == []
    assert result["subjects"][1]["participant_ids"] == ["p"]
    assert len(rejected) == 1 and "only bind to a person" in rejected[0]["reason"]
    payload["participants"][0]["subject_id"] = "you"
    result, rejected = retention(payload, {"subjects": [subject("person"), subject("you", "you")],
        "memories": [], "changes": []})
    assert [s["participant_ids"] for s in result["subjects"]] == [[], ["p"]]
    assert len(rejected) == 1 and "cannot change" in rejected[0]["reason"]


def test_genuine_person_conflicts_are_rejected_without_guessing():
    result, rejected = retention(identity_payload(), {"subjects": [subject("person"), subject("other")],
        "memories": [], "changes": []})
    assert all(s["participant_ids"] == [] for s in result["subjects"])
    assert len(rejected) == 2 and all("Conflicting" in r["reason"] for r in rejected)


@pytest.mark.parametrize("compact", [False, True])
def test_bad_titles_and_new_account_owner_do_not_discard_independent_memory(compact):
    payload = identity_payload()
    if compact:
        payload, _ = compact_retention(payload)
    a, b, c = payload["new_subject_ids"]
    good = subject(a, participants=())
    bad_title = {**subject(b, participants=()), "title": " \n\t "}
    bad_owner = subject(c, "you", ())
    sid = payload["segments"][0]["id"]
    result, rejected = retention(payload, {"subjects": [good, bad_title, bad_owner], "memories": [
        {"id": name, "text": "A retained statement", "segment_ids": [sid], "subject_ids": [owner]}
        for name, owner in [("good", a), ("bad-title", b), ("bad-owner", c)]], "changes": []})
    assert [m["id"] for m in result["memories"]] == ["good"]
    assert len(rejected) == 4
    # The strict mutation contract enforces the same singleton invariant.
    with pytest.raises(ValueError, match="account owner"):
        memory_contract.retention_model(payload).model_validate({"subjects": [bad_owner], "memories": [], "changes": []})


@pytest.mark.asyncio
@pytest.mark.parametrize("overlap", [False, True])
async def test_prior_candidates_include_late_chunks_with_exact_deduplication(monkeypatch, overlap):
    chunks = ["first", "middle", "last"]
    monkeypatch.setattr("mycelium.retention.split_text_by_tokens", lambda text, size: chunks)
    async def search(chunk, limit):
        return [SimpleNamespace(claim_id="shared" if overlap and i == 0 else f"{chunk}-{i}") for i in range(limit)]
    index = SimpleNamespace(search=AsyncMock(side_effect=search))
    ids = await related_claim_ids(index, "source")
    assert len(ids) == len(set(ids)) == 48
    assert "last-15" in ids
    if overlap:
        assert ids[0] == "shared" and ids.count("shared") == 1
    else:
        assert [sum(cid.startswith(chunk) for cid in ids) for chunk in chunks] == [16, 16, 16]
    assert index.search.await_count == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("independent_snapshot", [False, True])
async def test_competing_completion_survives_failure_and_next_build(tmp_path, monkeypatch, independent_snapshot):
    with Mycelium(tmp_path) as memory:
        configured(memory, monkeypatch)
        captured = await capture(memory, "The instrument is ready.")
        async def competing_commit(llm, payload):
            # The second UnitOfWork opens a separate SQLite connection, stages a
            # real competing transaction and validates it against the same store.
            unit = UnitOfWork(memory.db) if independent_snapshot else None
            artifacts = ArtifactStore(tmp_path, db=unit) if unit else memory.artifacts
            retainer = Retainer(llm, artifacts, memory.config)
            encoder = copy(memory.encoder)
            encoder.artifacts = artifacts
            source = artifacts.get_source(captured.source_ids[0])
            episode = artifacts.get_episode(captured.episode_ids[0])
            batch = episode.extraction_batches[0]
            result = {"subjects": [], "memories": [{"id": "m", "text": "The instrument is ready.",
                "subject_ids": [], "segment_ids": [payload["segments"][0]["id"]]}], "changes": []}
            try:
                with artifacts.db.transaction():
                    episode.claim_ids = retainer.save_retained_memories(source, batch.batch_id, payload, result)
                    batch.status, batch.response = "complete", result
                    batch.attempt_count += 1
                    retainer.finalize_episode(source, episode, encoder)
                if unit:
                    unit.commit()
            finally:
                if unit:
                    unit.close()
            return result
        retain = AsyncMock(side_effect=competing_commit)
        monkeypatch.setattr(memory_contract, "retain", retain)
        result = await memory.consolidate()
        assert any("Memory changed" in f["reason"] for f in result.report.failures)
        episode = memory.artifacts.get_episode(captured.episode_ids[0])
        assert episode.extraction_status == episode.extraction_batches[0].status == "complete"
        assert episode.claim_ids == [c.claim_id for c in memory.artifacts.list_claims()]
        assert len(episode.claim_ids) == 1
        await memory.consolidate()
        assert retain.await_count == 1


@pytest.mark.asyncio
async def test_ordinary_failure_is_retryable_and_counts_attempts(tmp_path, monkeypatch):
    with Mycelium(tmp_path) as memory:
        configured(memory, monkeypatch)
        await capture(memory, "The instrument is ready.")
        real = memory_contract.retain
        monkeypatch.setattr(memory_contract, "retain", AsyncMock(side_effect=RuntimeError("offline")))
        assert (await memory.consolidate()).report.failures
        episode, = memory.artifacts.list_episodes()
        assert episode.extraction_batches[0].status == "failed"
        assert episode.extraction_batches[0].attempt_count == 1
        monkeypatch.setattr(memory_contract, "retain", real)
        assert not (await memory.consolidate()).report.failures
        episode, = memory.artifacts.list_episodes()
        assert episode.extraction_batches[0].status == "complete"
        assert episode.extraction_batches[0].attempt_count == 2
