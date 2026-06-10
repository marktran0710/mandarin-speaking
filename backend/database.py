import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator


DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "mandarin_stories.db"),
)


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
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


def row_to_custom_story(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "learningGoal": row["learning_goal"],
        "level": row["level"],
        "frames": json.loads(row["frames"] or "[]"),
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
