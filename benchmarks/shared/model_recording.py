"""Capture unchanged native inference requests for benchmark inspection."""

import asyncio
import copy
import json
import time
from pathlib import Path
from uuid import uuid4

from mycelium.telemetry import trace_metadata


class RecordingClient:
    def __init__(self, client, root: Path):
        self.client, self.root = client, root

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def chat(self, **request):
        # Every wrapper/restart gets unique paths; QA clients are recreated for
        # successive checkpoints and must never overwrite earlier requests.
        identifier = uuid4().hex
        path = self.root / f"{identifier}.json"
        record = {"id": identifier, "trace": trace_metadata(), "request": copy.deepcopy(request),
                  "started_at": time.time(), "status": "running"}

        def write():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, default=str))
            temporary.replace(path)

        write()
        started = time.monotonic()
        try:
            response = await self.client.chat(**request)
            record.update(status="complete", response=response.model_dump(mode="json", exclude_none=True))
            return response
        except asyncio.CancelledError as exc:
            deadline = record["trace"].get("experiment_deadline_at")
            record.update(status="cancelled", error=f"{type(exc).__name__}: {exc}",
                          cancellation_reason="deadline" if deadline is not None and time.time() >= deadline else "cancelled")
            raise
        except BaseException as exc:
            record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            record["seconds"] = time.monotonic() - started
            write()
