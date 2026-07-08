from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from engram.pipeline import meeting_response, segment_response
from server.runtime import get_engram

router = APIRouter()


@router.get("/meetings")
async def list_meetings():
    service = get_engram()
    return [
        meeting_response(meeting, [])
        for meeting in service.store.list_meetings()
    ]


@router.post("/meetings/upload")
async def upload_meeting_audio(
    title: str | None = Form(default=None),
    file: UploadFile = File(...),
):
    service = get_engram()
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio upload is empty")
    meeting = await service.create_uploaded_meeting(
        title=title or file.filename or "Uploaded recording",
        audio_bytes=audio_bytes,
        original_filename=file.filename,
    )
    return meeting_response(meeting, [])


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str):
    service = get_engram()
    try:
        meeting = service.store.get_meeting(meeting_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    segments = service.store.list_segments(meeting_id)
    data = meeting_response(meeting, segments)
    data["segments"] = [segment_response(segment, meeting.speaker_names) for segment in segments]
    return data


@router.post("/meetings/{meeting_id}/process")
async def process_meeting(meeting_id: str):
    service = get_engram()
    try:
        meeting = service.store.get_meeting(meeting_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.status not in {"ready", "failed"}:
        segments = service.store.list_segments(meeting_id)
        return meeting_response(meeting, segments)
    meeting = service.store.update_meeting(meeting_id, status="processing", error=None)
    asyncio.create_task(service.process_meeting(meeting_id))
    segments = service.store.list_segments(meeting_id)
    return meeting_response(meeting, segments)


@router.put("/meetings/{meeting_id}/speakers")
async def update_meeting_speakers(meeting_id: str, payload: dict[str, Any] = Body(...)):
    service = get_engram()
    speaker_names = payload.get("speaker_names")
    if not isinstance(speaker_names, dict):
        raise HTTPException(status_code=400, detail="speaker_names must be an object")
    try:
        meeting = await service.update_speaker_names(meeting_id, {str(k): str(v) for k, v in speaker_names.items()})
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    segments = service.store.list_segments(meeting_id)
    data = meeting_response(meeting, segments)
    data["segments"] = [segment_response(segment, meeting.speaker_names) for segment in segments]
    return data


@router.post("/meetings/{meeting_id}/finalize")
async def finalize_meeting(meeting_id: str):
    service = get_engram()
    try:
        meeting = await service.finalize_meeting(meeting_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    segments = service.store.list_segments(meeting_id)
    data = meeting_response(meeting, segments)
    data["segments"] = [segment_response(segment, meeting.speaker_names) for segment in segments]
    return data


@router.websocket("/meetings/{meeting_id}/stream")
async def stream_meeting(websocket: WebSocket, meeting_id: str):
    service = get_engram()
    try:
        service.store.get_meeting(meeting_id)
    except FileNotFoundError:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    queue = await service.subscribe(meeting_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        service.unsubscribe(meeting_id, queue)
