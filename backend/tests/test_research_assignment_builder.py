"""Integration tests for application/research_assignment_builder.py."""
import pytest
from psycopg.types.json import Jsonb

import db
from application.research.assignment_builder import (
    AssignmentsAlreadyExistError,
    StudyFrozenError,
    build_assignments_for_study,
)
from repositories import research as repo


def _publish_story(story_id: str, lesson_number: int, word_ids: list[str]) -> None:
    vocab_assessment = [
        {
            "questionId": f"{word}:know_it:v1",
            "wordId": word,
            "targetWord": word,
            "level": "easy",
            "questionType": "basic_meaning_mcq",
            "answerFormat": "single_choice",
            "prompt": f"Answer for {word}",
            "options": ["a", "b"],
            "correctAnswer": "a",
            "acceptedAnswers": ["a"],
        }
        for word in word_ids
    ]
    with db.connect_db() as conn:
        conn.execute(
            """
            INSERT INTO custom_stories (id, title, frames, published, lesson_number, vocab_assessment)
            VALUES (%s, %s, %s, TRUE, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                published = TRUE, lesson_number = EXCLUDED.lesson_number,
                vocab_assessment = EXCLUDED.vocab_assessment
            """,
            (story_id, f"Lesson {lesson_number} story", Jsonb([]), lesson_number, Jsonb(vocab_assessment)),
        )


def _create_study(study_id: str, status: str = "active") -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status=status, config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _add_participant(study_id: str, student_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id=None, active=True, created_at="2026-01-01T00:00:00Z",
        )


def test_assigns_every_active_participant_a_condition_for_every_eligible_word():
    _create_study("study-basic")
    _publish_story("story-l5", 5, ["w1", "w2", "w3", "w4"])
    _add_participant("study-basic", "stu-a")
    _add_participant("study-basic", "stu-b")

    with db.connect_db() as conn:
        result = build_assignments_for_study(
            conn, "study-basic", assignment_version="v1", created_at="2026-01-02T00:00:00Z",
        )
        assignments = repo.find_assignments_for_study(conn, "study-basic")

    assert result.participants_assigned == 2
    assert result.words_per_participant == 4
    assert len(assignments) == 8  # 2 participants x 4 words
    assert sum(result.condition_counts.values()) == 8
    # Each condition should appear exactly once per participant (4 words, 4 conditions).
    assert all(count == 2 for count in result.condition_counts.values())


def test_ignores_words_outside_the_lesson_range():
    _create_study("study-range")
    _publish_story("story-l5", 5, ["in-range"])
    _publish_story("story-l9", 9, ["out-of-range"])
    _add_participant("study-range", "stu-a")

    with db.connect_db() as conn:
        result = build_assignments_for_study(
            conn, "study-range", assignment_version="v1", created_at="2026-01-02T00:00:00Z",
            lesson_min=5, lesson_max=8,
        )
        assignments = repo.find_assignments_for_study(conn, "study-range")

    assert result.words_per_participant == 1
    assert [a["word_id"] for a in assignments] == ["in-range"]


def test_ignores_inactive_participants():
    _create_study("study-inactive")
    _publish_story("story-l5", 5, ["w1"])
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id="study-inactive", student_id="stu-inactive", class_id=None,
            sequence_id=None, active=False, created_at="2026-01-01T00:00:00Z",
        )
        result = build_assignments_for_study(
            conn, "study-inactive", assignment_version="v1", created_at="2026-01-02T00:00:00Z",
        )

    assert result.participants_assigned == 0


def test_refuses_to_run_twice_without_force():
    _create_study("study-once")
    _publish_story("story-l5", 5, ["w1"])
    _add_participant("study-once", "stu-a")

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "study-once", assignment_version="v1", created_at="2026-01-02T00:00:00Z")

    with db.connect_db() as conn:
        with pytest.raises(AssignmentsAlreadyExistError):
            build_assignments_for_study(conn, "study-once", assignment_version="v2", created_at="2026-01-03T00:00:00Z")


def test_force_regenerates_a_non_frozen_study():
    _create_study("study-force")
    _publish_story("story-l5", 5, ["w1", "w2"])
    _add_participant("study-force", "stu-a")

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "study-force", assignment_version="v1", created_at="2026-01-02T00:00:00Z")

    with db.connect_db() as conn:
        result = build_assignments_for_study(
            conn, "study-force", assignment_version="v2", created_at="2026-01-03T00:00:00Z", force=True,
        )
        assignments = repo.find_assignments_for_study(conn, "study-force")

    assert result.assignment_version == "v2"
    assert all(a["assignment_version"] == "v2" for a in assignments)


def test_refuses_to_run_against_a_frozen_study_even_with_force():
    _create_study("study-frozen", status="frozen")
    _publish_story("story-l5", 5, ["w1"])
    _add_participant("study-frozen", "stu-a")

    with db.connect_db() as conn:
        with pytest.raises(StudyFrozenError):
            build_assignments_for_study(
                conn, "study-frozen", assignment_version="v1", created_at="2026-01-02T00:00:00Z", force=True,
            )


def test_sets_the_participant_sequence_id_deterministically_by_roster_order():
    _create_study("study-sequence")
    _publish_story("story-l5", 5, ["w1", "w2", "w3", "w4"])
    _add_participant("study-sequence", "stu-1")
    _add_participant("study-sequence", "stu-2")
    _add_participant("study-sequence", "stu-3")

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "study-sequence", assignment_version="v1", created_at="2026-01-02T00:00:00Z")
        participants = repo.find_participants_for_study(conn, "study-sequence")

    # Ordered by student_id: stu-1, stu-2, stu-3 -> sequences A, B, C.
    by_student = {p["student_id"]: p["sequence_id"] for p in participants}
    assert by_student == {"stu-1": "A", "stu-2": "B", "stu-3": "C"}


def test_a_related_set_gets_the_same_condition_for_one_student(tmp_path):
    _create_study("study-related")
    _publish_story("story-l5", 5, ["前", "上", "後", "下"])
    _add_participant("study-related", "stu-a")

    csv_path = tmp_path / "related.csv"
    csv_path.write_text("word_id,related_set_id\n前,front-back\n後,front-back\n", encoding="utf-8")

    with db.connect_db() as conn:
        build_assignments_for_study(
            conn, "study-related", assignment_version="v1", created_at="2026-01-02T00:00:00Z",
            related_vocab_csv_path=csv_path,
        )
        assignments = {a["word_id"]: a for a in repo.find_assignments_for_study(conn, "study-related")}

    assert assignments["前"]["bkt_policy"] == assignments["後"]["bkt_policy"]
    assert assignments["前"]["retention_policy"] == assignments["後"]["retention_policy"]
    assert assignments["前"]["related_set_id"] == "front-back"


def test_yoked_words_get_a_yoke_source_from_the_matching_adaptive_condition():
    _create_study("study-yoke")
    _publish_story("story-l5", 5, ["w1", "w2", "w3", "w4"])
    _add_participant("study-yoke", "stu-a")

    with db.connect_db() as conn:
        build_assignments_for_study(conn, "study-yoke", assignment_version="v1", created_at="2026-01-02T00:00:00Z")
        assignments = repo.find_assignments_for_study(conn, "study-yoke")

    yoked = [a for a in assignments if a["retention_policy"] == "yoked"]
    adaptive_word_ids = {a["word_id"] for a in assignments if a["retention_policy"] == "adaptive_sm2"}
    assert len(yoked) > 0
    for row in yoked:
        assert row["yoke_source_word_id"] in adaptive_word_ids
