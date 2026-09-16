from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from mycelium.database import database, UnitOfWork
from mycelium.artifacts import ArtifactStore
from mycelium.claim_index import LanceClaimIndex, _id_batches
from mycelium.sessions import SessionStore
from mycelium.snapshots import snapshot_store


def test_atomic_records_revisions_and_unique_slug(tmp_path):
    db = database(tmp_path)
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.put("entities", "a", {"slug": "one"})
            raise RuntimeError("rollback")
    assert db.ids("entities") == []
    assert db.revision("entities") == 0
    db.put("entities", "a", {"slug": "one"})
    with pytest.raises(ValueError, match="non-unique"):
        db.put("entities", "b", {"slug": "one"})
    assert db.ids("entities", "slug", "one") == ["a"]


def test_pending_identity_lookup_decodes_only_matching_records(tmp_path, monkeypatch):
    from dataclasses import asdict
    from mycelium.artifacts import EntityResolutionDecision
    artifacts = ArtifactStore(tmp_path / "artifacts")
    for i in range(100):
        decision = EntityResolutionDecision(str(i), "entity_creation", "entity", "person", "Person",
            [], [], [], .9, "Review fixture", "review_required" if i == 0 else "accepted", "test", "2031-01-01")
        artifacts.db.put("entity-resolution-decisions", str(i), asdict(decision))
    reads = []
    original = artifacts.db.get
    def get(kind, identifier):
        if kind == "entity-resolution-decisions":
            reads.append(identifier)
        return original(kind, identifier)
    monkeypatch.setattr(artifacts.db, "get", get)
    assert [d.decision_id for d in artifacts.list_entity_resolution_decisions(review_state="review_required")] == ["0"]
    assert reads == ["0"]


def test_live_writer_excluded_and_crash_releases_lease(tmp_path):
    code = "from pathlib import Path; from mycelium.database import database; import sys; d=database(Path(sys.argv[1])); print('ready', flush=True); sys.stdin.read()"
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(RuntimeError, match="already has a writer"):
            database(tmp_path)
    finally:
        process.kill()  # Only the test-owned child, simulating a crash.
        process.wait(timeout=10)
    db = database(tmp_path)
    db.put("claims", "a", {"text": "after crash"})
    assert db.get("claims", "a")["text"] == "after crash"


def test_snapshot_backs_up_wal_and_projects_committed_state(tmp_path):
    root = tmp_path / "live"
    db = database(root)
    db.put("claims", "a", {"text": "before"})
    with db.transaction():
        db.put("wiki", "a", {"content": "Committed page"})
        db.project("wiki/a.md", "Committed page")
    snapshot_store(root, tmp_path / "copy")
    db.put("claims", "a", {"text": "after"})
    copied = database(tmp_path / "copy")
    assert copied.get("claims", "a")["text"] == "before"
    assert (tmp_path / "copy/wiki/a.md").read_text() == "Committed page"
    assert not (tmp_path / "copy/indexes").exists()


def test_unit_collection_conflicts_and_rollback(tmp_path):
    db = database(tmp_path)
    db.put("claims", "a", {"text": "original"})
    unit = UnitOfWork(db)
    try:
        assert unit.ids("claims") == ["a"]
        unit.put("claims", "a", {"text": "proposed"})
        db.put("claims", "b", {"text": "new member"})
        with pytest.raises(ValueError, match="changed during"):
            unit.commit()
        assert db.get("claims", "a")["text"] == "original"
    finally:
        unit.close()


def test_session_listing_never_reads_transcripts(tmp_path, monkeypatch):
    db = database(tmp_path)
    sessions = SessionStore(db)
    sessions.save(
        "a",
        {"query": "First", "transcript": [{"role": "user", "content": "x" * 10000}]},
    )
    sessions.save("b", {"query": "Second", "transcript": []})
    original = db.get

    def summary_only(kind, identifier):
        assert kind != "messages"
        return original(kind, identifier)

    monkeypatch.setattr(db, "get", summary_only)
    sessions.rename("b", "Renamed")
    assert sessions.summaries()["a"]["message_count"] == 1
    assert sessions.summaries()["b"]["query"] == "Renamed"


@pytest.mark.asyncio
async def test_large_store_unchanged_search_has_no_filesystem_scan(
    tmp_path, monkeypatch
):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    with artifacts.db.transaction():
        for index in range(50000):
            artifacts.db.put("claims", str(index), {"text": f"Record {index}"})
    embedder = type("Embedder", (), {"model": "test"})()
    index = LanceClaimIndex(tmp_path / "indexes", artifacts, embedder)
    monkeypatch.setattr(index, "_claim_records", lambda: [])
    synchronize = AsyncMock()
    monkeypatch.setattr(index, "_synchronize", synchronize)
    await index.search("first")

    def forbidden(*args, **kwargs):
        raise AssertionError("Unchanged search must not scan filesystem or claims")

    monkeypatch.setattr(Path, "glob", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(index, "_claim_records", forbidden)
    assert await index.search("second") == []
    synchronize.assert_awaited_once()
    batches = list(_id_batches({str(i) for i in range(50000)}))
    assert len(batches) == 100
    assert all(len(batch) == 500 for batch in batches)


def test_entity_uniqueness_does_not_read_all_entities(tmp_path, monkeypatch):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    original_ids = artifacts.db.ids

    def indexed_ids(kind, field=None, value=None):
        assert kind != "entities" or field == "slug"
        return original_ids(kind, field, value)

    monkeypatch.setattr(artifacts.db, "ids", indexed_ids)
    monkeypatch.setattr(
        artifacts, "list_entities", lambda **kwargs: pytest.fail("full entity scan")
    )
    first = artifacts.create_entity("person", "Nora")
    second = artifacts.create_entity("person", "Nora")
    assert first.slug != second.slug
    assert artifacts.entity_for_slug(second.slug).entity_id == second.entity_id


def test_failed_synchronous_curation_rolls_back_all_edits(tmp_path):
    from mycelium.database import atomic_curation

    artifacts = ArtifactStore(tmp_path / "artifacts")

    class Service:
        def __init__(self):
            self.artifacts = artifacts

        @atomic_curation
        def edit(self):
            self.artifacts.db.put("claims", "a", {"text": "partial"})
            self.artifacts.db.project("wiki/a.md", "partial")
            raise ValueError("invalid later edit")

    with pytest.raises(ValueError, match="invalid later edit"):
        Service().edit()
    assert artifacts.db.ids("claims") == []
    assert artifacts.db.publication_status() == []
