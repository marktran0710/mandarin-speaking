from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from database import connect_db
import auth

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


def _row_to_event(row: dict) -> dict:
    return {
        "eventId": row["event_id"], "schemaVersion": row["schema_version"],
        "name": row["name"], "occurredAt": row["occurred_at"],
        "studentId": row.get("student_id"), "classId": row.get("class_id"),
        "sessionId": row.get("session_id"), "attemptId": row.get("attempt_id"),
        "topicId": row.get("topic_id"), "sceneIndex": row.get("scene_index"),
        "questionId": row.get("question_id"), "condition": row.get("condition"),
        "properties": row.get("properties") or {},
    }


@router.post("/api/measurement-events", status_code=202)
async def record_measurement_event(
    event: MeasurementEventRequest,
    identity: auth.Identity = Depends(auth.require_student),
):
    # Never trust a client-supplied student id for analytics attribution.
    event.studentId = identity.id
    with connect_db() as db:
        db.execute(
            """
            INSERT INTO learning_measurement_events (
                event_id, schema_version, name, occurred_at, student_id, class_id,
                session_id, attempt_id, topic_id, scene_index, question_id,
                condition, properties
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            """,
            (event.eventId, event.schemaVersion, event.name, event.occurredAt,
             event.studentId, event.classId, event.sessionId, event.attemptId,
             event.topicId, event.sceneIndex, event.questionId, event.condition,
             Jsonb(event.properties)),
        )
    return {"eventId": event.eventId, "stored": True}


@router.get("/api/measurement-events")
async def list_measurement_events(
    limit: int = Query(default=2000, ge=1, le=10000),
    identity: auth.Identity = Depends(auth.require_teacher_or_admin),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM learning_measurement_events ORDER BY occurred_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [_row_to_event(row) for row in rows]
