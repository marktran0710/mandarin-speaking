"""Persistence boundary for the ``story_submissions`` table.

Pure CRUD only - the visibility-filter and scene/feedback orchestration
decisions live in services/submission_service.py. Every function takes an
already-open connection so the caller controls the transaction boundary.
"""
from typing import Optional

from psycopg.types.json import Jsonb


def find_submissions(
    db,
    *,
    exclude_test_accounts: bool,
    story_id: Optional[str],
    student_id: Optional[str],
    student_name: Optional[str],
    include_scenes: bool,
) -> list[dict]:
    conditions = []
    params: list = []
    if exclude_test_accounts:
        # Test/synthetic accounts are dev/QA fixtures; a teacher's queue must
        # never mix them with real submissions. Admin tooling still sees all.
        conditions.append("student_id NOT IN (SELECT id FROM students WHERE is_test_account)")
    if story_id:
        conditions.append("story_id = %s")
        params.append(story_id)
    if student_id:
        conditions.append("student_id = %s")
        params.append(student_id)
    elif student_name:
        conditions.append("student_name = %s")
        params.append(student_name)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    # The per-scene `scenes` JSONB (each scene's transcription, tone metrics and
    # audio) is the heavy part of a submission. The teacher dashboard's roster
    # and pending-count views read only the summary, so they can pass
    # include_scenes=false and skip it; the review view keeps the full payload.
    # Also replaces the endpoint's `SELECT *`.
    columns = (
        "id, story_id, story_title, student_name, student_id, submitted_at, "
        "concatenated_audio_url, story_feedback, review_status, teacher_note, "
        "practice_path, quiz_scores, submission_count"
    )
    if include_scenes:
        columns += ", scenes"

    return db.execute(
        f"SELECT {columns} FROM story_submissions{where} ORDER BY submitted_at DESC",
        params,
    ).fetchall()


def update_review(db, submission_id: str, status: str, note) -> Optional[dict]:
    return db.execute(
        """
        UPDATE story_submissions
        SET review_status = %s, teacher_note = %s
        WHERE id = %s
        RETURNING *
        """,
        (status, note, submission_id),
    ).fetchone()


def find_latest_for_student_story(db, student_id: str, story_id: str) -> Optional[dict]:
    """The student's existing submission for this lesson (newest first, so
    historical duplicates from before one-per-lesson resolve to the latest)."""
    return db.execute(
        """
        SELECT id, submission_count
        FROM story_submissions
        WHERE student_id = %s AND story_id = %s
        ORDER BY submitted_at DESC
        LIMIT 1
        """,
        (student_id, story_id),
    ).fetchone()


def find_owner(db, submission_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT student_id FROM story_submissions WHERE id = %s",
        (submission_id,),
    ).fetchone()


def upsert_scenes(
    db,
    *,
    id: str,
    story_id: str,
    story_title: str,
    student_name: str,
    student_id: str,
    submitted_at,
    scenes: list,
    practice_path: Optional[str] = None,
    quiz_scores: Optional[dict] = None,
    submission_count: int = 1,
) -> None:
    # A resubmission replaces the work, so it goes back to the teacher's
    # queue: review_status resets to pending (the previous teacher_note is
    # kept for the teacher's reference).
    db.execute(
        """
        INSERT INTO story_submissions
            (id, story_id, story_title, student_name, student_id, submitted_at, scenes,
             practice_path, quiz_scores, submission_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            story_id = EXCLUDED.story_id,
            story_title = EXCLUDED.story_title,
            student_name = EXCLUDED.student_name,
            student_id = EXCLUDED.student_id,
            submitted_at = EXCLUDED.submitted_at,
            scenes = EXCLUDED.scenes,
            practice_path = EXCLUDED.practice_path,
            quiz_scores = EXCLUDED.quiz_scores,
            submission_count = EXCLUDED.submission_count,
            review_status = 'pending'
        """,
        (
            id, story_id, story_title, student_name, student_id, submitted_at, Jsonb(scenes),
            practice_path, Jsonb(quiz_scores) if quiz_scores is not None else None, submission_count,
        ),
    )


def update_story_extras(
    db, submission_id: str, concatenated_audio_url: Optional[str], story_feedback: Optional[dict]
) -> Optional[dict]:
    return db.execute(
        """
        UPDATE story_submissions
        SET concatenated_audio_url = %s, story_feedback = %s
        WHERE id = %s
        RETURNING *
        """,
        (
            concatenated_audio_url,
            Jsonb(story_feedback) if story_feedback else None,
            submission_id,
        ),
    ).fetchone()
