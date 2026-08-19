"""Research-pilot ingestion, split out from the classroom-facing
`routers/audio.py` so that JWT-authenticated student identity can be
enforced there without breaking the pilot harness.

The small-teacher-validated-pilot architecture
(`benchmarking/results/pilot_teacher_validation_integration.md`) posts audio
records directly with a pseudonymous `participant_id` (as `studentId`) and
never logs in through the student/teacher roster at all - see the provenance
note in `routers/teacher_review.py`. This endpoint is exactly the old,
unauthenticated `POST /api/audio-records` behavior, kept only for that
harness; real classroom traffic goes through the authenticated endpoint in
`routers/audio.py` instead.
"""
from fastapi import APIRouter

import main
from main import AudioRecordRequest

router = APIRouter()


@router.post("/api/pilot/audio-records")
async def create_pilot_audio_record(record: AudioRecordRequest):
    main.save_audio_record(record)
    return record
