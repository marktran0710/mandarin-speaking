import security.auth as auth
import services.speaking_progress_service as speaking_progress_service
from db import connect_db
from main import SpeakingProgressRequest
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter()


@router.get("/api/speaking-progress")
def list_speaking_progress(
    topic_id: str,
    identity: auth.Identity = Depends(auth.require_student),
):
    with connect_db() as db:
        return speaking_progress_service.list_progress(db, identity.id, topic_id)


@router.put("/api/speaking-progress")
async def upsert_speaking_progress(
    progress: SpeakingProgressRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    with connect_db() as db:
        try:
            speaking_progress_service.record_progress(db, progress, identity.id)
        except speaking_progress_service.SpeakingProgressError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return progress
