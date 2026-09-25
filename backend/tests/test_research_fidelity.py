"""Epic 8, Task 8.2/8.3: application/research_fidelity.py's aggregation."""
from datetime import datetime, timedelta, timezone

import pytest

import db
from application.research.fidelity import ResearchStudyNotFoundError, build_admin_summary, build_fidelity_summary
from application.research.logging import record_policy_event
from repositories import research as repo

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


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


def _assign(study_id, student_id, word_id, *, bkt_policy="mastery_blind", retention_policy="adaptive_sm2"):
    with db.connect_db() as conn:
        repo.insert_assignment(
            conn, study_id=study_id, student_id=student_id, word_id=word_id,
            lesson_id="5", section_id="s", bkt_policy=bkt_policy, retention_policy=retention_policy,
            sequence_id="A", related_set_id=None, yoke_source_word_id=None,
            assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


class TestBuildFidelitySummary:
    def test_an_empty_study_reports_all_zeros_and_no_violations(self):
        study_id = "study-fidelity-empty"
        _create_study(study_id)
        with db.connect_db() as conn:
            summary = build_fidelity_summary(conn, study_id)
        assert summary["coreCompletedCount"] == 0
        assert summary["practice"]["bktOnCount"] == 0
        assert summary["practice"]["bktOffCount"] == 0
        assert summary["probes"]["completionRate"] is None
        assert summary["policyViolations"] == 0

    def test_splits_practice_items_selected_into_bkt_on_and_bkt_off(self):
        study_id = "study-fidelity-practice"
        _create_study(study_id)
        with db.connect_db() as conn:
            record_policy_event(conn, study_id=study_id, student_id="s1", event_type="practice_item_selected", word_id="w1", payload={"condition": "C"}, occurred_at=NOW)
            record_policy_event(conn, study_id=study_id, student_id="s1", event_type="practice_item_selected", word_id="w2", payload={"condition": "S"}, occurred_at=NOW)
            record_policy_event(conn, study_id=study_id, student_id="s1", event_type="practice_item_selected", word_id="w3", payload={"condition": "B"}, occurred_at=NOW)
            record_policy_event(conn, study_id=study_id, student_id="s1", event_type="practice_item_selected", word_id="w4", payload={"condition": "BS"}, occurred_at=NOW)
            summary = build_fidelity_summary(conn, study_id)
        assert summary["practice"]["bktOffCount"] == 2  # C + S
        assert summary["practice"]["bktOnCount"] == 2  # B + BS

    def test_computes_probe_completion_rate(self):
        study_id = "study-fidelity-probes"
        _create_study(study_id)
        with db.connect_db() as conn:
            record_policy_event(conn, study_id=study_id, student_id="s1", event_type="probe_assigned", word_id="w1", occurred_at=NOW)
            record_policy_event(conn, study_id=study_id, student_id="s1", event_type="probe_assigned", word_id="w2", occurred_at=NOW)
            record_policy_event(conn, study_id=study_id, student_id="s1", event_type="probe_completed", word_id="w1", occurred_at=NOW)
            summary = build_fidelity_summary(conn, study_id)
        assert summary["probes"]["assigned"] == 2
        assert summary["probes"]["completed"] == 1
        assert summary["probes"]["completionRate"] == pytest.approx(0.5)

    def test_computes_average_review_delay_from_retention_events(self):
        study_id = "study-fidelity-delay"
        _create_study(study_id)
        with db.connect_db() as conn:
            from analytics.learner_model.srs import SrsState

            due_on = NOW
            answered_on = NOW + timedelta(days=2)
            repo.record_retention_event(
                conn, student_id="s1", study_id=study_id, word_id="w1", event_type="maintenance_success",
                old_state=SrsState(reps=1, ease=2.5, interval_days=1, due_on=due_on, last_reviewed_on=NOW - timedelta(days=1)),
                new_state=SrsState(reps=2, ease=2.5, interval_days=6, due_on=answered_on + timedelta(days=6), last_reviewed_on=answered_on),
                source_response_id="src-1", algorithm_version="sm2-v1", correct=True, occurred_at=answered_on,
            )
            summary = build_fidelity_summary(conn, study_id)
        assert summary["retention"]["averageDelayDays"] == pytest.approx(2.0)


class TestBuildAdminSummary:
    def test_raises_for_an_unknown_study(self):
        with db.connect_db() as conn:
            with pytest.raises(ResearchStudyNotFoundError):
                build_admin_summary(conn, "no-such-study")

    def test_reports_participant_counts_and_assignment_balance(self):
        study_id = "study-admin-summary"
        _create_study(study_id)
        _add_participant(study_id, "student-1", active=True)
        _add_participant(study_id, "student-2", active=False)
        _assign(study_id, "student-1", "word-a", bkt_policy="mastery_blind", retention_policy="yoked")
        _assign(study_id, "student-1", "word-b", bkt_policy="bkt_personalized", retention_policy="adaptive_sm2")

        with db.connect_db() as conn:
            summary = build_admin_summary(conn, study_id)

        assert summary["studyId"] == study_id
        assert summary["participants"] == {"active": 1, "total": 2}
        assert summary["totalAssignments"] == 2
        assert summary["assignmentBalance"] == {"C": 1, "BS": 1}
        assert "fidelity" in summary
