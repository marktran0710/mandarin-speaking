"""Tests for application/research_assignment_audit.py - proves the audit
actually detects each kind of problem it claims to, not just that it runs
without crashing on well-formed data."""
import db
from application.research.assignment_audit import audit_assignments_for_study
from application.research.assignment_builder import build_assignments_for_study
from repositories import research as repo
from psycopg.types.json import Jsonb


def _publish_story(story_id: str, lesson_number: int, word_ids: list[str]) -> None:
    vocab_assessment = [
        {"questionId": f"{w}:know_it:v1", "wordId": w, "targetWord": w, "level": "easy",
         "questionType": "basic_meaning_mcq", "answerFormat": "single_choice",
         "prompt": f"Answer for {w}", "options": ["a", "b"], "correctAnswer": "a", "acceptedAnswers": ["a"]}
        for w in word_ids
    ]
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stories (id, title, frames, published, lesson_number, vocab_assessment)
            VALUES (%s, %s, %s, TRUE, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                published = TRUE, lesson_number = EXCLUDED.lesson_number, vocab_assessment = EXCLUDED.vocab_assessment
            """,
            (story_id, f"Lesson {lesson_number} story", Jsonb([]), lesson_number, Jsonb(vocab_assessment)),
        )


def _create_study(study_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status="active", config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _add_participant(study_id: str, student_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id=None, active=True, created_at="2026-01-01T00:00:00Z",
        )


def test_a_normal_run_is_reported_clean():
    _create_study("audit-clean")
    _publish_story("story-l5", 5, ["w1", "w2", "w3", "w4"])
    _add_participant("audit-clean", "stu-a")
    _add_participant("audit-clean", "stu-b")

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "audit-clean", assignment_version="v1", created_at="2026-01-02T00:00:00Z")
        report = audit_assignments_for_study(conn, "audit-clean")

    assert report.is_clean
    assert report.total_assignments == 8
    assert sum(report.condition_counts.values()) == 8


def test_detects_a_participant_added_after_the_run_as_missing():
    _create_study("audit-missing")
    _publish_story("story-l5", 5, ["w1", "w2"])
    _add_participant("audit-missing", "stu-a")

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "audit-missing", assignment_version="v1", created_at="2026-01-02T00:00:00Z")

    # Added after the assignment run - has zero assignments.
    _add_participant("audit-missing", "stu-late")

    with db.connect_db() as conn:
        report = audit_assignments_for_study(conn, "audit-missing")

    assert not report.is_clean
    assert report.participants_with_missing_words["stu-late"] == (0, 2)
    assert "stu-a" not in report.participants_with_missing_words


def test_detects_a_related_set_split_across_conditions_for_one_student():
    _create_study("audit-related-violation")
    _publish_story("story-l5", 5, ["w1"])
    _add_participant("audit-related-violation", "stu-a")

    # Directly insert conflicting rows - this is not something the real
    # builder can produce (it always keeps a related set together), but the
    # audit's OWN detection logic must still catch it if the data is ever
    # wrong, independent of whether the builder is currently correct.
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id="audit-related-violation", student_id="stu-a", word_id="前",
            lesson_id="5", section_id="story-l5", bkt_policy="mastery_blind",
            retention_policy="yoked", sequence_id="A", related_set_id="front-back",
            yoke_source_word_id=None, assignment_version="v1", created_at="2026-01-02T00:00:00Z",
        )
        repo.insert_assignment(
            conn, study_id="audit-related-violation", student_id="stu-a", word_id="後",
            lesson_id="5", section_id="story-l5", bkt_policy="bkt_personalized",
            retention_policy="adaptive_sm2", sequence_id="A", related_set_id="front-back",
            yoke_source_word_id=None, assignment_version="v1", created_at="2026-01-02T00:00:00Z",
        )
        report = audit_assignments_for_study(conn, "audit-related-violation")

    assert not report.is_clean
    assert ("stu-a", "front-back") in report.related_set_violations


def test_detects_unyoked_words_when_word_count_is_not_a_multiple_of_four():
    _create_study("audit-unyoked")
    _publish_story("story-l5", 5, ["w1", "w2", "w3", "w4", "w5"])  # 5 words: C,B,S,BS,C -> 2nd C unyoked
    _add_participant("audit-unyoked", "stu-a")

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "audit-unyoked", assignment_version="v1", created_at="2026-01-02T00:00:00Z")
        report = audit_assignments_for_study(conn, "audit-unyoked")

    assert not report.is_clean
    assert report.unyoked_count == 1


def test_reports_lesson_and_class_balance():
    _create_study("audit-balance")
    _publish_story("story-l5", 5, ["w1", "w2"])
    _publish_story("story-l6", 6, ["w3", "w4"])
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id="audit-balance", student_id="stu-a", class_id="class-1",
            sequence_id=None, active=True, created_at="2026-01-01T00:00:00Z",
        )

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "audit-balance", assignment_version="v1", created_at="2026-01-02T00:00:00Z")
        report = audit_assignments_for_study(conn, "audit-balance")

    assert set(report.lesson_balance.keys()) == {"5", "6"}
    assert sum(sum(counts.values()) for counts in report.lesson_balance.values()) == 4
    assert "class-1" in report.class_balance
    assert sum(report.class_balance["class-1"].values()) == 4
