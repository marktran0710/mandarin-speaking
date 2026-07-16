import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "mandarin_stories.db"),
)

_DB_TIMEOUT = float(os.getenv("DB_TIMEOUT_SECONDS", "10"))


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=_DB_TIMEOUT, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    # WAL mode: readers don't block writers and vice-versa.
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA cache_size=-8000")   # 8 MB page cache
    connection.execute("PRAGMA synchronous=NORMAL")  # safe with WAL
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    database_dir = os.path.dirname(DATABASE_PATH)
    if database_dir:
        os.makedirs(database_dir, exist_ok=True)
    with connect_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS audio_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                duration INTEGER NOT NULL,
                transcription TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL,
                topic_id TEXT,
                image_url TEXT,
                image_index INTEGER,
                audio_url TEXT,
                praat_metrics TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(db, "audio_records", "audio_url", "TEXT")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_stories (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                learning_goal TEXT NOT NULL,
                frames TEXT NOT NULL,
                published INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(db, "custom_stories", "published", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "custom_stories", "linear", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(db, "custom_stories", "lesson_number", "INTEGER")
        ensure_column(db, "custom_stories", "narrative_mode", "TEXT NOT NULL DEFAULT 'story'")
        ensure_column(db, "custom_stories", "first_frame_is_example", "INTEGER NOT NULL DEFAULT 0")
        # Superseded by the per-frame easy/medium/hard difficulty tiers —
        # a single free-text "level" description no longer means anything.
        ensure_column_dropped(db, "custom_stories", "level")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS help_requests (
                id TEXT PRIMARY KEY,
                student_name TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                resolved_at TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS story_submissions (
                id TEXT PRIMARY KEY,
                story_id TEXT NOT NULL,
                story_title TEXT NOT NULL,
                student_name TEXT NOT NULL,
                submitted_at TEXT NOT NULL,
                scenes TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(db, "story_submissions", "concatenated_audio_url", "TEXT")
        ensure_column(db, "story_submissions", "story_feedback", "TEXT")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS vocab_quiz_attempts (
                id TEXT PRIMARY KEY,
                story_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                total_questions INTEGER NOT NULL,
                correct_count INTEGER NOT NULL,
                total_time_ms INTEGER NOT NULL,
                question_results TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        ensure_column(db, "vocab_quiz_attempts", "mode", "TEXT")
        # Nullable: legacy attempts recorded before the roster existed only
        # have student_name (a free-typed string, prone to collisions/typos)
        # and stay that way — new attempts carry the stable roster id
        # alongside it so per-student analysis (IRT, FREX) has a real join
        # key instead of matching on name text.
        ensure_column(db, "vocab_quiz_attempts", "student_id", "TEXT")

        db.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def row_to_audio_record(row: sqlite3.Row) -> dict:
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
        "praatMetrics": json.loads(row["praat_metrics"] or "null"),
    }


def row_to_story_submission(row: sqlite3.Row) -> dict:
    row_keys = row.keys()
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "storyTitle": row["story_title"],
        "studentName": row["student_name"],
        "submittedAt": row["submitted_at"],
        "scenes": json.loads(row["scenes"] or "[]"),
        "concatenatedAudioUrl": row["concatenated_audio_url"] if "concatenated_audio_url" in row_keys else None,
        "storyFeedback": (
            json.loads(row["story_feedback"])
            if ("story_feedback" in row_keys and row["story_feedback"])
            else None
        ),
    }


def row_to_custom_story(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "learningGoal": row["learning_goal"],
        "frames": json.loads(row["frames"] or "[]"),
        "published": bool(row["published"]),
        "linear": bool(row["linear"]),
        "lessonNumber": row["lesson_number"],
        "narrativeMode": row["narrative_mode"],
        "firstFrameIsExample": bool(row["first_frame_is_example"]),
    }


def row_to_help_request(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "studentName": row["student_name"],
        "message": row["message"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "resolvedAt": row["resolved_at"],
    }


def row_to_vocab_quiz_attempt(row: sqlite3.Row) -> dict:
    row_keys = row.keys()
    return {
        "id": row["id"],
        "storyId": row["story_id"],
        "studentName": row["student_name"],
        "studentId": row["student_id"] if "student_id" in row_keys else None,
        "mode": row["mode"] if "mode" in row_keys else None,
        "completedAt": row["completed_at"],
        "totalQuestions": row["total_questions"],
        "correctCount": row["correct_count"],
        "totalTimeMs": row["total_time_ms"],
        "questionResults": json.loads(row["question_results"] or "[]"),
    }


def row_to_student(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "createdAt": row["created_at"],
    }


def ensure_column(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    columns = {
        row["name"]
        for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def ensure_column_dropped(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
) -> None:
    """Mirrors ensure_column for the opposite direction — drops a retired
    column if it's still there (SQLite 3.35+ supports DROP COLUMN
    directly), a no-op on a fresh DB that never had it."""
    columns = {
        row["name"]
        for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in columns:
        db.execute(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
