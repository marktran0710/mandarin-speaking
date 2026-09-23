"""Integration tests for application/research_retention.py (Epic 5)."""
from datetime import datetime, timedelta, timezone

import pytest

import db
from application.research_retention import (
    ResearchReviewUnavailableError,
    apply_retention_review,
    build_review_session,
    enroll_section_retention,
)
from repositories import vocabulary_research as repo


def _create_study(study_id: str, status: str = "active") -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status=status, config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _add_participant(study_id: str, student_id: str, active: bool = True) -> None:
    with db.connect_db() as conn:
        repo.insert_participant(
            conn, study_id=study_id, student_id=student_id, class_id=None,
            sequence_id="A", active=active, created_at="2026-01-01T00:00:00Z",
        )


def _assign(study_id, student_id, word_id, *, section_id, bkt_policy, retention_policy, yoke_source_word_id=None):
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="5", section_id=section_id, bkt_policy=bkt_policy, retention_policy=retention_policy,
            sequence_id="A", related_set_id=None, yoke_source_word_id=yoke_source_word_id,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _response(word_id: str, correct: bool, quiz_id: str) -> dict:
    return {
        "conceptId": word_id, "correct": correct, "authoritativeResolved": True,
        "activityType": "scheduled_maintenance", "sourceResponseId": f"{quiz_id}:0",
        "quizId": quiz_id, "attemptId": quiz_id,
    }


