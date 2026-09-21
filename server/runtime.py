from __future__ import annotations

import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any

import mycelium
from mycelium.artifacts import SourceSegment
from mycelium.models import LogEntry
from mycelium.operations import ConsolidationRequest, SourceInput
from mycelium.memory_tools import MEMORY_TOOL_NAMES
from engram import EngramConfig, EngramService, EngramStore


_mem: mycelium.Mycelium | None = None
_engram: EngramService | None = None
_dream_lock: asyncio.Lock | None = None
_meta_lock: asyncio.Lock | None = None
_session_locks: dict[str, asyncio.Lock] = {}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def get_mem() -> mycelium.Mycelium:
    global _mem
    if _mem is None:
        _mem = mycelium.Mycelium(
            store_path=os.environ.get("MYCELIUM_STORE", "./mycelium_store"),
            config_path="mycelium.toml",
        )
    return _mem


def get_engram() -> EngramService:
    global _engram
    if _engram is None:
        config = EngramConfig.from_toml("mycelium.toml")
        config.ensure_dirs()
        _engram = EngramService(config, EngramStore(config.db_path), get_mem)
        _engram.recover_interrupted_meetings()
    return _engram


def get_sessions():
    from mycelium.sessions import SessionStore

    return SessionStore(get_mem().db)


def get_meta_lock() -> asyncio.Lock:
    global _meta_lock
    if _meta_lock is None:
        _meta_lock = asyncio.Lock()
    return _meta_lock


def get_session_lock(session_id: str) -> asyncio.Lock:
    lock = _session_locks.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _session_locks[session_id] = lock
    return lock


def ensure_session_record(record: dict[str, Any], session_id: str) -> dict[str, Any]:
    record.setdefault("query", "New session")
    record.setdefault("transcript", [])
    record.setdefault("captured_turns", 0)
    if any(not str(m.get("timestamp") or "").strip() for m in record["transcript"]):
        raise ValueError(
            f"Session {session_id} contains timestamp-free transcript messages"
        )
    return record


def append_turn(
    meta: dict[str, Any],
    session_id: str,
    user_message: str,
    assistant_message: str,
    user_timestamp: str,
    assistant_timestamp: str,
    loaded_pages: list[dict[str, Any]] | None = None,
    tool_events: list[dict[str, Any]] | None = None,
    retrieval_trace: dict[str, Any] | None = None,
    memory_workspace: dict[str, Any] | None = None,
) -> None:
    record = ensure_session_record(meta[session_id], session_id)
    user_record = {
        "role": "user",
        "content": user_message,
        "timestamp": user_timestamp,
    }
    record["transcript"].append(user_record)
    assistant_record: dict[str, Any] = {
        "role": "assistant",
        "content": assistant_message,
        "timestamp": assistant_timestamp,
    }
    if loaded_pages is not None:
        assistant_record["loaded_pages"] = loaded_pages
    if tool_events is not None:
        assistant_record["tool_events"] = tool_events
    if retrieval_trace is not None:
        assistant_record["retrieval_trace"] = retrieval_trace
    if memory_workspace is not None:
        assistant_record["memory_workspace"] = memory_workspace
    record["transcript"].append(assistant_record)


def _format_tool_observation_content(
    *,
    chat_session_id: str,
    episode_id: str,
    turn_count: int,
    tool_event: dict[str, Any],
) -> str:
    status = "failed" if tool_event.get("failed") else "succeeded"
    arguments = json.dumps(tool_event.get("arguments", {}), indent=2, sort_keys=True)
    result = str(tool_event.get("result", "")).strip()

    return "\n".join(
        [
            "Tool observation from chat.",
            "",
            f"- chat_session_id: {chat_session_id}",
            f"- episode_id: {episode_id}",
            f"- turn_count: {turn_count}",
            f"- tool_name: {tool_event.get('tool_name', 'unknown')}",
            f"- status: {status}",
            "",
            "Arguments:",
            "```json",
            arguments,
            "```",
            "",
            "Result:",
            result or "(empty result)",
        ]
    )


async def append_tool_event_logs(
    session_id: str,
    episode_id: str,
    tool_events: list[dict[str, Any]],
    turn_count: int,
    occurred_at: str,
) -> list[LogEntry]:
    if not tool_events:
        return []

    mem = get_mem()
    created_entries = []

    for event_index, tool_event in enumerate(tool_events, start=1):
        if str(tool_event.get("tool_name") or "") in MEMORY_TOOL_NAMES:
            continue
        content = _format_tool_observation_content(
            chat_session_id=session_id,
            episode_id=episode_id,
            turn_count=turn_count,
            tool_event=tool_event,
        )
        tool_name = str(tool_event.get("tool_name") or "unknown")
        result = str(tool_event.get("result") or "").strip()
        ingestion = await mem.ingest_source(
            SourceInput(
                transcript=content,
                session_id=episode_id,
                source_type="tool_observation",
                occurred_at=occurred_at,
                metadata={
                    "chat_session_id": session_id,
                    "episode_id": episode_id,
                    "turn_count": turn_count,
                    "tool_name": tool_name,
                    "arguments": dict(tool_event.get("arguments") or {}),
                    "failed": bool(tool_event.get("failed")),
                },
                segments=(
                    SourceSegment(
                        segment_id="",
                        index=0,
                        speaker=tool_name,
                        role="tool",
                        content=result or "Tool call produced no result.",
                        timestamp=occurred_at,
                    ),
                ),
                idempotency_key=(
                    f"tool-observation:{session_id}:{episode_id}:"
                    f"{turn_count}:{event_index}"
                ),
            )
        )
        created_entries.extend(ingestion.log_entries)

    return created_entries


