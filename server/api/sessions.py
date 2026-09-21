from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dataclasses import asdict
from typing import List, Optional
import uuid

from ollama import web_fetch, web_search

from mycelium.budget import count_message_tokens, ContextBudgetError
from mycelium.memory_tools import MEMORY_TOOL_DEFINITIONS, MemoryToolset
from mycelium.operations import MemoryEvidence, MemoryWorkspace, RetrievalRequest
from mycelium.prompting import render_prompt
from mycelium.retrieval_context import fit_memory_evidence, render_memory_workspace
from server.runtime import (
    capture_saved_turns,
    append_turn,
    ensure_session_record,
    get_meta_lock,
    get_mem,
    get_session_lock,
    iso_now,
    get_sessions,
)

router = APIRouter()


def _session_meta(session_id):
    try:
        return {session_id: get_sessions().get(session_id)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")


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


def build_chat_prompt(
    record: dict,
    current_message: str,
    evidence: MemoryEvidence,
    *,
    budget_tokens: int,
    workspace_search_limit: int,
    workspace_evidence_budget_tokens: int,
) -> tuple[list[dict[str, str]], MemoryEvidence, str]:
    """Fit system, current request, recent transcript, and memory under one budget."""
    if budget_tokens <= 0:
        raise ValueError("Assistant prompt budget must be positive")
    history = chat_history_messages(record, current_message)[:-1]
    recent_start = max(0, len(history) - 4)
    while recent_start < len(history) and history[recent_start]["role"] != "user":
        recent_start += 1
    selected_history = history[recent_start:]
    selected_evidence = MemoryEvidence(
        more_available=evidence.more_available
        or bool(evidence.records or evidence.sources)
    )

    def assemble(
        prompt_history: list[dict[str, str]],
        prompt_evidence: MemoryEvidence,
        user_content: str,
    ) -> list[dict[str, str]]:
        workspace = MemoryWorkspace(
            revision=0,
            request=user_content,
            evidence=prompt_evidence,
            operations=(),
            remaining_searches=workspace_search_limit,
            remaining_evidence_tokens=workspace_evidence_budget_tokens,
        )
        request = render_prompt(
            "assistant/memory_request.user.jinja",
            memory_evidence=render_memory_workspace(workspace, include_request=False),
            user_request=user_content,
        )
        return [
            {"role": "system", "content": _assistant_system_prompt()},
            *prompt_history,
            {"role": "user", "content": request},
        ]

    messages = assemble(selected_history, selected_evidence, current_message)
    while selected_history and count_message_tokens(messages) > budget_tokens:
        selected_history.pop(0)
        while selected_history and selected_history[0]["role"] != "user":
            selected_history.pop(0)
        messages = assemble(selected_history, selected_evidence, current_message)

    if count_message_tokens(messages) > budget_tokens:
        raise ContextBudgetError(
            "The current request exceeds the assistant context budget; shorten or split it"
        )

    selected_evidence = fit_memory_evidence(
        evidence,
        lambda trial: (
            count_message_tokens(assemble(selected_history, trial, current_message))
            <= budget_tokens
        ),
    )
    messages = assemble(selected_history, selected_evidence, current_message)

    older = history[:recent_start]
    turn_starts = [i for i, item in enumerate(older) if item["role"] == "user"]
    for start in reversed(turn_starts):
        trial_history = [*older[start:], *selected_history]
        trial = assemble(trial_history, selected_evidence, current_message)
        if count_message_tokens(trial) > budget_tokens:
            break
        messages = trial

    return messages, selected_evidence, current_message


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
    memory_workspace: Optional[dict] = None


class SessionInfo(BaseModel):
    id: str
    query: str
    transcript: List[Message]


@router.get("/", response_model=List[dict])
async def list_sessions():
    return [
        {"id": key, "query": record["query"]}
        for key, record in get_sessions().summaries().items()
    ]


@router.post("/", response_model=dict)
async def create_session(req: SessionCreate):
    session_id = str(uuid.uuid4())[:8]
    async with get_meta_lock():
        meta = {}
        meta[session_id] = {"query": req.query, "transcript": []}
        ensure_session_record(meta[session_id], session_id)
        get_sessions().save(session_id, meta[session_id])
    return {"id": session_id, "query": req.query}


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    async with get_meta_lock():
        meta = _session_meta(session_id)
        if session_id not in meta:
            raise HTTPException(status_code=404, detail="Session not found")
        ensure_session_record(meta[session_id], session_id)
    return {"id": session_id, **meta[session_id]}


@router.patch("/{session_id}", response_model=dict)
async def update_session(session_id: str, req: SessionUpdate):
    name = req.query.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Session name cannot be empty")
    async with get_session_lock(session_id):
        async with get_meta_lock():
            meta = _session_meta(session_id)
            if session_id not in meta:
                raise HTTPException(status_code=404, detail="Session not found")
            ensure_session_record(meta[session_id], session_id)
            get_sessions().rename(session_id, name)
    return {"id": session_id, "query": name}


@router.post("/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest):
    user_timestamp = iso_now()
    async with get_session_lock(session_id):
        async with get_meta_lock():
            meta = _session_meta(session_id)
            if session_id not in meta:
                raise HTTPException(status_code=404, detail="Session not found")
            record = ensure_session_record(meta[session_id], session_id)

        mem = get_mem()
        prompt_budget = min(
            mem.config.context_budget_tokens,
            mem.config.llm.context_window_tokens
            - (
                max(4096, mem.config.llm.reasoning_output_tokens)
                if mem.config.llm.reasoning_enabled
                else 4096
            )
            - 3072,
        )
        tool_evidence_budget = mem.config.retrieval.tool_evidence_budget_tokens
        if tool_evidence_budget >= prompt_budget:
            raise ValueError(
                "Memory tool evidence budget must be smaller than the assistant prompt budget"
            )
        # Reserve output, schema/tool envelopes, and room for tool evidence.
        initial_prompt_budget = prompt_budget - tool_evidence_budget
        try:
            preflight_messages, _, _ = build_chat_prompt(
                record,
                req.message,
                MemoryEvidence(),
                budget_tokens=initial_prompt_budget,
                workspace_search_limit=mem.config.retrieval.tool_search_limit,
                workspace_evidence_budget_tokens=tool_evidence_budget,
            )
        except ContextBudgetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        retrieval_query = render_prompt(
            "assistant/retrieval_query.user.jinja",
            chat_topic=record["query"],
            recent_thread="\n".join(
                f"{item['role']}: {item['content']}"
                for item in preflight_messages[1:-1]
            ),
            no_prior_turns="(no prior turns)",
            user_message=req.message,
        )
        retrieval = await mem.retrieve_context(
            RetrievalRequest(
                query=retrieval_query,
                budget_tokens=initial_prompt_budget,
            )
        )
        messages, initial_evidence, fitted_request = build_chat_prompt(
            record,
            req.message,
            retrieval.evidence,
            budget_tokens=initial_prompt_budget,
            workspace_search_limit=mem.config.retrieval.tool_search_limit,
            workspace_evidence_budget_tokens=tool_evidence_budget,
        )
        memory_tools = MemoryToolset(
            mem.retriever,
            result_limit=mem.config.retrieval.tool_result_limit,
            search_limit=mem.config.retrieval.tool_search_limit,
            evidence_budget_tokens=tool_evidence_budget,
            request=fitted_request,
            initial_evidence=initial_evidence,
        )
        current_request = render_prompt(
            "assistant/current_request.user.jinja", user_request=fitted_request
        )
        chat_response = await mem.llm.call_messages(
            messages,
            num_ctx=mem.config.llm.context_window_tokens,
            max_tool_rounds=mem.config.retrieval.tool_search_limit,
            tool_definitions=[web_search, web_fetch, *MEMORY_TOOL_DEFINITIONS],
            tool_runner=memory_tools.run,
            replaceable_context_message_index=len(messages) - 1,
            replacement_context_content=current_request,
        )
        assistant_timestamp = iso_now()
        response_text = chat_response.content
        tool_events = [asdict(event) for event in chat_response.tool_events]
        memory_workspace = asdict(memory_tools.workspace.snapshot)
        loaded_page_meta = [
            {
                "slug": p.slug,
                "title": p.title,
                "version": p.version,
            }
            for p in retrieval.page_references
            if p.entity_id
            in {entity_id for record in initial_evidence.records
                for entity_id in (record.subject_entity_id, *(s.entity_id for s in record.subjects))}
        ]

        async with get_meta_lock():
            meta = _session_meta(session_id)
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
                memory_workspace,
            )
            get_sessions().save(session_id, meta[session_id])

        capture_error = None
        try:
            await capture_saved_turns(session_id)
        except Exception as exc:
            # The reply is already durable. Build Memory or the next turn retries capture.
            capture_error = str(exc)

        return {
            "response": response_text,
            "user_timestamp": user_timestamp,
            "assistant_timestamp": assistant_timestamp,
            "loaded_pages": loaded_page_meta,
            "retrieval_trace": retrieval.trace,
            "tool_events": tool_events,
            "memory_workspace": memory_workspace,
            "capture_status": "pending" if capture_error else "captured",
            "capture_error": capture_error,
        }
