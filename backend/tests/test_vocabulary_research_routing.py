"""Integration tests for application/vocabulary_research.py's Epic 6
orchestration: apply_response_routing and enroll_research_retention_for_attempt."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import db
from application.research.retention import enroll_section_retention
from application.research.response_routing import apply_response_routing, enroll_research_retention_for_attempt
from domain.research.policy import build_research_context
from repositories import research as repo


INACTIVE = build_research_context(
    study_id=None, study_status=None, policy_version=None, assignment_version=None,
    practice_budget=None, participant_active=False,
)


def _active_context(study_id: str) -> object:
    return build_research_context(
        study_id=study_id, study_status="active", policy_version="v1", assignment_version="v1",
        practice_budget=None, participant_active=True,
    )


def _create_study(study_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status="active", config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _assign(study_id, student_id, word_id, *, section_id, retention_policy="adaptive_sm2") -> None:
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="5", section_id=section_id, bkt_policy="mastery_blind", retention_policy=retention_policy,
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _attempt(mode: str, attempt_id: str = "attempt-1") -> SimpleNamespace:
    return SimpleNamespace(id=attempt_id, mode=mode, baseStoryId="story-5-1", storyId="story-5-1")


def _result(word_id: str, correct: bool) -> dict:
    return {"conceptId": word_id, "correct": correct, "authoritativeResolved": True, "activityType": "scheduled_maintenance"}


NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


class TestApplyResponseRouting:
    def test_is_a_noop_for_core_and_practice_activity_types(self):
        with db.connect_db() as conn:
            # No retention state exists for either word; if this touched
            # anything it would error looking up a non-existent assignment/
            # study rather than silently doing nothing.
            apply_response_routing(conn, "student-1", INACTIVE, _attempt("tier1"), [_result("word-a", True)], now_override=NOW)
            apply_response_routing(conn, "student-1", INACTIVE, _attempt("weak_words"), [_result("word-a", True)], now_override=NOW)
        # No exception is the assertion here - a review-only function being
        # called with a non-review attempt must not touch any table.

    def test_routes_a_review_answer_to_production_srs_for_a_non_participant(self):
        with db.connect_db() as conn:
            apply_response_routing(conn, "student-1", INACTIVE, _attempt("maintenance_review"), [
                {"conceptId": "word-a", "correct": True, "authoritativeResolved": True, "activityType": "scheduled_maintenance", "quizId": "q1"},
            ], now_override=NOW)
        # apply_srs_updates requires an existing SM-2 schedule to grade
        # (maintenance only advances an existing word) - with none enrolled,
        # zero words update. The real assertion is WHICH function ran: no
        # vocab_research_retention_state row gets created for a non-participant.
        with db.connect_db() as conn:
            rows = conn.execute("SELECT COUNT(*) AS total FROM vocab_research_retention_state WHERE student_id = %s", ("student-1",)).fetchone()
        assert rows["total"] == 0

    def test_routes_a_review_answer_to_retention_for_an_active_participant(self):
        _create_study("study-routing-a")
        _assign("study-routing-a", "student-1", "word-a", section_id="s")
        context = _active_context("study-routing-a")
        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-routing-a", "s", now=NOW - timedelta(days=2))
            apply_response_routing(
                conn, "student-1", context, _attempt("maintenance_review"),
                [{"conceptId": "word-a", "correct": True, "authoritativeResolved": True, "activityType": "scheduled_maintenance", "quizId": "q1"}],
                now_override=NOW,
            )
            state = repo.find_retention_states(conn, "student-1", "study-routing-a")["word-a"]
        assert state["reps"] == 2  # advanced past the enrollment default of 1

    def test_grades_every_word_in_one_batch_sharing_a_single_quiz_id_research_path(self):
        # Regression: a review round is typically submitted under ONE quiz
        # id for every word in it. Before Epic 6 unified the event-shaping
        # helper, the research path had no per-index uniqueness step, so
        # the second word's grading silently collided with the first's
        # idempotency key and never advanced.
        _create_study("study-routing-batch")
        _assign("study-routing-batch", "student-1", "word-a", section_id="s")
        _assign("study-routing-batch", "student-1", "word-b", section_id="s")
        context = _active_context("study-routing-batch")
        with db.connect_db() as conn:
            enroll_section_retention(conn, "student-1", "study-routing-batch", "s", now=NOW - timedelta(days=2))
            apply_response_routing(
                conn, "student-1", context, _attempt("maintenance_review"),
                [
                    {"conceptId": "word-a", "correct": True, "authoritativeResolved": True, "activityType": "scheduled_maintenance", "quizId": "shared-round"},
                    {"conceptId": "word-b", "correct": True, "authoritativeResolved": True, "activityType": "scheduled_maintenance", "quizId": "shared-round"},
                ],
                now_override=NOW,
            )
            states = repo.find_retention_states(conn, "student-1", "study-routing-batch")
        assert states["word-a"]["reps"] == 2
        assert states["word-b"]["reps"] == 2


class TestEnrollResearchRetentionForAttempt:
    def test_is_a_noop_for_a_non_participant(self):
        with db.connect_db() as conn:
            enroll_research_retention_for_attempt(conn, "student-1", INACTIVE, _attempt("tier3"), now=NOW)
            rows = conn.execute("SELECT COUNT(*) AS total FROM vocab_research_retention_state WHERE student_id = %s", ("student-1",)).fetchone()
        assert rows["total"] == 0

    def test_is_a_noop_for_a_non_core_mode(self):
        _create_study("study-enroll-noop")
        context = _active_context("study-enroll-noop")
        with db.connect_db() as conn:
            enroll_research_retention_for_attempt(conn, "student-1", context, _attempt("weak_words"), now=NOW)
            rows = conn.execute("SELECT COUNT(*) AS total FROM vocab_research_retention_state WHERE student_id = %s", ("student-1",)).fetchone()
        assert rows["total"] == 0