def _find_completed_turns(transcript: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Return list of (start_idx, assistant_idx) slices for completed turns."""
    turns = []
    start_idx = 0
    for idx, msg in enumerate(transcript):
        if msg.get("role") == "assistant":
            turns.append((start_idx, idx))
            start_idx = idx + 1
    return turns


async def capture_saved_turns(session_id: str) -> None:
    """Capture uncaptured completed turns. Caller holds this session's lock.

    The transcript is the durable retry input; the cursor advances only after
    all source writes for the turn succeed. Stable keys make replay safe.
    """
    async with get_meta_lock():
        meta = {session_id: get_sessions().get(session_id)}
        record = ensure_session_record(meta[session_id], session_id)
        transcript = list(record["transcript"])
        captured = int(record["captured_turns"])
    completed_turns = _find_completed_turns(transcript)
    for turn_index in range(captured, len(completed_turns)):
        start_idx, asst_idx = completed_turns[turn_index]
        messages = transcript[start_idx : asst_idx + 1]
        turn_id = f"{session_id}-turn-{turn_index + 1}"
        previous_ids = [
            m["source_id"]
            for m in transcript[max(0, start_idx - 8) : start_idx]
            if m.get("source_id")
        ]
        ingestion = await get_mem().ingest_source(
            SourceInput(
                transcript="\n".join(
                    f"[{m['timestamp']}] {m['role'].upper()}: {m['content']}"
                    for m in messages
                ),
                session_id=session_id,
                occurred_at=messages[0]["timestamp"],
                segments=tuple(
                    SourceSegment(
                        segment_id="",
                        index=i,
                        role=m["role"],
                        speaker=m["role"],
                        content=m["content"],
                        timestamp=m["timestamp"],
                    )
                    for i, m in enumerate(messages)
                ),
                metadata={"turn_index": turn_index, "context_source_ids": previous_ids},
                idempotency_key=f"chat-turn:{turn_id}",
            )
        )
        await append_tool_event_logs(
            session_id,
            turn_id,
            messages[-1].get("tool_events", []),
            turn_index + 1,
            messages[-1]["timestamp"],
        )
        async with get_meta_lock():
            meta = {session_id: get_sessions().get(session_id)}
            record = meta[session_id]
            record["captured_turns"] = turn_index + 1
            record["transcript"][asst_idx]["source_id"] = ingestion.source_ids[0]
            get_sessions().save(session_id, meta[session_id])
        transcript[asst_idx]["source_id"] = ingestion.source_ids[0]


def _get_dream_lock() -> asyncio.Lock:
    global _dream_lock
    if _dream_lock is None:
        _dream_lock = asyncio.Lock()
    return _dream_lock


def _dream_report_response(report) -> dict[str, Any]:
    return {
        "pages_updated": report.pages_updated,
        "pages_created": report.pages_created,
        "entries_consolidated": report.entries_consolidated,
        "completed_source_ids": report.completed_source_ids,
        "pending_source_ids": report.pending_source_ids,
        "failures": report.failures,
        "warnings": report.warnings,
        "reconsolidation_proposal_ids": report.reconsolidation_proposal_ids,
    }


async def run_consolidation() -> dict[str, Any]:
    async with _get_dream_lock():
        for session_id in get_sessions().summaries():
            async with get_session_lock(session_id):
                await capture_saved_turns(session_id)
        result = await get_mem().consolidate(
            ConsolidationRequest()
        )
    return _dream_report_response(result.report)


def clear_memory_store() -> dict[str, int]:
    mem = get_mem()
    counts = {
        "wiki_pages_deleted": len(mem.wiki.list_all()),
        "archived_pages_deleted": len(mem.db.ids("wiki-archive")),
        "logs_deleted": len(
            {entry.entry_id.split("#")[0] for entry in mem.log_store.list_entries(None)}
        ),
        "sessions_reset": 0,
    }
    with mem.db.transaction():
        mem.db.connection.execute("DELETE FROM publication")
        for kind, folder in (("wiki", "wiki"), ("wiki-archive", "wiki/_archive")):
            for identifier in mem.db.ids(kind):
                mem.db.delete(kind, identifier)
                mem.db.project(f"{folder}/{identifier}.md", None)
        dates = {
            entry.entry_id.split("#")[0] for entry in mem.log_store.list_entries(None)
        }
        for identifier in mem.db.ids("logs"):
            mem.db.delete("logs", identifier)
        for date in dates:
            mem.db.project(f"logs/{date}.md", None)
        artifact_counts = mem.artifacts.clear()
        for key in (
            "sources",
            "episodes",
            "claims",
            "dream_runs",
            "reconsolidation_proposals",
        ):
            counts[f"artifact_{key}_deleted"] = artifact_counts[key]
        for session_id in get_sessions().summaries():
            record = get_sessions().get(session_id)
            record["captured_turns"] = 0
            for message in record["transcript"]:
                message.pop("source_id", None)
            get_sessions().save(session_id, record)
            counts["sessions_reset"] += 1
        mem.wiki.save_index("# Wiki Index\n\n_last updated: never_\n\n## Pages\n")
        mem._ensure_user_profile()
    mem.retriever.claim_index._revision = None
    mem.retriever.claim_index._has_records = False
    indexes_dir = mem.store_path / "indexes"
    if indexes_dir.exists():
        shutil.rmtree(indexes_dir)
    mem.db.publish()
    return counts


def rebuild_wiki_store() -> dict[str, int]:
    """Recreate reading surfaces while preserving evidence and human corrections."""
    mem = get_mem()
    with mem.db.transaction():
        result = mem.consolidator.materializer.regenerate_all()
    mem.db.publish()
    return {
        "pages_updated": len(result.updated_slugs),
        "pages_created": len(result.created_slugs),
        "pages_deleted": len(result.deleted_slugs),
    }
