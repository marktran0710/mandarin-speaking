import json

import pytest
from psycopg.types.json import Jsonb

from db import connect_db
from scripts.purge_legacy_vocab import WORD_TABLES, purge


CURRENT = "C5-5-1-W007"
OLD = "C5-5-1-I6-W007"


@pytest.fixture
def vocabulary():
    with connect_db() as db:
        db.execute("DELETE FROM learning_measurement_events WHERE event_id IN ('event-current', 'event-old')")
        db.execute(
            "INSERT INTO custom_stories (id, title, published, vocab_assessment) VALUES ('lesson', 'Lesson', TRUE, %s)",
            (Jsonb([{"wordId": CURRENT, "targetWord": "下午茶"}]),),
        )
        for label, word_id in (("current", CURRENT), ("old", OLD)):
            attempt = f"attempt-{label}"
            db.execute(
                """INSERT INTO vocab_quiz_attempts
                   (id, story_id, student_name, student_id, completed_at, mode,
                    total_questions, correct_count, total_time_ms, question_results)
                   VALUES (%s, 'lesson', 'Student', 'student', '2026-09-27T00:00:00Z',
                           'tier1', 1, 1, 100, %s)""",
                (attempt, Jsonb([{"conceptId": f" {word_id} ", "word": "下午茶", "correct": True}])),
            )
            db.execute(
                """INSERT INTO vocab_quiz_responses
                   (student_id, word_id, word, quiz_id, attempt_id, item_id,
                    question_type, correct, response_time_ms, attempt_order)
                   VALUES ('student', %s, '下午茶', %s, %s, %s, 'basic_meaning_mcq', TRUE, 100, 0)""",
                (word_id, attempt, attempt, f"item-{label}"),
            )
            db.execute(
                """INSERT INTO student_vocab_mastery
                   (student_id, word_id, p_learned, observation_count, correct_count,
                    incorrect_count, created_at, updated_at)
                   VALUES ('student', %s, .5, 1, 1, 0, 'now', 'now')""", (word_id,),
            )
            db.execute(
                """INSERT INTO student_vocab_srs (student_id, word_id, created_at, updated_at)
                   VALUES ('student', %s, 'now', 'now')""", (word_id,),
            )
            db.execute(
                """INSERT INTO student_vocab_srs_events
                   (student_id, word_id, source_response_id, event_type,
                    old_reps, new_reps, old_ease, new_ease, old_interval_days,
                    new_interval_days, algorithm_version, occurred_at)
                   VALUES ('student', %s, %s, 'legacy_snapshot', 0, 0, 2.5, 2.5, 0, 0, 'v1', now())""",
                (word_id, f"source-{label}"),
            )
            db.execute(
                """INSERT INTO learning_measurement_events
                   (event_id, schema_version, name, occurred_at, attempt_id)
                   VALUES (%s, 'v1', 'quiz', 'now', %s)""", (f"event-{label}", attempt),
            )
    yield
    with connect_db() as db:
        db.execute("DELETE FROM learning_measurement_events WHERE event_id IN ('event-current', 'event-old')")


def test_preview_preserves_all_data(vocabulary):
    with connect_db() as db:
        report = purge(db)
        assert report["obsoleteWordIds"] == [OLD]
        assert not report["executed"]
        assert all(count == 1 for count in report["rows"].values())
        assert db.execute("SELECT count(*) AS count FROM vocab_quiz_responses").fetchone()["count"] == 2


def test_execute_backs_up_dependents_preserves_current_and_is_idempotent(vocabulary, tmp_path):
    backup = tmp_path / "backup.json"
    with connect_db() as db:
        report = purge(db, execute=True, backup=backup)
        assert report["executed"]
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert saved["tables"]["vocab_quiz_responses"][0]["word_id"] == OLD
    assert saved["tables"]["vocab_quiz_attempts"][0]["id"] == "attempt-old"
    with connect_db() as db:
        for table in WORD_TABLES:
            assert [row["word_id"] for row in db.execute(f"SELECT word_id FROM {table}").fetchall()] == [CURRENT]
        assert db.execute("SELECT id FROM vocab_quiz_attempts").fetchone()["id"] == "attempt-current"
        assert db.execute("SELECT event_id FROM learning_measurement_events").fetchone()["event_id"] == "event-current"
        assert db.execute("SELECT published FROM custom_stories").fetchone()["published"]
        assert purge(db)["obsoleteWordCount"] == 0
        assert not purge(db, execute=True, backup=backup)["executed"]


def test_backup_failure_prevents_deletion(vocabulary, tmp_path):
    backup = tmp_path / "backup.json"
    backup.write_text("previous backup", encoding="utf-8")
    with pytest.raises(FileExistsError), connect_db() as db:
        purge(db, execute=True, backup=backup)
    with connect_db() as db:
        assert purge(db)["obsoleteWordCount"] == 1
    assert backup.read_text(encoding="utf-8") == "previous backup"


def test_failure_after_deletion_rolls_back_all_tables(vocabulary, tmp_path):
    class FailAtAttempts:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, query, params=None):
            statement = query if isinstance(query, str) else query.as_string(self.connection)
            if statement.startswith('DELETE FROM "vocab_quiz_attempts"'):
                raise RuntimeError("Simulated deletion failure")
            return self.connection.execute(query, params)

    with pytest.raises(RuntimeError, match="Simulated"), connect_db() as db:
        purge(FailAtAttempts(db), execute=True, backup=tmp_path / "backup.json")
    with connect_db() as db:
        assert all(count == 1 for count in purge(db)["rows"].values())


def test_mixed_attempt_is_rejected_without_deleting_current_answers(vocabulary, tmp_path):
    with connect_db() as db:
        db.execute("UPDATE vocab_quiz_attempts SET question_results = %s WHERE id = 'attempt-old'", (
            Jsonb([{"conceptId": OLD}, {"conceptId": CURRENT}]),
        ))
    with pytest.raises(ValueError, match="mixes obsolete and current"), connect_db() as db:
        purge(db, execute=True, backup=tmp_path / "backup.json")
    assert not (tmp_path / "backup.json").exists()


def test_research_linked_evidence_is_rejected(vocabulary, tmp_path):
    with connect_db() as db:
        db.execute("UPDATE vocab_quiz_responses SET research_study_id = 'study' WHERE word_id = %s", (OLD,))
    with pytest.raises(ValueError, match="research-linked"), connect_db() as db:
        purge(db, execute=True, backup=tmp_path / "backup.json")
    assert not (tmp_path / "backup.json").exists()


def test_empty_published_pool_is_rejected(vocabulary, tmp_path):
    with connect_db() as db:
        db.execute("UPDATE custom_stories SET published = FALSE")
    with pytest.raises(ValueError, match="Published vocabulary is empty"), connect_db() as db:
        purge(db, execute=True, backup=tmp_path / "backup.json")
    assert not (tmp_path / "backup.json").exists()
