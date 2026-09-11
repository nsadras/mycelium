"""Test setup/inspection for independent session records."""

from mycelium.database import database
from mycelium.sessions import SessionStore


def configure_sessions(monkeypatch, runtime, path):
    store = SessionStore(database(path.parent))
    monkeypatch.setattr(runtime, "get_sessions", lambda: store)
    from server.api import sessions

    monkeypatch.setattr(sessions, "get_sessions", lambda: store)
    return store


def read_sessions(runtime):
    store = runtime.get_sessions()
    return {key: store.get(key) for key in store.summaries()}


def seed_sessions(runtime, records):
    for key, record in records.items():
        runtime.get_sessions().save(key, record)
