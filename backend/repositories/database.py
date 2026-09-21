import hashlib
import json
import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# This module reads DATABASE_URL at import time (below), and scripts/tests
# may import it directly without going through main.py first - so without
# loading here too, any DATABASE_URL/DB_POOL_*/DB_TIMEOUT_SECONDS override in
# .env could be silently ignored and the hardcoded default below wins
# instead. Mirrors the same self-contained load_dotenv() pattern
# services/ai_feedback.py already uses for its own module-level API key reads.
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin"
)

# Postgres' own default max_connections is 100; a pool of 32 leaves plenty
# of headroom for psql/pg_dump/other tools while still covering a burst of
# ~50 students, since each connection is only held for the duration of one
# query (connect_db()'s `with` block), not the whole request - the CPU-bound
# Praat/ASR work happens outside it. min=2 avoids a cold-open on the first
# couple of concurrent requests after the pool has been idle.
#
# The DB-backed route handlers are plain `def`, so Starlette runs each in a
# worker thread; the pool must therefore be able to serve as many concurrent
# queries as there are worker threads (see the thread-limiter alignment in
# main's startup) or those threads queue on connection checkout.
_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "32"))
_DB_TIMEOUT = float(os.getenv("DB_TIMEOUT_SECONDS", "10"))


def pool_max_size() -> int:
    """Configured max pool size, so the app can size its thread limiter to match."""
    return _POOL_MAX

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
        "studentId": row["student_id"],
        "imageUrl": row["image_url"],
        "imageIndex": row["image_index"],
        "audioUrl": row["audio_url"],
        "audioName": row.get("audio_name"),
        # JSONB: psycopg already parsed this.
        "praatMetrics": row["praat_metrics"],
        "sessionId": row.get("session_id"),
        "attemptId": row.get("attempt_id"),
        "attemptNumber": row.get("attempt_number"),
        "attemptType": row.get("attempt_type"),
        "serverVerifiedAt": row.get("server_verified_at"),
        "audioSha256": row.get("audio_sha256"),
        "serverVerificationVersion": row.get("server_verification_version"),
    }


def row_to_story_submission(row: dict) -> dict:
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "storyTitle": row["story_title"],
        "studentName": row["student_name"],
        "studentId": row.get("student_id"),
        "submittedAt": row["submitted_at"],
        # `.get`: a lightweight list query may omit scenes (see
        # list_story_submissions' include_scenes=false path).
        "scenes": row.get("scenes") or [],
        "concatenatedAudioUrl": row.get("concatenated_audio_url"),
        "storyFeedback": row.get("story_feedback"),
        "reviewStatus": row.get("review_status") or "pending",
        "teacherNote": row.get("teacher_note"),
    }


def row_to_custom_story(row: dict) -> dict:
    vocab_assessment = row.get("vocab_assessment")
    return {
        "id": row["id"],
        "title": row["title"],
        "frames": row["frames"] or [],
        "storyVocabulary": row.get("story_vocabulary"),
        "storyPhrases": row.get("story_phrases"),
        "vocabAssessment": vocab_assessment,
        "vocabAssessmentRevision": vocab_assessment_revision(vocab_assessment),
        "published": bool(row["published"]),
        "lessonNumber": row["lesson_number"],
        "lessonSubOrder": row.get("lesson_sub_order"),
        "quizExclusions": row.get("quiz_exclusions") or [],
        "quizMaterialSnapshot": row.get("quiz_material_snapshot"),
        "quizApprovedSnapshot": row.get("quiz_approved_snapshot"),
        "quizPendingApprovals": row.get("quiz_pending_approvals"),
        "rubricScores": row.get("rubric_scores"),
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
    # `.get`, not `[...]`: a lightweight list query may omit question_results
    # entirely (see list_vocab_quiz_attempts' include_results=false path).
    question_results = row.get("question_results") or []
    first_result = question_results[0] if question_results else {}
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
        "questionResults": question_results,
        # Attempt-level fields are derived from the first new-format item;
        # legacy rows simply omit them.
        **({"baseStoryId": first_result["baseStoryId"]} if first_result.get("baseStoryId") else {}),
        **({"level": first_result["level"]} if first_result.get("level") else {}),
    }


def vocab_assessment_revision(value: object) -> str | None:
    """Return a deterministic revision for optimistic quiz-bank edits."""
    if not isinstance(value, list):
        return None
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def row_to_speaking_progress(row: dict) -> dict:
    return {
        "studentId": row["student_id"],
        "topicId": row["topic_id"],
        "sceneIndex": row["scene_index"],
        "attempts": row["attempts"],
        "bestTone": row["best_tone"],
        "bestFluency": row["best_fluency"],
        "masteryPassed": row["mastery_passed"],
        "contentPassed": row["content_passed"],
        "clearedWords": row["cleared_words"] or [],
        "latestResult": row.get("latest_result"),
        "verifiedAudioRecordId": row.get("verified_audio_record_id"),
        "progressionEligible": bool(row.get("verified_audio_record_id")),
        "updatedAt": row["updated_at"],
    }


def row_to_student(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "createdAt": row["created_at"],
        "status": row.get("status") or "active",
        "isTestAccount": bool(row.get("is_test_account")),
    }


# Every table keyed by student_id, i.e. everything a deleted student's account
# must not leave behind. There is no DB-level FK/cascade for these (students
# rows predate most of them), so a student delete has to walk this list itself.
STUDENT_OWNED_TABLES = (
    "audio_records",
    "bkt_model_student_folds",
    "learning_measurement_events",
    "speaking_progress",
    "story_submissions",
    "student_vocab_mastery",
    "student_vocab_srs",
    "student_vocab_srs_events",
    "vocab_quiz_attempts",
    "vocab_quiz_responses",
)


def delete_student_cascade(db, student_id: str) -> bool:
    """Delete a student and every row owned by them, in one transaction.

    Returns False (nothing deleted, nothing else touched) if the student
    doesn't exist, so callers can 404 instead of reporting a false success.
    """
    for table in STUDENT_OWNED_TABLES:
        db.execute(f"DELETE FROM {table} WHERE student_id = %s", (student_id,))  # noqa: S608 (table from a fixed internal tuple, not user input)
    row = db.execute("DELETE FROM students WHERE id = %s RETURNING id", (student_id,)).fetchone()
    return row is not None


def row_to_teacher(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"], "createdAt": row["created_at"], "status": row["status"]}
