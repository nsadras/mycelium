import json

import pytest

from mycelium.artifact_repository import _atomic_json
from mycelium.lifecycle_transaction import LifecycleTransaction


@pytest.mark.asyncio
async def test_staging_keeps_live_evidence_unchanged_and_preserves_new_capture(tmp_path):
    artifacts, wiki = tmp_path / "artifacts", tmp_path / "wiki"
    wiki.mkdir()
    _atomic_json(artifacts / "claims/a.json", {"text": "Original"})
    transaction = LifecycleTransaction(artifacts, wiki)
    async with transaction.stage() as (paths, before):
        _atomic_json(paths["artifacts"] / "claims/a.json", {"text": "Corrected"})
        assert json.loads((artifacts / "claims/a.json").read_text())["text"] == "Original"
        _atomic_json(artifacts / "sources/new.json", {"capture": "arrived meanwhile"})
        transaction.publish("edit", paths, before, {"done": True})
    assert json.loads((artifacts / "claims/a.json").read_text())["text"] == "Corrected"
    assert (artifacts / "sources/new.json").exists()
    assert transaction.completed("edit") == {"done": True}


@pytest.mark.asyncio
async def test_failed_model_work_does_not_publish_and_concurrent_edits_are_rejected(tmp_path):
    artifacts, wiki = tmp_path / "artifacts", tmp_path / "wiki"
    wiki.mkdir()
    _atomic_json(artifacts / "claims/a.json", {"text": "Original"})
    transaction = LifecycleTransaction(artifacts, wiki)
    with pytest.raises(RuntimeError):
        async with transaction.stage() as (paths, before):
            _atomic_json(paths["artifacts"] / "claims/a.json", {"text": "Unfinished"})
            raise RuntimeError("inference failed")
    assert json.loads((artifacts / "claims/a.json").read_text())["text"] == "Original"
    async with transaction.stage() as (paths, before):
        _atomic_json(paths["artifacts"] / "claims/a.json", {"text": "Proposed"})
        _atomic_json(artifacts / "claims/a.json", {"text": "Other correction"})
        with pytest.raises(ValueError, match="changed during"):
            transaction.publish("edit", paths, before, {})


def test_recovery_replays_partial_publication_without_inference(tmp_path, monkeypatch):
    artifacts, wiki = tmp_path / "artifacts", tmp_path / "wiki"
    wiki.mkdir()
    transaction = LifecycleTransaction(artifacts, wiki)
    path = transaction.journals / "edit.json"
    _atomic_json(path, {"status": "prepared", "writes": {
        "artifacts": {"claims/a.json": '{"text":"Corrected"}'},
        "wiki": {"a.md": "Corrected"}}, "result": {"done": True}})
    import mycelium.lifecycle_transaction as module
    original = module.os.replace
    def interrupted(source, target):
        if str(target).endswith("a.md"):
            raise OSError("interruption")
        return original(source, target)
    monkeypatch.setattr(module.os, "replace", interrupted)
    with pytest.raises(OSError):
        transaction.recover()
    assert (artifacts / "claims/a.json").exists()
    monkeypatch.setattr(module.os, "replace", original)
    transaction.recover()
    assert (wiki / "a.md").read_text() == "Corrected"
    assert transaction.completed("edit") == {"done": True}
