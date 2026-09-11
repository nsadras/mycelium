"""Stage lifecycle edits, then publish an idempotent, recoverable file write set."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from mycelium.artifact_repository import _atomic_json


class MutationLock:
    """One reentrant mutation lock per store in this process; capture stays independent."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.owner = None
        self.depth = 0

    async def __aenter__(self):
        task = asyncio.current_task()
        if self.owner is not task:
            await self.lock.acquire()
            self.owner = task
        self.depth += 1

    async def __aexit__(self, *exc):
        self.depth -= 1
        if not self.depth:
            self.owner = None
            self.lock.release()


_locks: dict[Path, MutationLock] = {}


def mutation_lock(root: Path) -> MutationLock:
    return _locks.setdefault(root.resolve(), MutationLock())


class LifecycleTransaction:
    """Model work changes an isolated snapshot; publication needs no model calls.

    Artifacts use replace-on-write JSON, so unchanged files can be hard-linked.
    Wiki files use ordinary writes and are copied. Only changed files enter the
    journal. Capture that arrives during model work is outside this write set.
    """

    def __init__(self, artifacts: Path, wiki: Path):
        self.roots = {"artifacts": artifacts, "wiki": wiki}
        self.journals = artifacts / "lifecycle-operations"

    def operation_id(self, kind: str, inputs: dict) -> str:
        digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:24]
        return f"{kind}-{digest}"

    def _apply(self, path: Path, record: dict) -> dict:
        if record["status"] == "complete":
            return record["result"]
        for name, changes in record["writes"].items():
            root = self.roots[name]
            for relative, content in changes.items():
                target = root / relative
                if not target.resolve().is_relative_to(root.resolve()):
                    raise ValueError("Lifecycle journal path escapes its store")
                if content is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    fd, temporary = tempfile.mkstemp(dir=target.parent)
                    try:
                        with os.fdopen(fd, "w", encoding="utf-8") as stream:
                            stream.write(content)
                        os.replace(temporary, target)
                    finally:
                        if os.path.exists(temporary):
                            os.unlink(temporary)
        record["status"] = "complete"
        record.pop("writes", None)
        _atomic_json(path, record)
        return record["result"]

    def recover(self):
        for path in sorted(self.journals.glob("*.json")):
            record = json.loads(path.read_text())
            if record["status"] != "complete":
                self._apply(path, record)

    def completed(self, operation_id: str):
        path = self.journals / f"{operation_id}.json"
        if path.exists():
            return self._apply(path, json.loads(path.read_text()))
        return None

    @asynccontextmanager
    async def stage(self):
        with tempfile.TemporaryDirectory(prefix="mycelium-lifecycle-") as directory:
            staged = {}
            before = {}
            for name, root in self.roots.items():
                destination = Path(directory) / name
                before[name] = {str(p.relative_to(root)): p.read_text()
                                for p in root.rglob("*") if p.is_file()
                                and self.journals not in p.parents}
                shutil.copytree(root, destination, copy_function=os.link if name == "artifacts" else shutil.copy2,
                                ignore=shutil.ignore_patterns("lifecycle-operations"))
                staged[name] = destination
            yield staged, before

    def publish(self, operation_id: str, staged: dict, before: dict, result: dict):
        writes = {}
        for name, root in staged.items():
            after = {str(p.relative_to(root)): p.read_text() for p in root.rglob("*") if p.is_file()}
            changes = {key: after.get(key) for key in before[name].keys() | after.keys()
                       if before[name].get(key) != after.get(key)}
            # Capture may add new files while the operation runs. Preserve them;
            # reject a concurrent change to a file this operation would replace.
            for key in changes:
                original = self.roots[name] / key
                current = original.read_text() if original.exists() else None
                if current != before[name].get(key):
                    raise ValueError(f"Memory changed during lifecycle operation: {name}/{key}")
            writes[name] = changes
        record = {"status": "prepared", "writes": writes, "result": result}
        path = self.journals / f"{operation_id}.json"
        _atomic_json(path, record)
        return self._apply(path, record)
