"""Persistence boundary for ``speaking_progress`` and the ``audio_records``
lookups its upsert flow depends on.

Pure CRUD only - the merge/eligibility decision tree lives in
services/speaking_progress_service.py. Every function takes an already-open
connection so the caller controls the transaction boundary (the advisory
lock + reads + write all happen inside one ``connect_db()`` block).
"""
from typing import Any, Optional

from psycopg.types.json import Jsonb


def list_progress(db, student_id: str, topic_id: str) -> list[dict]:
    return db.execute(
        "SELECT * FROM speaking_progress WHERE student_id = %s AND topic_id = %s",
        (student_id, topic_id),
    ).fetchall()


def acquire_progress_lock(db, row_id: str) -> None:
    """Transaction-scoped advisory lock closing the first-insert race for row_id."""
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (row_id,))


def find_progress_for_update(db, row_id: str) -> Optional[dict]:
    return db.execute(
        """
        SELECT attempts, best_tone, best_fluency, mastery_passed,
               content_passed, cleared_words, latest_result,
               verified_audio_record_id
        FROM speaking_progress
        WHERE id = %s
        FOR UPDATE
        """,
        (row_id,),
    ).fetchone()


def find_verified_audio_record_for_update(db, record_id: str) -> Optional[dict]:
    return db.execute(
        """
        SELECT id, student_id, topic_id, image_index, transcription, audio_url,
               image_url, praat_metrics, server_verified_at,
               server_verification_version
        FROM audio_records
        WHERE id = %s
        FOR UPDATE
        """,
        (record_id,),
    ).fetchone()


def find_audio_record_summary(db, record_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT id, server_verified_at FROM audio_records WHERE id = %s",
        (record_id,),
    ).fetchone()


def find_verified_audio_stats(db, student_id: str, topic_id: str, image_index: int) -> list[dict]:
    return db.execute(
        """
        SELECT praat_metrics
        FROM audio_records
        WHERE student_id = %s AND topic_id = %s AND image_index = %s
          AND server_verified_at IS NOT NULL
        """,
        (student_id, topic_id, image_index),
    ).fetchall()


def upsert_progress(
    db,
    *,
    id: str,
    student_id: str,
    topic_id: str,
    scene_index: int,
    attempts: int,
    best_tone: float,
    best_fluency: float,
    mastery_passed: bool,
    content_passed: bool,
    cleared_words: list,
    latest_result: Optional[dict],
    verified_audio_record_id: Optional[str],
    conversation_id: Any,
    turn_id: Any,
    turn_index: Any,
) -> None:
    db.execute(
        """
        INSERT INTO speaking_progress
            (id, student_id, topic_id, scene_index, attempts, best_tone,
             best_fluency, mastery_passed, content_passed, cleared_words,
             latest_result, verified_audio_record_id, conversation_id, turn_id, turn_index)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            attempts = EXCLUDED.attempts,
            best_tone = EXCLUDED.best_tone,
            best_fluency = EXCLUDED.best_fluency,
            mastery_passed = EXCLUDED.mastery_passed,
            content_passed = EXCLUDED.content_passed,
            cleared_words = EXCLUDED.cleared_words,
            latest_result = EXCLUDED.latest_result,
            verified_audio_record_id = EXCLUDED.verified_audio_record_id,
            conversation_id = EXCLUDED.conversation_id,
            turn_id = EXCLUDED.turn_id,
            turn_index = EXCLUDED.turn_index,
            updated_at = to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
        """,
        (
            id,
            student_id,
            topic_id,
            scene_index,
            attempts,
            best_tone,
            best_fluency,
            mastery_passed,
            content_passed,
            Jsonb(cleared_words),
            Jsonb(latest_result) if latest_result is not None else None,
            verified_audio_record_id,
            conversation_id,
            turn_id,
            turn_index,
        ),
    )
