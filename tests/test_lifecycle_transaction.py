import pytest

from mycelium.database import database
from mycelium.lifecycle_transaction import LifecycleTransaction


@pytest.mark.asyncio
async def test_staging_keeps_live_evidence_unchanged_and_preserves_new_capture(
    tmp_path,
):
    db = database(tmp_path)
    db.put("claims", "a", {"text": "Original"})
    transaction = LifecycleTransaction(tmp_path / "artifacts", tmp_path / "wiki")
    async with transaction.stage() as (paths, before):
        paths["db"].put("claims", "a", {"text": "Corrected"})
        assert db.get("claims", "a")["text"] == "Original"
        db.put("sources", "new", {"capture": "arrived meanwhile"})
        transaction.publish("edit", paths, before, {"done": True})
    assert db.get("claims", "a")["text"] == "Corrected"
    assert db.get("sources", "new")["capture"] == "arrived meanwhile"
    assert transaction.completed("edit") == {"done": True}


@pytest.mark.asyncio
async def test_failed_model_work_does_not_publish_and_concurrent_edits_are_rejected(
    tmp_path,
):
    db = database(tmp_path)
    db.put("claims", "a", {"text": "Original"})
    transaction = LifecycleTransaction(tmp_path / "artifacts", tmp_path / "wiki")
    with pytest.raises(RuntimeError):
        async with transaction.stage() as (paths, before):
            paths["db"].put("claims", "a", {"text": "Unfinished"})
            raise RuntimeError("inference failed")
    assert db.get("claims", "a")["text"] == "Original"
    async with transaction.stage() as (paths, before):
        paths["db"].put("claims", "a", {"text": "Proposed"})
        db.put("claims", "a", {"text": "Other correction"})
        with pytest.raises(ValueError, match="changed during"):
            transaction.publish("edit", paths, before, {})


def test_recovery_replays_partial_publication_without_inference(tmp_path, monkeypatch):
    db = database(tmp_path)
    with db.transaction():
        db.put("claims", "a", {"text": "Corrected"})
        db.put("lifecycle-operations", "edit", {"result": {"done": True}})
        db.project("wiki/a.md", "Corrected")
    import mycelium.database as module

    original = module.os.replace

    def interrupted(source, target):
        raise OSError("interruption")

    monkeypatch.setattr(module.os, "replace", interrupted)
    transaction = LifecycleTransaction(tmp_path / "artifacts", tmp_path / "wiki")
    with pytest.raises(OSError):
        transaction.recover()
    assert db.get("claims", "a")["text"] == "Corrected"
    assert db.publication_status()[0]["error"] == "interruption"
    monkeypatch.setattr(module.os, "replace", original)
    transaction.recover()
    assert (tmp_path / "wiki/a.md").read_text() == "Corrected"
    assert transaction.completed("edit") == {"done": True}
