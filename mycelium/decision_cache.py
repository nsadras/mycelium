"""Durable reuse of validated decisions for an identical model request."""

from __future__ import annotations

import asyncio
import hashlib
import json
from weakref import WeakValueDictionary

from mycelium.database import UnitOfWork

_LOCKS: WeakValueDictionary = WeakValueDictionary()


class DecisionCache:
    def __init__(self, store, request):
        # Successful inference survives an aborted canonical mutation. Cache
        # records are derived data and never take part in its optimistic reads.
        self.db = store.db if isinstance(store, UnitOfWork) else store
        self.key = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        lock_key = (self.db.root, self.key)
        self.lock = _LOCKS.setdefault(lock_key, asyncio.Lock())

    def get(self):
        try:
            return self.db.get("model-decisions", self.key)
        except FileNotFoundError:
            return None

    def save(self, response, *, model_digest, stage):
        self.db.put("model-decisions", self.key, {
            "response": response, "model_digest": model_digest, "stage": stage,
            "request_digest": self.key,
        })
