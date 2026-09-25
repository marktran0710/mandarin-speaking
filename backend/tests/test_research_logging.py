"""Epic 8, Task 8.1: application/research_logging.py's thin, validating
wrapper around the policy-event log."""
from datetime import datetime, timezone

import pytest

import db
from application.research.logging import condition_label, record_policy_event
from repositories import research as repo

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _create_study(study_id: str) -> None:
    with db.connect_db() as conn:
        repo.insert_study(
            conn, id=study_id, name="Test study", status="active", config_json={},
            policy_version="v1", assignment_version="v1", created_at="2026-01-01T00:00:00Z",
        )


def _events(study_id: str, student_id: str) -> list[dict]:
    with db.connect_db() as conn:
        return conn.execute(
            "SELECT * FROM vocab_research_policy_events WHERE study_id = %s AND student_id = %s ORDER BY id",
            (study_id, student_id),
        ).fetchall()


class TestConditionLabel:
    def test_maps_every_policy_pair_to_its_condition_letter(self):
        assert condition_label("mastery_blind", "yoked") == "C"
        assert condition_label("bkt_personalized", "yoked") == "B"
        assert condition_label("mastery_blind", "adaptive_sm2") == "S"
        assert condition_label("bkt_personalized", "adaptive_sm2") == "BS"


class TestRecordPolicyEvent:
    def test_is_a_noop_when_study_id_is_none(self):
        with db.connect_db() as conn:
            record_policy_event(conn, study_id=None, student_id="student-1", event_type="core_completed", occurred_at=NOW)
        # No exception, and nothing to look up - a None study_id has no row
        # to query by definition, so the assertion is just "did not raise".

    def test_rejects_an_unknown_event_type(self):
        _create_study("study-log-invalid")
        with db.connect_db() as conn:
            with pytest.raises(ValueError):
                record_policy_event(conn, study_id="study-log-invalid", student_id="student-1", event_type="not_a_real_event", occurred_at=NOW)

    def test_records_a_word_scoped_event_with_its_payload(self):
        _create_study("study-log-word")
        with db.connect_db() as conn:
            record_policy_event(
                conn, study_id="study-log-word", student_id="student-1", event_type="practice_item_selected",
                word_id="word-a", payload={"condition": "B"}, occurred_at=NOW,
            )
        events = _events("study-log-word", "student-1")
        assert len(events) == 1
        assert events[0]["event_type"] == "practice_item_selected"
        assert events[0]["word_id"] == "word-a"
        assert events[0]["payload_json"]["condition"] == "B"

    def test_records_a_session_scoped_event_with_no_word_id(self):
        _create_study("study-log-session")
        with db.connect_db() as conn:
            record_policy_event(
                conn, study_id="study-log-session", student_id="student-1", event_type="core_completed",
                payload={"sectionId": "story-5-1"}, occurred_at=NOW,
            )
        events = _events("study-log-session", "student-1")
        assert len(events) == 1
        assert events[0]["word_id"] is None
