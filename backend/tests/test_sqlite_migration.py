"""Verifies the one-shot SQLite -> PostgreSQL copy: TEXT JSON becomes real
JSONB, 0/1 flags become booleans, and Chinese text survives the round trip."""
import json
import sqlite3

import pytest

from database import connect_db
from scripts.migrate_sqlite_to_postgres import migrate_all


@pytest.fixture()
def legacy_db(tmp_path):
    """A miniature copy of the old SQLite schema with one row per table."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE custom_stories (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, learning_goal TEXT NOT NULL,
            frames TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            linear INTEGER NOT NULL DEFAULT 0, lesson_number INTEGER,
            narrative_mode TEXT NOT NULL DEFAULT 'story',
            first_frame_is_example INTEGER NOT NULL DEFAULT 0,
            quiz_exclusions TEXT);
        CREATE TABLE audio_records (
            id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, duration INTEGER NOT NULL,
            transcription TEXT NOT NULL DEFAULT '', model TEXT NOT NULL, topic_id TEXT, student_id TEXT,
            image_url TEXT, image_index INTEGER, audio_url TEXT, praat_metrics TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE help_requests (
            id TEXT PRIMARY KEY, student_name TEXT NOT NULL, message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL, resolved_at TEXT);
        CREATE TABLE story_submissions (
            id TEXT PRIMARY KEY, story_id TEXT NOT NULL, story_title TEXT NOT NULL,
            student_name TEXT NOT NULL, submitted_at TEXT NOT NULL, scenes TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            concatenated_audio_url TEXT, story_feedback TEXT);
        CREATE TABLE vocab_quiz_attempts (
            id TEXT PRIMARY KEY, story_id TEXT NOT NULL, student_name TEXT NOT NULL,
            completed_at TEXT NOT NULL, total_questions INTEGER NOT NULL,
            correct_count INTEGER NOT NULL, total_time_ms INTEGER NOT NULL,
            question_results TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, mode TEXT, student_id TEXT);
        CREATE TABLE students (
            id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            password TEXT NOT NULL DEFAULT '123456');
        """
    )
    frames = json.dumps(
        [{"prompt": "這是我的房間。", "vocabulary": "房間",
          "vocabularyDistractors": json.dumps([["廚房", "客廳"]])}],
        ensure_ascii=False,
    )
    conn.execute(
        "INSERT INTO custom_stories (id, title, learning_goal, frames, published, "
        "created_at, linear, lesson_number, narrative_mode, first_frame_is_example, quiz_exclusions) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("s1", "我的房間", "describe a room", frames, 1,
         "2026-07-20 10:00:00", 0, 5, "story", 0,
         json.dumps([{"word": "房間", "kind": "cloze"}], ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO students (id, name, created_at, password) VALUES (?,?,?,?)",
        ("stu-1", "Mai", "2026-07-20 10:00:00", "123456"),
    )
    conn.execute(
        "INSERT INTO vocab_quiz_attempts (id, story_id, student_name, completed_at, "
        "total_questions, correct_count, total_time_ms, question_results, created_at, mode, student_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("a1", "teacher-s1", "Mai", "2026-07-21T09:00:00Z", 10, 8, 42000,
         json.dumps([{"word": "房間", "correct": True, "timeMs": 1200}], ensure_ascii=False),
         "2026-07-21 09:00:00", "tier2", "stu-1"),
    )
    conn.commit()
    conn.close()
    return str(path)


def test_migrate_all_copies_every_table(legacy_db):
    counts = migrate_all(legacy_db)
    assert counts["custom_stories"] == 1
    assert counts["students"] == 1
    assert counts["vocab_quiz_attempts"] == 1


def test_json_text_becomes_queryable_jsonb(legacy_db):
    migrate_all(legacy_db)
    with connect_db() as db:
        row = db.execute(
            "SELECT frames -> 0 ->> 'prompt' AS prompt, "
            "       jsonb_array_length(frames) AS n "
            "FROM custom_stories WHERE id = %s",
            ("s1",),
        ).fetchone()
    assert row["prompt"] == "這是我的房間。"
    assert row["n"] == 1


def test_nested_json_strings_stay_strings(legacy_db):
    """vocabularyDistractors is a JSON *string* inside frames — the frontend
    does JSON.parse() on it, so the migration must not unwrap it."""
    migrate_all(legacy_db)
    with connect_db() as db:
        row = db.execute(
            "SELECT frames -> 0 ->> 'vocabularyDistractors' AS raw FROM custom_stories WHERE id = %s",
            ("s1",),
        ).fetchone()
    assert json.loads(row["raw"]) == [["廚房", "客廳"]]


def test_integer_flags_become_booleans(legacy_db):
    migrate_all(legacy_db)
    with connect_db() as db:
        row = db.execute(
            "SELECT published, linear FROM custom_stories WHERE id = %s", ("s1",)
        ).fetchone()
    assert row["published"] is True
    assert row["linear"] is False


def test_migration_is_rerunnable(legacy_db):
    """Re-running must not duplicate or error — it upserts by primary key."""
    migrate_all(legacy_db)
    counts = migrate_all(legacy_db)
    assert counts["custom_stories"] == 1
    with connect_db() as db:
        total = db.execute("SELECT count(*) AS n FROM custom_stories").fetchone()["n"]
    assert total == 1
