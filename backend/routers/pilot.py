"""Authenticated audio-record ingestion used by teacher review.

The classroom-facing audio route remains in ``routers.audio``. This small
compatibility endpoint accepts the same record shape for teacher-review flows
without exposing any benchmark or research scoring surface.
"""

from fastapi import APIRouter, Depends

import auth
import main
from main import AudioRecordRequest

router = APIRouter(dependencies=[Depends(auth.require_teacher_or_admin)])


@router.post("/api/pilot/audio-records")
def create_pilot_audio_record(record: AudioRecordRequest):
    main.save_audio_record(record)
    return record
