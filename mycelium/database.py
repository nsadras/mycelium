"""Canonical SQLite storage, process ownership, and deterministic file publication."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import weakref
from contextlib import contextmanager
from pathlib import Path

_HANDLES: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
SCHEMA_VERSION = 1


class MemoryDatabase:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.path = self.root / "memory.sqlite3"
        if not self.path.exists() and (
            any((self.root / "artifacts").rglob("*.json"))
            or (self.root / "sessions_meta.json").exists()
            or any((self.root / "logs").glob("*.md"))
            or any((self.root / "wiki").glob("*.md"))
        ):
            raise ValueError(
                "Legacy memory store: select a fresh store directory; originals are unchanged."
            )
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "memory.sqlite3"
        self._lease = (self.root / ".writer.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self._lease.seek(0)
                self._lease.write(b"0")
                self._lease.flush()
                self._lease.seek(0)
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._lease.close()
            raise RuntimeError(
                f"Memory store already has a writer: {self.root}"
            ) from exc
        self.connection = sqlite3.connect(self.path, isolation_level=None)
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self.close()
            raise ValueError(f"Unsupported memory database version: {version}")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS generations(kind TEXT PRIMARY KEY, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS records(
                kind TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
                revision INTEGER NOT NULL, PRIMARY KEY(kind,id));
            CREATE UNIQUE INDEX IF NOT EXISTS entity_slug ON records(json_extract(payload,'$.slug')) WHERE kind='entities';
            CREATE TABLE IF NOT EXISTS changes(kind TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(kind,id));
            CREATE INDEX IF NOT EXISTS changes_revision ON changes(kind,revision);
            CREATE TABLE IF NOT EXISTS lookups(
                kind TEXT NOT NULL, id TEXT NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(kind,id,field,value), FOREIGN KEY(kind,id) REFERENCES records(kind,id) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS lookup_value ON lookups(kind,field,value,id);
            CREATE TABLE IF NOT EXISTS publication(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, content TEXT, error TEXT);
        """)
        self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.facade_clients = 0
        self.depth = 0
        self.closed = False

    @contextmanager
    def transaction(self):
        name = f"tx_{self.depth}"
        self.connection.execute(
            "BEGIN IMMEDIATE" if not self.depth else f"SAVEPOINT {name}"
        )
        self.depth += 1
        try:
            yield self
        except BaseException:
            self.depth -= 1
            if self.depth:
                self.connection.execute(f"ROLLBACK TO {name}")
                self.connection.execute(f"RELEASE {name}")
            else:
                self.connection.execute("ROLLBACK")
            raise
        else:
            self.depth -= 1
            self.connection.execute("COMMIT" if not self.depth else f"RELEASE {name}")

    def revision(self, kind):
        row = self.connection.execute(
            "SELECT revision FROM generations WHERE kind=?", (kind,)
        ).fetchone()
        return row[0] if row else 0

    def evidence_revision(self):
        return self.connection.execute("SELECT coalesce(sum(revision),0) FROM generations WHERE kind IN ('claims','sources','entities','placements','consolidated-facts','reconsolidation-proposals')").fetchone()[0]

    def get(self, kind, identifier):
        row = self.connection.execute(
            "SELECT payload FROM records WHERE kind=? AND id=?", (kind, identifier)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"{kind}/{identifier}")
        return json.loads(row[0])

    def ids(self, kind, field=None, value=None):
        if field is not None and value is not None:
            rows = self.connection.execute(
                "SELECT id FROM lookups WHERE kind=? AND field=? AND value=? ORDER BY id",
                (kind, field, str(value)),
            )
        else:
            rows = self.connection.execute(
                "SELECT id FROM records WHERE kind=? ORDER BY id", (kind,)
            )
        return [row[0] for row in rows]

    def put(self, kind, identifier, payload):
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self.transaction():
            row = self.connection.execute(
                "SELECT payload FROM records WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
            if row and row[0] == encoded:
                return
            self.connection.execute(
                "INSERT INTO generations VALUES (?,1) ON CONFLICT(kind) DO UPDATE SET revision=revision+1",
                (kind,),
            )
            try:
                self.connection.execute(
                    "INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload, revision=excluded.revision",
                    (kind, identifier, encoded, self.revision(kind)),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"Invalid or non-unique {kind} record: {identifier}"
                ) from exc
            self.connection.execute(
                "INSERT INTO changes VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET revision=excluded.revision",
                (kind, identifier, self.revision(kind)),
            )
            self.connection.execute(
                "DELETE FROM lookups WHERE kind=? AND id=?", (kind, identifier)
            )
            values = []
            for field in (
                "status",
                "slug",
                "claim_id",
                "entity_id",
                "owner_entity_id",
                "source_id",
                "dream_run_id",
                "review_state",
                "member_claim_ids",
                "session_id",
                "date",
            ):
                selected = payload.get(field)
                for value in selected if isinstance(selected, list) else [selected]:
                    if isinstance(value, (str, int)):
                        values.append((kind, identifier, field, str(value)))
            self.connection.executemany(
                "INSERT OR IGNORE INTO lookups VALUES (?,?,?,?)", values
            )

    def delete(self, kind, identifier):
        with self.transaction():
            changed = self.connection.execute(
                "DELETE FROM records WHERE kind=? AND id=?", (kind, identifier)
            ).rowcount
            if changed:
                self.connection.execute(
                    "INSERT INTO generations VALUES (?,1) ON CONFLICT(kind) DO UPDATE SET revision=revision+1",
                    (kind,),
                )
                self.connection.execute(
                    "INSERT INTO changes VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET revision=excluded.revision",
                    (kind, identifier, self.revision(kind)),
                )

    def changed_ids(self, kind, since):
        return {
            row[0]
            for row in self.connection.execute(
                "SELECT id FROM changes WHERE kind=? AND revision>?", (kind, since)
            )
        }

    def project(self, relative, content):
        if not (self.root / relative).resolve().is_relative_to(self.root):
            raise ValueError("Projection path escapes memory store")
        self.connection.execute(
            "INSERT INTO publication(path,content) VALUES (?,?)", (relative, content)
        )

    def publication_status(self):
        return [
            dict(zip(("sequence", "path", "error"), row))
            for row in self.connection.execute(
                "SELECT sequence,path,error FROM publication ORDER BY sequence"
            )
        ]

    def publish(self):
        if self.depth:
            return
        for sequence, relative, content in self.connection.execute(
            "SELECT sequence,path,content FROM publication ORDER BY sequence"
        ).fetchall():
            path = self.root / relative
            try:
                if not path.resolve().is_relative_to(self.root):
                    raise ValueError("Projection path escapes memory store")
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    fd, temp = tempfile.mkstemp(dir=path.parent)
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as stream:
                            stream.write(content)
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temp, path)
                    finally:
                        if os.path.exists(temp):
                            os.unlink(temp)
                self.connection.execute(
                    "DELETE FROM publication WHERE sequence=?", (sequence,)
                )
            except Exception as exc:
                self.connection.execute(
                    "UPDATE publication SET error=? WHERE sequence=?",
                    (str(exc), sequence),
                )
                raise

    def close(self):
        if not getattr(self, "closed", False):
            self.connection.close()
            self._lease.close()
            self.closed = True
            _HANDLES.pop(self.root, None)

    def __del__(self):
        if hasattr(self, "connection"):
            self.close()


