from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dataclasses import asdict
from typing import List, Optional
import uuid

from mycelium.context import render_memory_context
from server.runtime import (
    append_tool_event_logs,
    append_turn,
    ensure_session_record,
    get_meta_lock,
    get_mem,
    get_session_lock,
    iso_now,
    load_meta,
    recent_thread_context,
    save_meta,
)

router = APIRouter()


def chat_history_messages(record: dict, current_message: str) -> list[dict[str, str]]:
    messages = []
    for item in record.get("transcript", []):
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": current_message})
    return messages

class SessionCreate(BaseModel):
    query: Optional[str] = "New session"

class SessionUpdate(BaseModel):
    query: str

class ChatRequest(BaseModel):
    message: str

class Message(BaseModel):
    role: str
    content: str
    timestamp: str
    loaded_pages: Optional[List[dict]] = None
    tool_events: Optional[List[dict]] = None

class SessionInfo(BaseModel):
    id: str
    query: str
    transcript: List[Message]

@router.get("/", response_model=List[dict])
async def list_sessions():
    async with get_meta_lock():
        meta = load_meta()
        for session_id, record in meta.items():
            ensure_session_record(record, session_id)
        save_meta(meta)
    return [{"id": k, "query": v["query"]} for k, v in meta.items()]

@router.post("/", response_model=dict)
async def create_session(req: SessionCreate):
    session_id = str(uuid.uuid4())[:8]
    async with get_meta_lock():
        meta = load_meta()
        meta[session_id] = {"query": req.query, "transcript": []}
        ensure_session_record(meta[session_id], session_id)
        save_meta(meta)
    return {"id": session_id, "query": req.query}

@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    async with get_meta_lock():
        meta = load_meta()
        if session_id not in meta:
            raise HTTPException(status_code=404, detail="Session not found")
        ensure_session_record(meta[session_id], session_id)
        save_meta(meta)
    return {"id": session_id, **meta[session_id]}

@router.patch("/{session_id}", response_model=dict)
async def update_session(session_id: str, req: SessionUpdate):
    name = req.query.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Session name cannot be empty")
    async with get_session_lock(session_id):
        async with get_meta_lock():
            meta = load_meta()
            if session_id not in meta:
                raise HTTPException(status_code=404, detail="Session not found")
            record = ensure_session_record(meta[session_id], session_id)
            record["query"] = name
            save_meta(meta)
    return {"id": session_id, "query": name}

@router.post("/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    user_timestamp = iso_now()
    async with get_session_lock(session_id):
        async with get_meta_lock():
            meta = load_meta()
            if session_id not in meta:
                raise HTTPException(status_code=404, detail="Session not found")
            record = ensure_session_record(meta[session_id], session_id)
            episode_id = record["active_episode"]["id"]

        mem = get_mem()
        thread_context = recent_thread_context(record)
        retrieval_query = (
            f"CHAT TOPIC:\n{record['query']}\n\n"
            f"RECENT THREAD:\n{thread_context or '(no prior turns)'}\n\n"
            f"USER MESSAGE:\n{req.message}"
        )

        loaded_pages = await mem.load_context(retrieval_query)
        memory_context = render_memory_context(loaded_pages)

        system_prompt = (
            "You are a helpful and intelligent AI assistant. "
            "You have access to a long-term memory wiki that contains information you've learned from previous interactions. "
            "Use the following memory context and the conversation history to inform your response if relevant.\n\n"
            f"MEMORY CONTEXT:\n{memory_context or 'No relevant long-term memory context was found.'}"
        )
        messages = [{"role": "system", "content": system_prompt}] + chat_history_messages(record, req.message)
        chat_response = await mem.llm.call_messages(messages)
        assistant_timestamp = iso_now()
        response_text = chat_response.content
        tool_events = [asdict(event) for event in chat_response.tool_events]
        loaded_page_meta = [
            {
                "slug": p.slug,
                "title": p.title,
                "confidence": p.confidence,
                "version": p.version,
            }
            for p in loaded_pages
        ]

        async with get_meta_lock():
            meta = load_meta()
            if session_id not in meta:
                raise HTTPException(status_code=404, detail="Session not found")
            append_turn(
                meta,
                session_id,
                req.message,
                response_text,
                user_timestamp,
                assistant_timestamp,
                loaded_page_meta,
                tool_events,
            )
            turn_count = int(meta[session_id]["active_episode"].get("turn_count", 0))
            save_meta(meta)

        tool_log_entries = await append_tool_event_logs(
            session_id,
            episode_id,
            tool_events,
            turn_count,
            assistant_timestamp,
        )

        return {
            "response": response_text,
            "user_timestamp": user_timestamp,
            "assistant_timestamp": assistant_timestamp,
            "loaded_pages": loaded_page_meta,
            "tool_events": tool_events,
            "tool_logs_created": len(tool_log_entries),
            "episode_id": episode_id,
        }
