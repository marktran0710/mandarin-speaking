"""Persistence boundary for ``learning_measurement_events``.

Pure CRUD only. Every function takes an already-open connection so the
caller controls the transaction boundary.
"""
from psycopg.types.json import Jsonb


def insert_event(
    db,
    *,
    event_id: str,
    schema_version: str,
    name: str,
    occurred_at: str,
    student_id,
    class_id,
    session_id,
    attempt_id,
    topic_id,
    scene_index,
    question_id,
    condition,
    properties: dict,
) -> None:
    db.execute(
        """
        INSERT INTO learning_measurement_events (
            event_id, schema_version, name, occurred_at, student_id, class_id,
            session_id, attempt_id, topic_id, scene_index, question_id,
            condition, properties
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_id) DO NOTHING
        """,
        (
            event_id, schema_version, name, occurred_at, student_id, class_id,
            session_id, attempt_id, topic_id, scene_index, question_id,
            condition, Jsonb(properties),
        ),
    )


def list_events(db, limit: int) -> list[dict]:
    return db.execute(
        "SELECT * FROM learning_measurement_events ORDER BY occurred_at DESC LIMIT %s",
        (limit,),
    ).fetchall()
