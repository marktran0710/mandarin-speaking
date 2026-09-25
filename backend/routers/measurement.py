from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

import security.auth as auth
import services.measurement_service as measurement_service
from db import connect_db

router = APIRouter()


class MeasurementEventRequest(BaseModel):
    eventId: str = Field(..., min_length=1, max_length=160)
    schemaVersion: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=80)
    occurredAt: str = Field(..., min_length=1, max_length=80)
    studentId: Optional[str] = None
    classId: Optional[str] = None
    sessionId: Optional[str] = None
    attemptId: Optional[str] = None
    topicId: Optional[str] = None
    sceneIndex: Optional[int] = None
    questionId: Optional[str] = None
    condition: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)


@router.post("/api/measurement-events", status_code=202)
def record_measurement_event(
    event: MeasurementEventRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    # Never trust a client-supplied student id for analytics attribution.
    event.studentId = identity.id
    with connect_db() as db:
        return measurement_service.record_event(db, event)


@router.get("/api/measurement-events")
def list_measurement_events(
    limit: int = Query(default=2000, ge=1, le=10000),
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        return measurement_service.list_events(db, limit)
