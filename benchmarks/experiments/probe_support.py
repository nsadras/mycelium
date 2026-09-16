"""Shared recording and output-directory utilities for opt-in model probes."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ollama import AsyncClient


def fresh_run_root(name: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("benchmark_runs") / f"{name}-{stamp}-{uuid4().hex[:8]}"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str))


class RecordedSdk:
    def __init__(self, model, root):
        self.model, self.root = model, root
        self.sdk = AsyncClient(host="http://localhost:11434", timeout=900)
        self.index = len(list(root.glob("*.json")))

    async def chat(self, **request):
        self.index += 1
        options = {**request["options"], "seed": 17}
        if self.model == "qwen3.5:9b":
            options.update(temperature=1.0 if request.get("think") else 0.7,
                           top_p=0.95 if request.get("think") else 0.8,
                           top_k=20, min_p=0.0, presence_penalty=1.5,
                           repeat_penalty=1.0)
        request = {**request, "model": self.model, "options": options}
        path = self.root / f"{self.index:04d}.json"
        record = {"request": request}
        write(path, record)
        started = time.monotonic()
        try:
            response = await self.sdk.chat(**request)
            record["response"] = response.model_dump(mode="json", exclude_none=True)
            return response
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record["seconds"] = time.monotonic() - started
            write(path, record)

    async def close(self):
        await self.sdk._client.aclose()