def database(root: Path) -> MemoryDatabase:
    root = root.resolve()
    handle = _HANDLES.get(root)
    if handle is None or handle.closed:
        handle = MemoryDatabase(root)
        _HANDLES[root] = handle
    return handle


class UnitOfWork:
    """Snapshot reads and an isolated write set; no write lock during model work."""

    def __init__(self, db):
        self.db = db
        self.root = db.root
        self.reader = sqlite3.connect(db.path, isolation_level=None)
        self.reader.execute("BEGIN")
        # Establish snapshot immediately.
        self.reader.execute("SELECT count(*) FROM generations").fetchone()
        self.reads = {}
        self.collections = {}
        self.writes = {}
        self.projections = []

    def get(self, kind, identifier):
        key = (kind, identifier)
        if key in self.writes:
            value = self.writes[key]
            if value is None:
                raise FileNotFoundError(f"{kind}/{identifier}")
            return json.loads(json.dumps(value))
        row = self.reader.execute(
            "SELECT payload,revision FROM records WHERE kind=? AND id=?", key
        ).fetchone()
        self.reads[key] = row[1] if row else None
        if row is None:
            raise FileNotFoundError(f"{kind}/{identifier}")
        return json.loads(row[0])

    def revision(self, kind):
        row = self.reader.execute(
            "SELECT revision FROM generations WHERE kind=?", (kind,)
        ).fetchone()
        value = row[0] if row else 0
        self.collections[kind] = value
        return value

    def evidence_revision(self):
        return self.reader.execute("SELECT coalesce(sum(revision),0) FROM generations WHERE kind IN ('claims','sources','entities','placements','consolidated-facts','reconsolidation-proposals')").fetchone()[0]

    def ids(self, kind, field=None, value=None):
        self.revision(kind)
        if field is not None and value is not None:
            rows = self.reader.execute(
                "SELECT id FROM lookups WHERE kind=? AND field=? AND value=?",
                (kind, field, str(value)),
            )
        else:
            rows = self.reader.execute("SELECT id FROM records WHERE kind=?", (kind,))
        result = {row[0] for row in rows}
        for (written_kind, identifier), record in self.writes.items():
            if written_kind == kind:
                selected = record.get(field) if record is not None and field is not None else None
                matches = field is None or value is None or (
                    value in selected if isinstance(selected, list) else selected == value
                )
                if record is None or not matches:
                    result.discard(identifier)
                else:
                    result.add(identifier)
        return sorted(result)

    def validate_reads(self):
        """Validate consulted state without acquiring a write transaction."""
        for kind, expected in self.collections.items():
            if self.db.revision(kind) != expected:
                raise ValueError(f"Memory changed during operation: {kind}")
        for key, expected in self.reads.items():
            row = self.db.connection.execute(
                "SELECT revision FROM records WHERE kind=? AND id=?", key
            ).fetchone()
            if (row[0] if row else None) != expected:
                raise ValueError(f"Memory changed during operation: {key}")

    def put(self, kind, identifier, value):
        try:
            self.get(kind, identifier)
        except FileNotFoundError:
            pass
        self.writes[kind, identifier] = json.loads(json.dumps(value))

    def delete(self, kind, identifier):
        try:
            self.get(kind, identifier)
        except FileNotFoundError:
            pass
        self.writes[kind, identifier] = None

    @contextmanager
    def transaction(self):
        writes = dict(self.writes)
        length = len(self.projections)
        try:
            yield self
        except BaseException:
            self.writes = writes
            del self.projections[length:]
            raise

    def project(self, relative, content):
        self.projections.append((relative, content))

    def publish(self):
        pass  # Only the owning database publishes after the canonical commit.

    def commit(self):
        with self.db.transaction():
            for kind, expected in self.collections.items():
                if self.db.revision(kind) != expected:
                    raise ValueError(
                        f"Memory changed during lifecycle operation: {kind}"
                    )
            for key, expected in self.reads.items():
                row = self.db.connection.execute(
                    "SELECT revision FROM records WHERE kind=? AND id=?", key
                ).fetchone()
                if (row[0] if row else None) != expected:
                    raise ValueError(
                        f"Memory changed during lifecycle operation: {key}"
                    )
            for (kind, identifier), value in self.writes.items():
                if value is None:
                    self.db.delete(kind, identifier)
                else:
                    self.db.put(kind, identifier, value)
            for relative, content in self.projections:
                self.db.project(relative, content)
        self.db.publish()

    def close(self):
        self.reader.close()


def atomic_curation(method):
    """Group a synchronous domain edit and its projection intent into one commit."""
    from functools import wraps

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        db = self.artifacts.db
        with db.transaction():
            result = method(self, *args, **kwargs)
        db.publish()
        return result

    return wrapped
