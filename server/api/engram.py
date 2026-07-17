from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from engram.models import MeetingStatus, SegmentStatus
from engram.pipeline import meeting_response
from server.runtime import get_engram

router = APIRouter()


class EngramSegmentResponse(BaseModel):
    id: int | None
    meeting_id: str
    segment_index: int
    start_seconds: float
    end_seconds: float
    text: str
    speaker: str | None
    display_speaker: str | None
    status: SegmentStatus
    created_at: str | None


class EngramMeetingResponse(BaseModel):
    id: str
    title: str
    status: MeetingStatus
    created_at: str | None
    started_at: str | None
    ended_at: str | None
    duration_seconds: float | None
    audio_path: str | None
    error: str | None
    memory_log_entry_id: str | None
    summary: dict[str, Any] | None
    speaker_names: dict[str, str]
    segment_count: int
    segments: list[EngramSegmentResponse]


class SpeakerNamesUpdate(BaseModel):
    speaker_names: dict[str, str]


class DeleteMeetingResponse(BaseModel):
    deleted: bool
    meeting_id: str


@router.get("/meetings", response_model=list[EngramMeetingResponse])
async def list_meetings():
    service = get_engram()
    return [
        meeting_response(meeting, [])
        for meeting in service.store.list_meetings()
    ]


@router.post("/meetings/upload", response_model=EngramMeetingResponse)
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


@router.get("/meetings/{meeting_id}", response_model=EngramMeetingResponse)
async def get_meeting(meeting_id: str):
    service = get_engram()
    try:
        meeting = service.store.get_meeting(meeting_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    segments = service.store.list_segments(meeting_id)
    return meeting_response(meeting, segments)


@router.post(
    "/meetings/{meeting_id}/process",
    response_model=EngramMeetingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_meeting(meeting_id: str):
    service = get_engram()
    try:
        meeting = service.store.get_meeting(meeting_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.status in {"transcribing", "processing"}:
        segments = service.store.list_segments(meeting_id)
        return meeting_response(meeting, segments)
    if meeting.status not in {"ready", "failed"}:
        raise HTTPException(status_code=409, detail="Meeting is not available for processing")
    meeting = service.store.update_meeting(meeting_id, status="processing", error=None)
    service.start_processing(meeting_id)
    segments = service.store.list_segments(meeting_id)
    return meeting_response(meeting, segments)


@router.delete("/meetings/{meeting_id}", response_model=DeleteMeetingResponse)
async def delete_meeting(meeting_id: str):
    service = get_engram()
    try:
        await service.delete_meeting(meeting_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"deleted": True, "meeting_id": meeting_id}


@router.put("/meetings/{meeting_id}/speakers", response_model=EngramMeetingResponse)
async def update_meeting_speakers(meeting_id: str, payload: SpeakerNamesUpdate):
    service = get_engram()
    try:
        meeting = await service.update_speaker_names(
            meeting_id,
            {str(k): str(v) for k, v in payload.speaker_names.items()},
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Meeting not found")
    segments = service.store.list_segments(meeting_id)
    return meeting_response(meeting, segments)


@router.post("/meetings/{meeting_id}/finalize", response_model=EngramMeetingResponse)
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
    return meeting_response(meeting, segments)