def _retention_events(student_id: str, study_id: str, word_id: str) -> list[dict]:
    with db.connect_db() as conn:
        return conn.execute(
            "SELECT * FROM vocab_research_retention_events WHERE student_id = %s AND study_id = %s AND word_id = %s ORDER BY id",
            (student_id, study_id, word_id),
        ).fetchall()


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestEnrollSectionRetention:
    def test_enrolls_every_assigned_word_in_the_target_section(self):
        _create_study("study-enroll")
        _assign("study-enroll", "student-1", "word-a", section_id="story-5-1", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        _assign("study-enroll", "student-1", "word-b", section_id="story-5-1", bkt_policy="bkt_personalized", retention_policy="yoked")

        with db.connect_db() as conn:
            enrolled = enroll_section_retention(conn, "student-1", "study-enroll", "story-5-1", now=NOW)
            states = repo.find_retention_states(conn, "student-1", "study-enroll")

        assert enrolled == 2
        assert set(states) == {"word-a", "word-b"}
        assert states["word-a"]["reps"] == 1
        assert states["word-a"]["interval_days"] == 1

    def test_adaptive_and_yoked_words_enroll_with_the_identical_initial_schedule(self):
        _create_study("study-enroll-identical")
        _assign("study-enroll-identical", "student-1", "word-adaptive", section_id="s", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        _assign("study-enroll-identical", "student-1", "word-yoked", section_id="s", bkt_policy="mastery_blind", retention_policy="yoked", yoke_source_word_id="word-adaptive")

        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-enroll-identical", "s", now=NOW)
            states = repo.find_retention_states(conn, "student-1", "study-enroll-identical")

        assert states["word-adaptive"]["due_on"] == states["word-yoked"]["due_on"]
        assert states["word-adaptive"]["reps"] == states["word-yoked"]["reps"]

    def test_is_idempotent_and_never_re_enrolls_an_existing_word(self):
        _create_study("study-idempotent")
        _assign("study-idempotent", "student-1", "word-a", section_id="s", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")

        with db.connect_db() as conn:
            first = enroll_section_retention(conn, "student-1", "study-idempotent", "s", now=NOW)
            second = enroll_section_retention(conn, "student-1", "study-idempotent", "s", now=NOW + timedelta(days=5))

        assert first == 1
        assert second == 0

    def test_only_enrolls_words_from_the_target_section(self):
        _create_study("study-scoped")
        _assign("study-scoped", "student-1", "word-here", section_id="story-5-1", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        _assign("study-scoped", "student-1", "word-elsewhere", section_id="story-5-2", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")

        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-scoped", "story-5-1", now=NOW)
            states = repo.find_retention_states(conn, "student-1", "study-scoped")

        assert set(states) == {"word-here"}


class TestApplyRetentionReview:
    def test_grades_an_adaptive_word_with_real_sm2_math_once_due(self):
        _create_study("study-adaptive-grade")
        _assign("study-adaptive-grade", "student-1", "word-a", section_id="s", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-adaptive-grade", "s", now=NOW)
            due_time = NOW + timedelta(days=1, hours=1)
            updated = apply_retention_review(conn, "student-1", "study-adaptive-grade", [_response("word-a", True, "q1")], now=due_time)
            states = repo.find_retention_states(conn, "student-1", "study-adaptive-grade")

        assert updated == 1
        # SECOND_INTERVAL_DAYS after the second successful review (reps was 1 at enrollment).
        assert states["word-a"]["reps"] == 2
        assert states["word-a"]["interval_days"] == 6

    def test_never_changes_a_yoked_words_own_schedule_from_its_own_answer(self):
        _create_study("study-yoked-blind")
        _assign("study-yoked-blind", "student-1", "word-yoked", section_id="s", bkt_policy="mastery_blind", retention_policy="yoked")
        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-yoked-blind", "s", now=NOW)
            before = repo.find_retention_states(conn, "student-1", "study-yoked-blind")["word-yoked"]
            due_time = NOW + timedelta(days=1, hours=1)
            updated = apply_retention_review(conn, "student-1", "study-yoked-blind", [_response("word-yoked", False, "q1")], now=due_time)
            after = repo.find_retention_states(conn, "student-1", "study-yoked-blind")["word-yoked"]

        assert updated == 0
        assert after["reps"] == before["reps"]
        assert after["due_on"] == before["due_on"]
        events = _retention_events("student-1", "study-yoked-blind", "word-yoked")
        assert any(event["event_type"] == "yoked_exposure" for event in events)

    def test_mirrors_the_adaptive_words_new_schedule_onto_its_yoked_pair_without_the_pair_being_answered(self):
        _create_study("study-mirror")
        _assign("study-mirror", "student-1", "word-source", section_id="s", bkt_policy="bkt_personalized", retention_policy="adaptive_sm2")
        _assign("study-mirror", "student-1", "word-yoked", section_id="s", bkt_policy="mastery_blind", retention_policy="yoked", yoke_source_word_id="word-source")
        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-mirror", "s", now=NOW)
            due_time = NOW + timedelta(days=1, hours=1)
            # Only word-source is answered this round - word-yoked is not in the
            # response batch at all.
            apply_retention_review(conn, "student-1", "study-mirror", [_response("word-source", True, "q1")], now=due_time)
            states = repo.find_retention_states(conn, "student-1", "study-mirror")

        assert states["word-source"]["due_on"] == states["word-yoked"]["due_on"]
        assert states["word-source"]["reps"] == states["word-yoked"]["reps"]
        events = _retention_events("student-1", "study-mirror", "word-yoked")
        assert any(event["event_type"] == "yoked_mirror" for event in events)

    def test_does_not_grade_a_word_not_yet_due(self):
        _create_study("study-not-due")
        _assign("study-not-due", "student-1", "word-a", section_id="s", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-not-due", "s", now=NOW)
            # Reviewed the same hour it was enrolled - due_on is a day away.
            updated = apply_retention_review(conn, "student-1", "study-not-due", [_response("word-a", True, "q1")], now=NOW + timedelta(hours=1))
        assert updated == 0


class TestBuildReviewSession:
    def test_raises_for_a_non_participant(self):
        with db.connect_db() as conn:
            with pytest.raises(ResearchReviewUnavailableError):
                build_review_session(conn, "no-such-student")

    def test_returns_only_words_that_are_actually_due(self):
        _create_study("study-due-session")
        _add_participant("study-due-session", "student-1")
        # Enrolled long ago, so its 1-day interval has long since passed.
        _assign("study-due-session", "student-1", "word-due", section_id="s1", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        # Enrolled "now" (real clock), so it is not due for another day.
        _assign("study-due-session", "student-1", "word-not-due", section_id="s2", bkt_policy="mastery_blind", retention_policy="adaptive_sm2")
        with db.connect_db() as conn:
            long_ago = datetime.now(timezone.utc) - timedelta(days=30)
            enroll_section_retention(conn, "student-1", "study-due-session", "s1", now=long_ago)
            enroll_section_retention(conn, "student-1", "study-due-session", "s2")
            session = build_review_session(conn, "student-1")

        assert "word-due" in session["wordIds"]
        assert "word-not-due" not in session["wordIds"]
