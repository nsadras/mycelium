from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import uuid

import mycelium
from mycelium.models import LogEntry
from engram import EngramConfig, EngramService, EngramStore

SESSIONS_FILE = Path("mycelium_store/sessions_meta.json")
DEFAULT_IDLE_MINUTES = 20
DEFAULT_MAX_TURNS = 25

_mem: mycelium.Mycelium | None = None
_engram: EngramService | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def get_mem() -> mycelium.Mycelium:
    global _mem
    if _mem is None:
        _mem = mycelium.Mycelium(store_path="./mycelium_store", config_path="mycelium.toml")
    return _mem


def get_engram() -> EngramService:
    global _engram
    if _engram is None:
        config = EngramConfig.from_toml("mycelium.toml")
        config.ensure_dirs()
        _engram = EngramService(config, EngramStore(config.db_path), get_mem)
        _engram.recover_interrupted_meetings()
    return _engram


def load_meta() -> dict[str, Any]:
    if not SESSIONS_FILE.exists():
        return {}
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_meta(meta: dict[str, Any]) -> None:
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def ensure_session_record(record: dict[str, Any], session_id: str) -> dict[str, Any]:
    record.setdefault("query", "New session")
    record.setdefault("transcript", [])
    record.setdefault("episode_seq", 1)
    record.setdefault("encoded_episodes", [])
    if "active_episode" not in record:
        record["active_episode"] = {
            "id": f"{session_id}-ep-1",
            "started_at": iso_now(),
            "last_activity_at": iso_now(),
            "buffer": [],
            "turn_count": 0,
        }
    return record


