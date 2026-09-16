import gc
import sqlite3
import sys
import threading
import weakref

import pytest

from mycelium.database import database


def test_worker_gc_releases_connection_and_writer_lease_without_unraisable(tmp_path, monkeypatch):
    failures = []
    monkeypatch.setattr(sys, "unraisablehook", failures.append)
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        db = database(tmp_path)
        db.put("claims", "committed", {"text": "Keep this evidence"})
        db.connection.execute("BEGIN IMMEDIATE")
        db.connection.execute("INSERT INTO records VALUES ('claims','uncommitted','{}',1)")
        db.cycle = db
        reference = weakref.ref(db)
        del db
        collector = threading.Thread(target=gc.collect)
        collector.start()
        collector.join(timeout=10)
        assert not collector.is_alive()
        assert reference() is None
        assert failures == []
        reopened = database(tmp_path)
        assert reopened.ids("claims") == ["committed"]
        assert reopened.get("claims", "committed")["text"] == "Keep this evidence"
        reopened.close()
    finally:
        if was_enabled:
            gc.enable()


def test_database_operations_and_explicit_close_remain_thread_affine(tmp_path):
    db = database(tmp_path)
    db.put("claims", "one", {"text": "Original"})
    failures = []

    def foreign_access():
        for operation in [lambda: db.get("claims", "one"),
                          lambda: db.put("claims", "two", {}), db.close]:
            try:
                operation()
            except sqlite3.ProgrammingError as exc:
                failures.append(str(exc))

    worker = threading.Thread(target=foreign_access)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive()
    assert len(failures) == 3 and all("owning thread" in e for e in failures)
    assert db.ids("claims") == ["one"]
    assert db.depth == 0
    db.close()


def test_connection_initialization_failure_releases_writer_lease(tmp_path, monkeypatch):
    connect = sqlite3.connect

    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("Cannot open database")

    monkeypatch.setattr(sqlite3, "connect", unavailable)
    with pytest.raises(sqlite3.OperationalError):
        database(tmp_path)
    gc.collect()
    monkeypatch.setattr(sqlite3, "connect", connect)
    reopened = database(tmp_path)
    reopened.put("claims", "one", {})
    reopened.close()
