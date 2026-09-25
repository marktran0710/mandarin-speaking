"""Persistence boundary for the ``students`` table and the three-list
student-overview read.

Pure CRUD only - no session/auth decisions and no idempotency/visibility
business rules (those live in services/student_service.py). Every function
takes an already-open connection so the caller controls the transaction
boundary.
"""
from typing import Optional

_OVERVIEW_SUBMISSION_COLUMNS = (
    "id, story_id, story_title, student_name, student_id, submitted_at, "
    "concatenated_audio_url, review_status, teacher_note"
)
_OVERVIEW_ATTEMPT_COLUMNS = (
    "id, story_id, student_name, student_id, mode, completed_at, "
    "total_questions, correct_count, total_time_ms"
)


def fetch_overview(db, student_id: str, audio_limit: int):
    """Batch the student home's three reads over one pipelined round-trip.

    Returns (submission_rows, attempt_rows, audio_rows).
    """
    with db.pipeline():
        submissions_cur = db.execute(
            f"SELECT {_OVERVIEW_SUBMISSION_COLUMNS} FROM story_submissions "
            "WHERE student_id = %s ORDER BY submitted_at DESC",
            (student_id,),
        )
        attempts_cur = db.execute(
            f"SELECT {_OVERVIEW_ATTEMPT_COLUMNS} FROM vocab_quiz_attempts "
            "WHERE student_id = %s ORDER BY completed_at DESC",
            (student_id,),
        )
        audio_cur = db.execute(
            "SELECT * FROM audio_records WHERE student_id = %s "
            "ORDER BY created_at DESC, id DESC LIMIT %s",
            (student_id, audio_limit),
        )
    return submissions_cur.fetchall(), attempts_cur.fetchall(), audio_cur.fetchall()


def find_all(db, exclude_test_accounts: bool) -> list[dict]:
    # Postgres has no COLLATE NOCASE; lower() reproduces SQLite's
    # case-insensitive roster ordering (backed by ix_students_lower_name).
    where = " WHERE NOT is_test_account" if exclude_test_accounts else ""
    return db.execute(f"SELECT * FROM students{where} ORDER BY lower(name)").fetchall()


def find_by_name_ci(db, name: str) -> Optional[dict]:
    return db.execute(
        "SELECT * FROM students WHERE lower(name) = lower(%s)", (name,)
    ).fetchone()


def find_by_id(db, student_id: str) -> Optional[dict]:
    return db.execute("SELECT * FROM students WHERE id = %s", (student_id,)).fetchone()


def insert(db, student_id: str, name: str, password_hash: str) -> dict:
    return db.execute(
        "INSERT INTO students (id, name, password) VALUES (%s, %s, %s) RETURNING *",
        (student_id, name, password_hash),
    ).fetchone()


def update_password_hash(db, student_id: str, password_hash: str) -> None:
    """Silent rehash-on-verify write; no RETURNING, matching prior behavior."""
    db.execute(
        "UPDATE students SET password = %s WHERE id = %s",
        (password_hash, student_id),
    )


def reset_password(db, student_id: str, password_hash: str) -> Optional[dict]:
    return db.execute(
        "UPDATE students SET password = %s, password_reset_required = false "
        "WHERE id = %s RETURNING *",
        (password_hash, student_id),
    ).fetchone()


def find_name_conflict(db, name: str, exclude_student_id: str) -> Optional[dict]:
    return db.execute(
        "SELECT 1 FROM students WHERE lower(name) = lower(%s) AND id <> %s",
        (name, exclude_student_id),
    ).fetchone()


def update_fields(db, student_id: str, set_clauses: list[str], params: list) -> Optional[dict]:
    query_params = [*params, student_id]
    return db.execute(
        f"UPDATE students SET {', '.join(set_clauses)} WHERE id = %s RETURNING *",
        tuple(query_params),
    ).fetchone()
