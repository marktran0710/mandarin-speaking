"""Locks the migrated schema: table set, the JSONB columns the row_to_*
helpers depend on, and the boolean columns the API wraps in bool()."""
import os

import psycopg
import pytest

TEST_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://mandarin:mandarin@127.0.0.1:5432/mandarin_test"
)

EXPECTED_TABLES = {
    "audio_records",
    "custom_stories",
    "help_requests",
    "story_submissions",
    "students",
    "vocab_quiz_attempts",
}

JSONB_COLUMNS = [
    ("custom_stories", "frames"),
    ("custom_stories", "quiz_exclusions"),
    ("story_submissions", "scenes"),
    ("story_submissions", "story_feedback"),
    ("vocab_quiz_attempts", "question_results"),
    ("audio_records", "praat_metrics"),
]

BOOLEAN_COLUMNS = [
    ("custom_stories", "published"),
    ("custom_stories", "linear"),
    ("custom_stories", "first_frame_is_example"),
]


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(TEST_URL) as connection:
        yield connection


def test_all_tables_exist(conn):
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    names = {row[0] for row in rows}
    assert EXPECTED_TABLES <= names


@pytest.mark.parametrize("table,column", JSONB_COLUMNS)
def test_json_columns_are_jsonb(conn, table, column):
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    assert row is not None, f"{table}.{column} is missing"
    assert row[0] == "jsonb"


@pytest.mark.parametrize("table,column", BOOLEAN_COLUMNS)
def test_flag_columns_are_boolean(conn, table, column):
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    assert row is not None, f"{table}.{column} is missing"
    assert row[0] == "boolean"


def test_created_at_default_matches_sqlite_format(conn):
    """ORDER BY created_at DESC is lexicographic on TEXT — new rows must use
    the same 'YYYY-MM-DD HH:MM:SS' shape as the rows migrated from SQLite."""
    value = conn.execute(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'custom_stories' AND column_name = 'created_at'"
    ).fetchone()[0]
    assert "YYYY-MM-DD HH24:MI:SS" in value
