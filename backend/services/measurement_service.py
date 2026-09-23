"""Use-case orchestration for learning-measurement event ingestion/listing."""
from repositories import measurement_repository as repo


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


def record_event(db, event) -> dict:
    """Persist ``event`` (a MeasurementEventRequest with studentId already
    stamped by the router) and return its client-facing acknowledgement."""
    repo.insert_event(
        db,
        event_id=event.eventId,
        schema_version=event.schemaVersion,
        name=event.name,
        occurred_at=event.occurredAt,
        student_id=event.studentId,
        class_id=event.classId,
        session_id=event.sessionId,
        attempt_id=event.attemptId,
        topic_id=event.topicId,
        scene_index=event.sceneIndex,
        question_id=event.questionId,
        condition=event.condition,
        properties=event.properties,
    )
    return {"eventId": event.eventId, "stored": True}


def list_events(db, limit: int) -> list[dict]:
    return [_row_to_event(row) for row in repo.list_events(db, limit)]
