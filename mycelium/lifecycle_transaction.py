"""Stage lifecycle edits, then publish an idempotent, recoverable file write set."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path

from mycelium.database import database, UnitOfWork


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
    """Atomic canonical edits with deterministic post-commit publication."""

    def __init__(self, artifacts: Path, wiki: Path):
        self.db = database(artifacts.parent)

    def operation_id(self, kind: str, inputs: dict) -> str:
        digest = hashlib.sha256(
            json.dumps(inputs, sort_keys=True).encode()
        ).hexdigest()[:24]
        return f"{kind}-{digest}"

    def recover(self):
        self.db.publish()

    def completed(self, operation_id: str):
        try:
            result = self.db.get("lifecycle-operations", operation_id)["result"]
        except FileNotFoundError:
            return None
        self.db.publish()
        return result

    @asynccontextmanager
    async def stage(self):
        unit = UnitOfWork(self.db)
        try:
            yield {"db": unit}, None
        finally:
            unit.close()

    def publish(self, operation_id: str, staged: dict, before, result: dict):
        unit = staged["db"]
        unit.put("lifecycle-operations", operation_id, {"result": result})
        unit.commit()
        return result
