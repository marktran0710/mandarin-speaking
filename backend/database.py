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
                level TEXT NOT NULL,
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
        "level": row["level"],
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
