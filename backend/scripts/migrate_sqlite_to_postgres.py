"""One-shot copy of the legacy SQLite database into PostgreSQL.

Usage (from backend/):
    python -m scripts.migrate_sqlite_to_postgres
    python -m scripts.migrate_sqlite_to_postgres --sqlite mandarin_stories.db

Safe to re-run: every table upserts on its primary key, so a partial run can
just be repeated. The SQLite file is only ever read.
"""
import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psycopg.types.json import Jsonb  # noqa: E402

from database import connect_db  # noqa: E402

DEFAULT_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mandarin_stories.db"
)

# table -> (columns, json columns, boolean columns)
TABLES = {
    "custom_stories": (
        ["id", "title", "learning_goal", "frames", "published", "created_at",
         "linear", "lesson_number", "narrative_mode", "first_frame_is_example",
         "quiz_exclusions"],
        {"frames", "quiz_exclusions"},
        {"published", "linear", "first_frame_is_example"},
    ),
    "audio_records": (
        ["id", "timestamp", "duration", "transcription", "model", "topic_id",
         "image_url", "image_index", "audio_url", "praat_metrics", "created_at"],
        {"praat_metrics"},
        set(),
    ),
    "help_requests": (
        ["id", "student_name", "message", "status", "created_at", "resolved_at"],
        set(),
        set(),
    ),
    "story_submissions": (
        ["id", "story_id", "story_title", "student_name", "submitted_at", "scenes",
         "created_at", "concatenated_audio_url", "story_feedback"],
        {"scenes", "story_feedback"},
        set(),
    ),
    "vocab_quiz_attempts": (
        ["id", "story_id", "student_name", "completed_at", "total_questions",
         "correct_count", "total_time_ms", "question_results", "created_at",
         "mode", "student_id"],
        {"question_results"},
        set(),
    ),
    "students": (
        ["id", "name", "created_at", "password"],
        set(),
        set(),
    ),
}


def _convert(column: str, value, json_columns: set, bool_columns: set):
    if column in json_columns:
        if value in (None, ""):
            return None
        try:
            return Jsonb(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            # A row whose JSON never parsed under SQLite either — keep the
            # raw text so nothing is silently dropped, wrapped as a JSON
            # string so the column type still accepts it.
            return Jsonb(value)
    if column in bool_columns:
        return bool(value)
    return value


def migrate_table(sqlite_conn: sqlite3.Connection, table: str) -> int:
    columns, json_columns, bool_columns = TABLES[table]
    available = {row[1] for row in sqlite_conn.execute(f"PRAGMA table_info({table})")}
    if not available:
        print(f"  {table}: not present in the SQLite file, skipped")
        return 0
    columns = [c for c in columns if c in available]

    rows = sqlite_conn.execute(
        f"SELECT {', '.join(columns)} FROM {table}"
    ).fetchall()
    if not rows:
        return 0

    placeholders = ", ".join(["%s"] * len(columns))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != "id")
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT (id) DO UPDATE SET {updates}"
    )

    with connect_db() as db:
        for row in rows:
            db.execute(
                sql,
                tuple(
                    _convert(column, row[index], json_columns, bool_columns)
                    for index, column in enumerate(columns)
                ),
            )
    return len(rows)


def migrate_all(sqlite_path: str = DEFAULT_SQLITE_PATH) -> dict:
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"No SQLite database at {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    try:
        # students first: nothing enforces it today, but copying the roster
        # before the rows that reference student_id keeps the data sensible
        # if a foreign key is ever added.
        order = ["students", "custom_stories", "audio_records", "help_requests",
                 "story_submissions", "vocab_quiz_attempts"]
        counts = {}
        for table in order:
            counts[table] = migrate_table(sqlite_conn, table)
            print(f"  {table}: {counts[table]} rows")
        return counts
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default=DEFAULT_SQLITE_PATH)
    args = parser.parse_args()
    print(f"Migrating {args.sqlite} -> PostgreSQL")
    counts = migrate_all(args.sqlite)
    print(f"Done. {sum(counts.values())} rows copied.")
