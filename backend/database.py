import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
)

_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
_DB_TIMEOUT = float(os.getenv("DB_TIMEOUT_SECONDS", "10"))

# open=False so importing this module never blocks on a database that isn't
# up yet — init_db() opens it at FastAPI startup, and tests re-point it at
# the test database before opening.
_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=_POOL_MIN,
            max_size=_POOL_MAX,
            timeout=_DB_TIMEOUT,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        _pool.open()
    return _pool


@contextmanager
def connect_db() -> Iterator[psycopg.Connection]:
    """Hands out a pooled connection inside a transaction.

    psycopg3's Connection.execute() creates a cursor and runs the statement,
    so call sites keep the `db.execute(sql, params).fetchall()` shape they
    had under sqlite3. The pool's context manager commits on a clean exit and
    rolls back if the body raises.
    """
    with _get_pool().connection() as connection:
        yield connection


def init_db() -> None:
    """Opens the pool and fails loudly if the database is unreachable.

    Schema creation lives in Alembic (`python -m alembic upgrade head`) —
    this function no longer creates or alters tables.
    """
    with connect_db() as db:
        db.execute("SELECT 1").fetchone()


def close_db() -> None:
    """Closes the pool on application shutdown."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def reset_pool_for_tests(database_url: str) -> None:
    """Re-points the pool at another database (the pytest database).

    Tests must never share a connection pool with the development database —
    the suite truncates every table between tests.
    """
    global DATABASE_URL
    close_db()
    DATABASE_URL = database_url


def row_to_audio_record(row: dict) -> dict:
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "duration": row["duration"],
        "transcription": row["transcription"],
        "model": row["model"],
        "topicId": row["topic_id"],
        "imageUrl": row["image_url"],
        "imageIndex": row["image_index"],
        "audioUrl": row["audio_url"],
        # JSONB: psycopg already parsed this.
        "praatMetrics": row["praat_metrics"],
    }


def row_to_story_submission(row: dict) -> dict:
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "storyTitle": row["story_title"],
        "studentName": row["student_name"],
        "studentId": row.get("student_id"),
        "submittedAt": row["submitted_at"],
        "scenes": row["scenes"] or [],
        "concatenatedAudioUrl": row.get("concatenated_audio_url"),
        "storyFeedback": row.get("story_feedback"),
    }


def row_to_custom_story(row: dict) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "learningGoal": row["learning_goal"],
        "frames": row["frames"] or [],
        "published": bool(row["published"]),
        "linear": bool(row["linear"]),
        "lessonNumber": row["lesson_number"],
        "lessonSubOrder": row.get("lesson_sub_order"),
        "narrativeMode": row["narrative_mode"],
        "firstFrameIsExample": bool(row["first_frame_is_example"]),
        "quizExclusions": row.get("quiz_exclusions") or [],
        "quizMaterialSnapshot": row.get("quiz_material_snapshot"),
        "quizApprovedSnapshot": row.get("quiz_approved_snapshot"),
        "quizPendingApprovals": row.get("quiz_pending_approvals"),
    }


def row_to_help_request(row: dict) -> dict:
    return {
        "id": row["id"],
        "studentName": row["student_name"],
        "message": row["message"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "resolvedAt": row["resolved_at"],
    }


def row_to_vocab_quiz_attempt(row: dict) -> dict:
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "studentName": row["student_name"],
        "studentId": row.get("student_id"),
        "mode": row.get("mode"),
        "completedAt": row["completed_at"],
        "totalQuestions": row["total_questions"],
        "correctCount": row["correct_count"],
        "totalTimeMs": row["total_time_ms"],
        "questionResults": row["question_results"] or [],
    }


def row_to_student(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "createdAt": row["created_at"],
    }
