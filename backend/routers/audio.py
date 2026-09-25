from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

import security.auth as auth
from db import connect_db
from repositories import audio_record_repository as repo
import services.media as media_service
from services.media import AudioRecordRequest

router = APIRouter()


@router.get("/api/audio-records")
def list_audio_records(
    limit: int = Query(default=200, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
    student_id: Optional[str] = Query(default=None),
    topic_id: Optional[str] = Query(default=None),
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    # A student can only ever browse their own records - a client-supplied
    # student_id is ignored for that role. Teachers/admin keep the filter
    # (or none, to browse everyone) since that's the whole point of the
    # teacher dashboard's "all recent records" view.
    if identity.role == "student":
        student_id = identity.id

    with connect_db() as db:
        return repo.list_records(db, limit=limit, skip=skip, student_id=student_id, topic_id=topic_id)


@router.get("/api/audio-records/count")
def get_audio_record_count(
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        total = repo.count_records(db)
    return {"total": total}


@router.post("/api/audio-records")
def create_audio_record(
    record: AudioRecordRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    record.studentId = identity.id
    media_service.save_audio_record(record, owner_id=identity.id)
    return record


@router.post("/api/audio-records/upload")
async def upload_audio_record(
    record: str = Form(...),
    file: UploadFile = File(...),
    identity: auth.Identity = Depends(auth.require_student),
):
    try:
        audio_record = AudioRecordRequest.model_validate_json(record)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid audio record JSON") from exc

    audio_record.studentId = identity.id
    with connect_db() as db:
        existing = repo.find_owner(db, audio_record.id)
    if existing is not None and existing.get("student_id") != identity.id:
        raise HTTPException(status_code=409, detail="Audio record already belongs to another student.")
    audio_record.audioUrl = await media_service.save_uploaded_audio(file, audio_record.id, identity.id)
    audio_record.audioName = audio_record.audioUrl.rsplit("/", 1)[-1]
    media_service.save_audio_record(audio_record, owner_id=identity.id)
    return audio_record


@router.delete("/api/audio-records/{record_id}")
def delete_audio_record(
    record_id: str,
    identity: auth.Identity = Depends(auth.require_admin),
):
    with connect_db() as db:
        row = repo.delete_record(db, record_id)
    if row and row["audio_url"]:
        media_service.remove_uploaded_file(row["audio_url"])
    return {"ok": True}
