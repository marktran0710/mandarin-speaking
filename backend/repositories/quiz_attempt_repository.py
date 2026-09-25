"""Persistence boundary for the ``vocab_quiz_attempts`` table.

Pure CRUD only - no BKT/SRS decisions and no learner-facing business rules.
Every function takes an already-open connection (``db``) so callers control
the transaction boundary, matching the rest of the codebase's convention of
threading one ``connect_db()`` connection through a request.
"""
from typing import Optional

from psycopg.types.json import Jsonb

from domain.vocabulary.story_scope import story_scope_ids
from repositories.database import row_to_vocab_quiz_attempt


def list_attempts(
    db,
    *,
    story_id: Optional[str] = None,
    student_name: Optional[str] = None,
    student_id: Optional[str] = None,
    include_results: bool = True,
) -> list[dict]:
    columns = (
        "id, story_id, student_id, student_name, mode, completed_at, "
        "total_questions, correct_count, total_time_ms, progression_policy"
    )
    if include_results:
        columns += ", question_results"

    query = f"SELECT {columns} FROM vocab_quiz_attempts WHERE 1=1"
    params: list = []
    if story_id:
        query += " AND story_id = ANY(%s)"
        params.append(story_scope_ids(story_id))
    if student_name:
        query += " AND student_name = %s"
        params.append(student_name)
    if student_id:
        query += " AND student_id = %s"
        params.append(student_id)
    query += " ORDER BY completed_at DESC"

    rows = db.execute(query, params).fetchall()
    return [row_to_vocab_quiz_attempt(row) for row in rows]


def find_attempt_by_id(db, attempt_id: str) -> Optional[dict]:
    """Raw row (not mapped) - callers need the untranslated column names for comparison."""
    return db.execute(
        "SELECT * FROM vocab_quiz_attempts WHERE id = %s",
        (attempt_id,),
    ).fetchone()


def insert_attempt(
    db,
    *,
    id: str,
    story_id: str,
    student_name: str,
    student_id: str,
    mode,
    completed_at,
    total_questions: int,
    correct_count: int,
    total_time_ms: int,
    question_results: list,
    progression_policy: str = "production_accuracy",
    research_study_id: Optional[str] = None,
) -> None:
    db.execute(
        """
        INSERT INTO vocab_quiz_attempts
            (id, story_id, student_name, student_id, mode, completed_at,
             total_questions, correct_count, total_time_ms, question_results,
             progression_policy, research_study_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            id,
            story_id,
            student_name,
            student_id,
            mode,
            completed_at,
            total_questions,
            correct_count,
            total_time_ms,
            Jsonb(question_results),
            progression_policy,
            research_study_id,
        ),
    )
