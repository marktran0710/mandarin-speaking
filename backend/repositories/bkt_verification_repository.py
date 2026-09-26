"""Read-only persistence helpers for the admin BKT verification view."""

from __future__ import annotations

from typing import Any


def list_students(db: Any) -> list[dict[str, Any]]:
    return list(
        db.execute(
            """
            SELECT id, name, created_at, status, is_test_account
            FROM students
            ORDER BY lower(name), id
            """
        ).fetchall()
    )


def get_student(db: Any, student_id: str) -> dict[str, Any] | None:
    return db.execute(
        """
        SELECT id, name, created_at, status, is_test_account
        FROM students
        WHERE id = %s
        """,
        (student_id,),
    ).fetchone()


def list_bkt_response_rows(db: Any, student_id: str) -> list[dict[str, Any]]:
    """Mirror production's eligible response scope, with audit-facing fields."""
    return list(
        db.execute(
            """
            SELECT r.id, r.student_id, r.word_id, r.word, r.lesson_id,
                   r.quiz_id, r.attempt_id, r.item_id, r.question_type,
                   r.selected_answer, r.correct_answer, r.correct,
                   r.response_time_ms, r.occurred_at, r.occurred_at_utc,
                   r.attempt_order, r.quiz_level, r.quiz_mode, r.round_type,
                   r.knowledge_dimension, r.activity_type,
                   r.evidence_origin, r.resolver_version,
                   r.diagnostic_exposure_id, r.bkt_eligible,
                   s.lesson_number AS chapter
            FROM vocab_quiz_responses AS r
            LEFT JOIN custom_stories AS s ON s.id = r.lesson_id
            WHERE r.student_id = %s
              AND (
                (
                  lower(COALESCE(r.quiz_level, '')) IN ('tier1', 'tier2', 'tier3')
                  AND r.quiz_mode IN ('tier1', 'tier2', 'tier3')
                  AND r.bkt_eligible = TRUE
                )
                OR r.quiz_mode IN ('weak_words', 'maintenance_review')
              )
            ORDER BY r.occurred_at_utc ASC NULLS LAST, r.id ASC, r.attempt_order ASC
            """,
            (student_id,),
        ).fetchall()
    )
