from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dataclasses import asdict
from typing import List, Optional
import uuid

from ollama import web_fetch, web_search

from mycelium.budget import count_message_tokens, truncate_text_tokens
from mycelium.memory_tools import MEMORY_TOOL_DEFINITIONS, MemoryToolset
from mycelium.models import WikiPage
from mycelium.operations import MemoryEvidence, RetrievalRequest
from mycelium.prompting import render_prompt
from mycelium.retrieval_context import render_memory_evidence
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


def _assistant_system_prompt() -> str:
    return render_prompt(
        "assistant/memory_agent.system.jinja",
        response_instructions=render_prompt(
            "assistant/chat_response.instructions.jinja"
        ),
    )


def _evidence_for_pages(
    evidence: MemoryEvidence, pages: list[WikiPage]
) -> MemoryEvidence:
    entity_ids = {page.entity_id for page in pages}
    include_unowned = "_short-term-memory" in entity_ids
    return MemoryEvidence(
        records=tuple(
            record
            for record in evidence.records
            if record.subject_entity_id in entity_ids
            or (record.subject_entity_id is None and include_unowned)
        ),
        sources=evidence.sources,
        truncated=evidence.truncated,
    )


def build_chat_prompt(
    record: dict,
    current_message: str,
    pages: list[WikiPage],
    evidence: MemoryEvidence,
    *,
    budget_tokens: int,
) -> tuple[list[dict[str, str]], list[WikiPage]]:
    """Fit system, current request, recent transcript, and memory under one budget."""
    if budget_tokens <= 0:
        raise ValueError("Assistant prompt budget must be positive")
    history = chat_history_messages(record, current_message)[:-1]
    recent_start = max(0, len(history) - 4)
    selected_history = history[recent_start:]
    selected_pages: list[WikiPage] = []

    def assemble(
        prompt_history: list[dict[str, str]],
        prompt_pages: list[WikiPage],
        user_content: str,
    ) -> list[dict[str, str]]:
        selected_evidence = _evidence_for_pages(evidence, prompt_pages)
        request = render_prompt(
            "assistant/memory_request.user.jinja",
            memory_evidence=render_memory_evidence(selected_evidence),
            user_request=user_content,
        )
        return [
            {"role": "system", "content": _assistant_system_prompt()},
            *prompt_history,
            {"role": "user", "content": request},
        ]

    messages = assemble(selected_history, selected_pages, current_message)
    while selected_history and count_message_tokens(messages) > budget_tokens:
        selected_history.pop(0)
        messages = assemble(selected_history, selected_pages, current_message)

    if count_message_tokens(messages) > budget_tokens:
        empty_user = assemble([], [], "")
        available = budget_tokens - count_message_tokens(empty_user)
        current_message = truncate_text_tokens(
            current_message, max(0, available), keep_end=True
        )
        messages = assemble([], [], current_message)
        if count_message_tokens(messages) > budget_tokens:
            raise ValueError(
                "Assistant prompt budget is smaller than the system prompt"
            )
        selected_history = []

    for page in pages:
        trial_pages = [*selected_pages, page]
        trial = assemble(selected_history, trial_pages, current_message)
        if count_message_tokens(trial) <= budget_tokens:
            selected_pages = trial_pages
            messages = trial

    for item in reversed(history[:recent_start]):
        trial_history = [item, *selected_history]
        trial = assemble(trial_history, selected_pages, current_message)
        if count_message_tokens(trial) <= budget_tokens:
            selected_history = trial_history
            messages = trial

    return messages, selected_pages


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
    retrieval_trace: Optional[dict] = None


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
        retrieval_query = render_prompt(
            "assistant/retrieval_query.user.jinja",
            chat_topic=record["query"],
            recent_thread=thread_context,
            no_prior_turns="(no prior turns)",
            user_message=req.message,
        )

        prompt_budget = min(
            mem.config.context_budget_tokens,
            mem.config.llm.context_window_tokens,
        )
        tool_evidence_budget = mem.config.retrieval.tool_evidence_budget_tokens
        if tool_evidence_budget >= prompt_budget:
            raise ValueError(
                "Memory tool evidence budget must be smaller than the assistant prompt budget"
            )
        initial_prompt_budget = prompt_budget - tool_evidence_budget
        retrieval = await mem.retrieve_context(
            RetrievalRequest(
                query=retrieval_query,
                budget_tokens=initial_prompt_budget,
            )
        )
        candidate_pages = list(retrieval.pages)
        messages, loaded_pages = build_chat_prompt(
            record,
            req.message,
            candidate_pages,
            retrieval.evidence,
            budget_tokens=initial_prompt_budget,
        )
        memory_tools = MemoryToolset(
            mem.retriever,
            result_limit=mem.config.retrieval.tool_result_limit,
            search_limit=mem.config.retrieval.tool_search_limit,
            evidence_budget_tokens=tool_evidence_budget,
            initial_claim_ids=retrieval.evidence.claim_ids,
        )
        chat_response = await mem.llm.call_messages(
            messages,
            num_ctx=mem.config.llm.context_window_tokens,
            max_tool_rounds=mem.config.retrieval.tool_search_limit,
            tool_definitions=[web_search, web_fetch, *MEMORY_TOOL_DEFINITIONS],
            tool_runner=memory_tools.run,
            tool_result_chars=max(
                8000,
                tool_evidence_budget * 6,
            ),
        )
        assistant_timestamp = iso_now()
        response_text = chat_response.content
        tool_events = [asdict(event) for event in chat_response.tool_events]
        loaded_page_meta = [
            {
                "slug": p.slug,
                "title": p.title,
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
                retrieval.trace,
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
            "retrieval_trace": retrieval.trace,
            "tool_events": tool_events,
            "tool_logs_created": len(tool_log_entries),
            "episode_id": episode_id,
        }
