"""Persistence boundary for placement blueprints and attempt snapshots."""

from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


BLUEPRINT_ID = "active"


def get_active_blueprint(db: Any) -> dict[str, Any] | None:
    return db.execute(
        "SELECT id, revision, questions, created_at, updated_at "
        "FROM placement_test_blueprints WHERE id = %s",
        (BLUEPRINT_ID,),
    ).fetchone()


def replace_active_blueprint(db: Any, questions: list[dict[str, Any]], now: str) -> dict[str, Any]:
    # The advisory lock serializes the first insert as well as later revisions,
    # so two admins cannot both publish revision 1.
    db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("placement-test-blueprint",))
    current = db.execute(
        "SELECT revision FROM placement_test_blueprints WHERE id = %s FOR UPDATE",
        (BLUEPRINT_ID,),
    ).fetchone()
    revision = int(current["revision"]) + 1 if current else 1
    if current:
        db.execute(
            "UPDATE placement_test_blueprints SET revision = %s, questions = %s, updated_at = %s "
            "WHERE id = %s",
            (revision, Jsonb(questions), now, BLUEPRINT_ID),
        )
    else:
        db.execute(
            "INSERT INTO placement_test_blueprints "
            "(id, revision, questions, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
            (BLUEPRINT_ID, revision, Jsonb(questions), now, now),
        )
    return {
        "id": BLUEPRINT_ID,
        "revision": revision,
        "questions": questions,
        "created_at": current.get("created_at") if current else now,
        "updated_at": now,
    }


def insert_attempt(
    db: Any,
    *,
    attempt_id: str,
    student_id: str,
    blueprint_revision: int,
    question_snapshot: list[dict[str, Any]],
    started_at: str,
) -> None:
    db.execute(
        """
        INSERT INTO placement_test_attempts
            (id, student_id, blueprint_revision, question_snapshot,
             response_snapshot, status, started_at, total_questions,
             created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, 'in_progress', %s, %s, %s, %s)
        """,
        (
            attempt_id,
            student_id,
            blueprint_revision,
            Jsonb(question_snapshot),
            Jsonb([]),
            started_at,
            len(question_snapshot),
            started_at,
            started_at,
        ),
    )


def get_attempt_for_update(db: Any, attempt_id: str, student_id: str) -> dict[str, Any] | None:
    return db.execute(
        "SELECT * FROM placement_test_attempts "
        "WHERE id = %s AND student_id = %s FOR UPDATE",
        (attempt_id, student_id),
    ).fetchone()


def complete_attempt(
    db: Any,
    *,
    attempt_id: str,
    response_snapshot: list[dict[str, Any]],
    completed_at: str,
    correct_count: int,
    total_time_ms: int,
) -> None:
    db.execute(
        """
        UPDATE placement_test_attempts
        SET response_snapshot = %s, status = 'completed', completed_at = %s,
            correct_count = %s, total_time_ms = %s, updated_at = %s
        WHERE id = %s
        """,
        (Jsonb(response_snapshot), completed_at, correct_count, total_time_ms, completed_at, attempt_id),
    )


def list_imported_response_rows(db: Any, resolver_version: str) -> list[dict[str, Any]]:
    """Return the immutable response facts for one admin-visible import batch."""
    return db.execute(
        """
        SELECT
            r.student_id, s.name AS student_name,
            r.quiz_id, r.attempt_id, r.item_id, r.word_id, r.word,
            r.lesson_id, r.question_type, r.selected_answer, r.correct_answer,
            r.correct, r.response_time_ms, r.attempt_order,
            r.quiz_level, r.quiz_mode, r.bkt_eligible,
            r.evidence_origin, r.resolver_version, r.ingested_at,
            a.status AS attempt_status, a.blueprint_revision,
            a.completed_at, a.total_questions, a.correct_count, a.total_time_ms
        FROM vocab_quiz_responses AS r
        JOIN students AS s ON s.id = r.student_id
        LEFT JOIN placement_test_attempts AS a ON a.id = r.attempt_id
        WHERE r.evidence_origin = 'synthetic'
          AND r.resolver_version = %s
          AND r.bkt_eligible = TRUE
        ORDER BY r.student_id, r.attempt_order, r.id
        """,
        (resolver_version,),
    ).fetchall()


def list_imported_mastery_rows(db: Any, resolver_version: str) -> list[dict[str, Any]]:
    """Return mastery projections belonging to the selected import batch."""
    return db.execute(
        """
        SELECT m.student_id, m.word_id, m.p_learned,
               m.observation_count, m.correct_count, m.incorrect_count,
               m.model_version, m.parameter_fingerprint
        FROM student_vocab_mastery AS m
        WHERE EXISTS (
            SELECT 1
            FROM vocab_quiz_responses AS r
            WHERE r.student_id = m.student_id
              AND r.word_id = m.word_id
              AND r.evidence_origin = 'synthetic'
              AND r.resolver_version = %s
              AND r.bkt_eligible = TRUE
        )
        ORDER BY m.student_id, m.word_id
        """,
        (resolver_version,),
    ).fetchall()