def append_turn(
    meta: dict[str, Any],
    session_id: str,
    user_message: str,
    assistant_message: str,
    loaded_pages: list[dict[str, Any]] | None = None,
    tool_events: list[dict[str, Any]] | None = None,
) -> None:
    record = ensure_session_record(meta[session_id], session_id)
    now = iso_now()
    record["transcript"].append({"role": "user", "content": user_message})
    assistant_record = {"role": "assistant", "content": assistant_message}
    if loaded_pages is not None:
        assistant_record["loaded_pages"] = loaded_pages
    if tool_events is not None:
        assistant_record["tool_events"] = tool_events
    record["transcript"].append(assistant_record)

    episode = record["active_episode"]
    episode["buffer"].append({"role": "user", "content": user_message})
    episode["buffer"].append(assistant_record)
    episode["turn_count"] = int(episode.get("turn_count", 0)) + 1
    episode["last_activity_at"] = now


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
    truncated = "yes" if tool_event.get("truncated") else "no"

    return "\n".join(
        [
            "Tool observation from chat.",
            "",
            f"- chat_session_id: {chat_session_id}",
            f"- episode_id: {episode_id}",
            f"- turn_count: {turn_count}",
            f"- tool_name: {tool_event.get('tool_name', 'unknown')}",
            f"- status: {status}",
            f"- truncated: {truncated}",
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


def append_tool_event_logs(
    session_id: str,
    episode_id: str,
    tool_events: list[dict[str, Any]],
    turn_count: int,
) -> list[LogEntry]:
    if not tool_events:
        return []

    mem = get_mem()
    now = utc_now()
    date_str = now.strftime("%Y-%m-%d")
    created_entries = []

    for tool_event in tool_events:
        short_id = str(uuid.uuid4())[:8]
        entry = LogEntry(
            entry_id=f"{date_str}#tool-{short_id}",
            session_id=episode_id,
            timestamp=now,
            content=_format_tool_observation_content(
                chat_session_id=session_id,
                episode_id=episode_id,
                turn_count=turn_count,
                tool_event=tool_event,
            ),
            importance=0.5,
            status="raw",
            durability="durable",
            consolidated=False,
        )
        mem.log_store.append(entry)
        created_entries.append(entry)

    return created_entries


def recent_thread_context(record: dict[str, Any], limit: int = 8) -> str:
    transcript = record.get("transcript", [])[-limit:]
    return "\n".join(f"{m.get('role', '').upper()}: {m.get('content', '')}" for m in transcript)


def episode_transcript(record: dict[str, Any]) -> str:
    episode = record.get("active_episode", {})
    return "\n".join(f"{m.get('role', '').upper()}: {m.get('content', '')}" for m in episode.get("buffer", []))


def start_new_episode(record: dict[str, Any], session_id: str) -> dict[str, Any]:
    record["episode_seq"] = int(record.get("episode_seq", 1)) + 1
    episode_id = f"{session_id}-ep-{record['episode_seq']}"
    record["active_episode"] = {
        "id": episode_id,
        "started_at": iso_now(),
        "last_activity_at": iso_now(),
        "buffer": [],
        "turn_count": 0,
    }
    return record["active_episode"]


async def flush_session_episode(session_id: str, reason: str = "manual") -> dict[str, Any]:
    meta = load_meta()
    if session_id not in meta:
        return {"session_id": session_id, "status": "missing", "entries_encoded": 0, "resolved_pages": []}

    record = ensure_session_record(meta[session_id], session_id)
    episode = record["active_episode"]
    transcript = episode_transcript(record)
    turn_count = int(episode.get("turn_count", 0))
    transcript_chars = len(transcript)
    if not transcript.strip():
        save_meta(meta)
        return {
            "session_id": session_id,
            "episode_id": episode["id"],
            "status": "empty",
            "entries_encoded": 0,
            "turn_count": turn_count,
            "transcript_chars": transcript_chars,
            "resolved_pages": [],
        }

    mem = get_mem()
    try:
        entries = await mem.encoder.encode_session(
            transcript,
            episode["id"],
        )
    except Exception as exc:
        save_meta(meta)
        return {
            "session_id": session_id,
            "episode_id": episode["id"],
            "status": "encode_error",
            "error": str(exc),
            "entries_encoded": 0,
            "turn_count": turn_count,
            "transcript_chars": transcript_chars,
            "resolved_pages": [],
        }
    if not entries:
        save_meta(meta)
        return {
            "session_id": session_id,
            "episode_id": episode["id"],
            "status": "no_entries",
            "entries_encoded": 0,
            "turn_count": turn_count,
            "transcript_chars": transcript_chars,
            "resolved_pages": [],
        }

    resolved_pages = await mem.reconsolidation_engine.resolve_labile_pages(episode["id"])
    record["encoded_episodes"].append(
        {
            "id": episode["id"],
            "encoded_at": iso_now(),
            "reason": reason,
            "turn_count": turn_count,
            "entries_encoded": len(entries),
            "resolved_pages": resolved_pages,
        }
    )
    start_new_episode(record, session_id)
    save_meta(meta)
    return {
        "session_id": session_id,
        "episode_id": episode["id"],
        "status": "flushed",
        "entries_encoded": len(entries),
        "turn_count": turn_count,
        "transcript_chars": transcript_chars,
        "resolved_pages": resolved_pages,
    }


async def flush_idle_episodes(
    idle_minutes: int = DEFAULT_IDLE_MINUTES,
    max_turns: int = DEFAULT_MAX_TURNS,
    force: bool = False,
) -> dict[str, Any]:
    meta = load_meta()
    now = utc_now()
    candidates: list[str] = []

    for session_id, record in meta.items():
        ensure_session_record(record, session_id)
        episode = record["active_episode"]
        if not episode.get("buffer"):
            continue
        last_activity = datetime.fromisoformat(episode["last_activity_at"])
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        is_idle = now - last_activity >= timedelta(minutes=idle_minutes)
        is_large = int(episode.get("turn_count", 0)) >= max_turns
        if force or is_idle or is_large:
            candidates.append(session_id)

    save_meta(meta)
    results = [await flush_session_episode(session_id, "manual") for session_id in candidates]
    return {"flushed": len([r for r in results if r["status"] == "flushed"]), "results": results}


async def resolve_session_reconsolidation(session_id: str) -> dict[str, Any]:
    meta = load_meta()
    if session_id not in meta:
        return {"session_id": session_id, "status": "missing", "resolved_pages": []}
    record = ensure_session_record(meta[session_id], session_id)
    save_meta(meta)
    episode_id = record["active_episode"]["id"]
    resolved_pages = await get_mem().reconsolidation_engine.resolve_labile_pages(episode_id)
    return {
        "session_id": session_id,
        "episode_id": episode_id,
        "status": "resolved",
        "resolved_pages": resolved_pages,
    }


async def run_dream() -> dict[str, Any]:
    report = await get_mem().dream()
    return {
        "pages_updated": report.pages_updated,
        "pages_created": report.pages_created,
        "entries_consolidated": report.entries_consolidated,
        "conflicts_found": report.conflicts_found,
        "conflicts_resolved": report.conflicts_resolved,
        "completed_source_ids": report.completed_source_ids,
        "pending_source_ids": report.pending_source_ids,
        "failures": report.failures,
    }


def clear_memory_store() -> dict[str, int]:
    mem = get_mem()
    counts = {
        "wiki_pages_deleted": 0,
        "archived_pages_deleted": 0,
        "logs_deleted": 0,
        "labile_files_deleted": 0,
        "artifact_sources_deleted": 0,
        "artifact_episodes_deleted": 0,
        "artifact_claims_deleted": 0,
        "sessions_reset": 0,
    }

    wiki_dir = mem.store_path / "wiki"
    archive_dir = wiki_dir / "_archive"
    logs_dir = mem.store_path / "logs"
    labile_dir = mem.store_path / "labile"

    for path in wiki_dir.glob("*.md"):
        if path.name == "_index.md":
            continue
        path.unlink()
        counts["wiki_pages_deleted"] += 1

    for path in archive_dir.glob("*.md"):
        path.unlink()
        counts["archived_pages_deleted"] += 1

    for path in logs_dir.glob("*.md"):
        path.unlink()
        counts["logs_deleted"] += 1

    for path in labile_dir.glob("*.md"):
        path.unlink()
        counts["labile_files_deleted"] += 1

    artifact_counts = mem.artifacts.clear()
    counts["artifact_sources_deleted"] = artifact_counts["sources"]
    counts["artifact_episodes_deleted"] = artifact_counts["episodes"]
    counts["artifact_claims_deleted"] = artifact_counts["claims"]
    counts["artifact_dream_runs_deleted"] = artifact_counts["dream_runs"]

    mem.wiki.save_index("# Wiki Index\n\n_last updated: never_\n\n## Pages\n")
    meta = load_meta()
    for session_id, record in meta.items():
        ensure_session_record(record, session_id)
        record["episode_seq"] = 1
        record["encoded_episodes"] = []
        record["active_episode"] = {
            "id": f"{session_id}-ep-1",
            "started_at": iso_now(),
            "last_activity_at": iso_now(),
            "buffer": record.get("transcript", []),
            "turn_count": len([m for m in record.get("transcript", []) if m.get("role") == "user"]),
        }
        counts["sessions_reset"] += 1
    save_meta(meta)
    mem._ensure_user_profile()
    return counts


def clear_wiki_store() -> dict[str, int]:
    mem = get_mem()
    counts = {
        "wiki_pages_deleted": 0,
        "archived_pages_deleted": 0,
        "logs_marked_unconsolidated": 0,
    }

    wiki_dir = mem.store_path / "wiki"
    archive_dir = wiki_dir / "_archive"

    for path in wiki_dir.glob("*.md"):
        if path.name == "_index.md":
            continue
        path.unlink()
        counts["wiki_pages_deleted"] += 1

    for path in archive_dir.glob("*.md"):
        path.unlink()
        counts["archived_pages_deleted"] += 1

    # Mark all event logs as unconsolidated to support seamless rebuilds
    log_files = list(mem.log_store.logs_dir.glob("*.md"))
    mem.log_store.mark_all_unconsolidated()
    counts["logs_marked_unconsolidated"] = len(log_files)

    mem.wiki.save_index("# Wiki Index\n\n_last updated: never_\n\n## Pages\n")
    mem._ensure_user_profile() # Auto-seed the profile page immediately

    return counts
