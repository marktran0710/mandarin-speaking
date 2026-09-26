"""Acceptance-level checks for the modified SM-2 retention policy.

These tests intentionally name the launch contract in one place: enrollment
starts at one day, successful maintenance reviews follow 1 -> 6 -> 15 days,
failures reset the repetition count, and retries cannot create a second
transition for the same server response.
"""

from datetime import datetime, timedelta, timezone

from analytics.learner_model.srs import SrsState, is_due, review, should_advance
from analytics.learner_model.srs_store import apply_srs_updates


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=timezone.utc)


def test_modified_sm2_acceptance_sequence_is_one_six_fifteen_then_reset():
    state = SrsState()

    state = review(state, 4, _dt(1))
    assert (state.reps, state.interval_days, state.ease) == (1, 1, 2.5)
    assert state.due_on == _dt(2)

    state = review(state, 4, _dt(2))
    assert (state.reps, state.interval_days, state.ease) == (2, 6, 2.5)
    assert state.due_on == _dt(8)

    state = review(state, 4, _dt(8))
    assert (state.reps, state.interval_days, state.ease) == (3, 15, 2.5)
    assert state.due_on == _dt(23)

    failed = review(state, 2, _dt(23))
    assert (failed.reps, failed.interval_days) == (0, 1)
    assert round(failed.ease, 2) == 2.18
    assert failed.due_on == _dt(24)


def test_due_and_early_review_guards_use_exact_instants():
    state = review(SrsState(), 4, _dt(1), day_seconds=60)
    assert is_due(state, _dt(1, 0)) is False
    assert is_due(state, _dt(1) + timedelta(seconds=59)) is False
    assert is_due(state, _dt(1) + timedelta(minutes=1)) is True
    assert should_advance(state, _dt(1) + timedelta(seconds=59), day_seconds=60) is False
    assert should_advance(state, _dt(1) + timedelta(minutes=1), day_seconds=60) is True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _IdempotentDb:
    """Small DB double that models the event uniqueness constraint."""

    def __init__(self, state_row):
        self.state_row = state_row
        self.events = set()
        self.upserts = []

    def execute(self, sql, params=None):
        if "INSERT INTO student_vocab_srs_events" in sql:
            source_response_id = params[2]
            if source_response_id in self.events:
                return _Cursor([])
            self.events.add(source_response_id)
            return _Cursor([{"id": len(self.events)}])
        if "INSERT INTO student_vocab_srs" in sql:
            self.upserts.append(params)
            self.state_row = {
                "word_id": params[1],
                "reps": params[2],
                "ease": params[3],
                "interval_days": params[4],
                "due_on": params[5],
                "last_reviewed_on": params[6],
            }
            return _Cursor([])
        return _Cursor([self.state_row])


def test_maintenance_retry_is_idempotent_and_does_not_advance_early():
    now = _dt(1)
    db = _IdempotentDb({
        "word_id": "word-1",
        "reps": 1,
        "ease": 2.5,
        "interval_days": 1,
        "due_on": now,
        "last_reviewed_on": now - timedelta(days=2),
    })
    result = {
        "conceptId": "word-1",
        "correct": True,
        "authoritativeResolved": True,
        "activityType": "scheduled_maintenance",
        "sourceResponseId": "response-1",
    }

    assert apply_srs_updates(db, "student-1", [result], now=now) == 1
    assert apply_srs_updates(db, "student-1", [result], now=now) == 0
    assert len(db.events) == 1
    assert len(db.upserts) == 1

    # A response before the scheduled due instant is ignored even with a new
    # source identity, so manually replaying early cannot push the due date.
    early = dict(result, sourceResponseId="response-early")
    assert apply_srs_updates(db, "student-1", [early], now=now + timedelta(hours=1)) == 0
    assert len(db.events) == 1


def test_personalized_practice_never_advances_srs():
    now = _dt(1)
    db = _IdempotentDb({
        "word_id": "word-1",
        "reps": 2,
        "ease": 2.5,
        "interval_days": 6,
        "due_on": now,
        "last_reviewed_on": now - timedelta(days=7),
    })
    result = {
        "conceptId": "word-1",
        "correct": True,
        "authoritativeResolved": True,
        "activityType": "personalized_practice",
        "sourceResponseId": "practice-1",
    }
    assert apply_srs_updates(db, "student-1", [result], now=now) == 0
    assert not db.events
    assert not db.upserts
