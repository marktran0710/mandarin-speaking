import json

import pytest
from psycopg.types.json import Jsonb

from db import connect_db
from scripts.reset_student_lesson import reset_lesson
from services.vocab_quiz_progression_service import get_progression


@pytest.fixture
def lessons():
    with connect_db() as db:
        for student in ("student-1", "student-2"):
            db.execute("INSERT INTO students (id, name, password) VALUES (%s, %s, 'test')", (student, student))
        for lesson in ("lesson-1", "lesson-2"):
            db.execute(
                "INSERT INTO custom_stories (id, title, published, vocab_assessment) VALUES (%s, %s, TRUE, %s)",
                (lesson, lesson, Jsonb([{"wordId": f"{lesson}-word", "targetWord": "Word"}])),
            )
        for student, lesson in (("student-1", "lesson-1"), ("student-1", "lesson-2"), ("student-2", "lesson-1")):
            for tier in ("tier1", "tier2", "tier3"):
                attempt = f"{student}:{lesson}:{tier}"
                db.execute(
                    """INSERT INTO vocab_quiz_attempts
                       (id, student_id, student_name, story_id, mode, completed_at,
                        total_questions, correct_count, total_time_ms, question_results)
                       VALUES (%s, %s, %s, %s, %s, '2026-09-28T00:00:00Z', 1, 1, 100, '[]')""",
                    (attempt, student, student, lesson, tier),
                )
                db.execute(
                    """INSERT INTO vocab_quiz_responses
                       (student_id, word_id, word, lesson_id, quiz_id, attempt_id, item_id,
                        question_type, correct, response_time_ms, attempt_order, quiz_mode,
                        quiz_level, bkt_eligible)
                       VALUES (%s, %s, 'Word', %s, %s, %s, %s, 'basic_meaning_mcq', TRUE, 100, 0, %s, %s, TRUE)""",
                    (student, f"{lesson}-word", lesson, attempt, attempt, attempt, tier, tier),
                )
            db.execute(
                """INSERT INTO student_vocab_mastery
                   (student_id, word_id, p_learned, observation_count, correct_count,
                    incorrect_count, created_at, updated_at)
                   VALUES (%s, %s, .8, 3, 3, 0, 'now', 'now')""", (student, f"{lesson}-word"),
            )
            db.execute(
                "INSERT INTO speaking_progress (id, student_id, topic_id, scene_index, content_passed) VALUES (%s, %s, %s, 0, TRUE)",
                (f"{student}:{lesson}", student, f"teacher-{lesson}"),
            )
            db.execute(
                """INSERT INTO story_submissions (id, student_id, student_name, story_id, story_title, submitted_at, scenes)
                   VALUES (%s, %s, %s, %s, 'Lesson', 'now', '[]')""",
                (f"{student}:{lesson}", student, student, f"teacher-{lesson}"),
            )


def test_reset_relocks_target_preserves_other_lesson_and_other_student(lessons, tmp_path):
    backup = tmp_path / "backup.json"
    with connect_db() as db:
        assert get_progression(db, "student-1", "lesson-1")["quizStars"] == 3
        report = reset_lesson(db, "student-1", "teacher-lesson-1", execute=True, backup=backup)
        assert report["executed"]
        assert report["progression"]["quizStars"] == 0
        assert not report["progression"]["speakingUnlocked"]
        assert not report["progression"]["conversationUnlocked"]
        for student, lesson in (("student-1", "lesson-2"), ("student-2", "lesson-1")):
            assert get_progression(db, student, lesson)["quizStars"] == 3
        assert db.execute("SELECT count(*) AS count FROM speaking_progress").fetchone()["count"] == 2
        assert db.execute("SELECT count(*) AS count FROM story_submissions").fetchone()["count"] == 2
    saved = json.loads(backup.read_text(encoding="utf-8"))
    assert len(saved["tables"]["vocab_quiz_responses"]) == 3
    assert saved["tables"]["speaking_progress"][0]["content_passed"]


def test_reset_preview_preserves_the_gate(lessons):
    with connect_db() as db:
        report = reset_lesson(db, "student-1", "lesson-1")
        assert not report["executed"]
        assert report["rows"]["vocab_quiz_responses"] == 3
        assert get_progression(db, "student-1", "lesson-1")["quizStars"] == 3


def test_reset_requires_a_writable_new_backup(lessons, tmp_path):
    backup = tmp_path / "backup.json"
    backup.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError), connect_db() as db:
        reset_lesson(db, "student-1", "lesson-1", execute=True, backup=backup)
    with connect_db() as db:
        assert get_progression(db, "student-1", "lesson-1")["quizStars"] == 3
