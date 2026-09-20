from datetime import datetime, timedelta, timezone

from analytics.review_queue import combine_review_queue
from analytics.srs import SrsState
from analytics.srs_store import apply_srs_updates, enroll_strong_words, load_srs_states, upsert_srs_state


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "INSERT INTO student_vocab_srs_events" in sql:
            return _Cursor([{"id": len(_events(self)) + 1}])
        return _Cursor(self._rows)


def _dt(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


TODAY = _dt(2026, 2, 10)


def _mastery(word_id, obs, status="NEEDS_PRACTICE", p=0.4):
    return {"wordId": word_id, "word": word_id, "observationCount": obs, "pLearned": p, "status": status}


def test_combine_puts_due_words_first_then_weak_and_tags_reasons():
    weak = [_mastery("A", 5)]                       # genuinely weak (BKT)
    mastery = [_mastery("A", 5), _mastery("B", 8, "STRONG", 0.98), _mastery("C", 3, "STRONG", 0.97)]
    srs = {
        "B": SrsState(reps=3, ease=2.7, interval_days=16, due_on=_dt(2026, 2, 8)),   # overdue
        "C": SrsState(reps=2, ease=2.6, interval_days=6, due_on=_dt(2026, 2, 20)),   # not due yet
    }

    queue = combine_review_queue(weak, mastery, srs, TODAY)

    # B (due) comes before A (weak); C is not due so it is absent.
    assert [row["wordId"] for row in queue] == ["B", "A"]
    assert queue[0]["reviewReason"] == "due" and queue[0]["dueOn"] == "2026-02-08T00:00:00+00:00"
    assert queue[1]["reviewReason"] == "weak"
    # A strong-but-due word is NEVER relabelled weak.
    assert queue[0]["status"] == "STRONG"


def test_combine_orders_multiple_due_by_most_overdue_first():
    mastery = [_mastery("X", 4, "STRONG"), _mastery("Y", 4, "STRONG")]
    srs = {
        "X": SrsState(reps=2, ease=2.5, interval_days=6, due_on=_dt(2026, 2, 9)),
        "Y": SrsState(reps=2, ease=2.5, interval_days=6, due_on=_dt(2026, 2, 1)),  # more overdue
    }
    queue = combine_review_queue([], mastery, srs, TODAY)
    assert [row["wordId"] for row in queue] == ["Y", "X"]


def test_combine_skips_due_word_with_no_mastery_or_zero_observations():
    srs = {"ghost": SrsState(reps=1, ease=2.5, interval_days=1, due_on=_dt(2026, 2, 1))}
    assert combine_review_queue([], [], srs, TODAY) == []
    assert combine_review_queue([], [_mastery("ghost", 0)], srs, TODAY) == []


def test_combine_does_not_duplicate_a_word_that_is_both_weak_and_due():
    weak = [_mastery("A", 5)]
    srs = {"A": SrsState(reps=1, ease=2.5, interval_days=1, due_on=_dt(2026, 2, 1))}
    queue = combine_review_queue(weak, [_mastery("A", 5)], srs, TODAY)
    assert [row["wordId"] for row in queue] == ["A"]
    assert queue[0]["reviewReason"] == "weak"   # weak wins the dedup


def test_store_loads_states_and_parses_dates():
    db = _FakeDB(rows=[{
        "word_id": "B", "reps": 3, "ease": 2.7, "interval_days": 16,
        "due_on": _dt(2026, 2, 8), "last_reviewed_on": "2026-01-23T00:00:00Z",
    }])
    states = load_srs_states(db, "s1", ["B"])
    assert states["B"] == SrsState(reps=3, ease=2.7, interval_days=16,
                                    due_on=_dt(2026, 2, 8), last_reviewed_on=_dt(2026, 1, 23))
    # Scoped query binds the id list.
    assert "ANY(%s)" in db.calls[0][0] and db.calls[0][1] == ("s1", ["B"])


def test_store_empty_word_scope_skips_query():
    db = _FakeDB()
    assert load_srs_states(db, "s1", []) == {}
    assert db.calls == []


def _inserts(db):
    return [c for c in db.calls if "INSERT INTO student_vocab_srs\n" in c[0]]


def _events(db):
    return [c for c in db.calls if "INSERT INTO student_vocab_srs_events" in c[0]]


def test_apply_srs_updates_skips_an_unenrolled_word():
    db = _FakeDB(rows=[])  # no existing schedule
    n = apply_srs_updates(db, "s1", [{"conceptId": "A", "correct": True, "timeMs": 900, "sourceResponseId": "r-1", "authoritativeResolved": True}], now=TODAY)
    assert n == 0
    assert _inserts(db) == []
    assert _events(db) == []


def test_apply_srs_updates_ignores_unresolved_client_correctness():
    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 1, "ease": 2.5, "interval_days": 1,
        "due_on": TODAY, "last_reviewed_on": TODAY - timedelta(days=2),
    }])
    n = apply_srs_updates(
        db,
        "s1",
        [{
            "conceptId": "A", "correct": True, "timeMs": 900,
            "sourceResponseId": "unresolved-item", "authoritativeResolved": False,
        }],
        now=TODAY,
    )
    assert n == 0
    assert _inserts(db) == []
    assert _events(db) == []


def test_enroll_strong_words_starts_a_schedule_without_grading_a_review():
    db = _FakeDB(rows=[])
    n = enroll_strong_words(
        db,
        "s1",
        [{"wordId": "A", "vocabularyState": {"review": {"status": "STRONG"}}}],
        now=TODAY,
    )
    assert n == 1
    params = _inserts(db)[0][1]
    assert params[1] == "A" and params[2] == 1 and params[4] == 1
    assert params[5] == _dt(2026, 2, 11) and params[6] == TODAY
    assert params[3] == 2.5
    assert len(_events(db)) == 1
    assert _events(db)[0][1][5] == "enrollment"


def test_enroll_strong_words_never_overwrites_an_existing_schedule():
    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 2, "ease": 2.6, "interval_days": 6,
        "due_on": _dt(2026, 2, 16), "last_reviewed_on": _dt(2026, 2, 4),
    }])
    n = enroll_strong_words(
        db,
        "s1",
        [{"wordId": "A", "vocabularyState": {"review": {"status": "STRONG"}}}],
        now=TODAY,
    )
    assert n == 0 and _inserts(db) == []


def test_apply_srs_updates_takes_the_last_answer_for_a_word():
    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 1, "ease": 2.5, "interval_days": 1,
        "due_on": _dt(2026, 2, 10), "last_reviewed_on": _dt(2026, 2, 9),
    }])
    n = apply_srs_updates(db, "s1", [
        {"conceptId": "A", "correct": False, "timeMs": 100},
        {"conceptId": "A", "correct": True, "timeMs": 100, "sourceResponseId": "r-2", "authoritativeResolved": True},
    ], now=TODAY)
    assert n == 1 and len(_inserts(db)) == 1  # one word, last (correct) answer wins


def test_apply_srs_updates_skips_a_word_already_reviewed_today():
    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 2, "ease": 2.6, "interval_days": 6,
        "due_on": _dt(2026, 2, 16), "last_reviewed_on": TODAY,
    }])
    n = apply_srs_updates(db, "s1", [{"conceptId": "A", "correct": True, "timeMs": 100, "sourceResponseId": "r-4", "authoritativeResolved": True}], now=TODAY)
    assert n == 0 and _inserts(db) == []


def test_apply_srs_updates_does_not_advance_a_word_before_its_due_time():
    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 2, "ease": 2.6, "interval_days": 6,
        "due_on": _dt(2026, 2, 16), "last_reviewed_on": _dt(2026, 2, 4),
    }])
    n = apply_srs_updates(db, "s1", [{"conceptId": "A", "correct": True, "timeMs": 100, "sourceResponseId": "r-3", "authoritativeResolved": True}], now=TODAY)
    assert n == 0 and _inserts(db) == []


def test_apply_srs_updates_ignores_results_without_word_or_correctness():
    db = _FakeDB(rows=[])
    n = apply_srs_updates(db, "s1", [{"correct": True}, {"conceptId": "A"}], now=TODAY)
    assert n == 0 and _inserts(db) == []


def test_apply_srs_updates_honors_a_compressed_day_length():
    from datetime import timedelta

    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 1, "ease": 2.5, "interval_days": 1,
        "due_on": TODAY, "last_reviewed_on": TODAY - timedelta(minutes=2),
    }])
    n = apply_srs_updates(
        db, "s1", [{"conceptId": "A", "correct": True, "timeMs": 900, "sourceResponseId": "r-5", "authoritativeResolved": True}],
        now=TODAY, day_seconds=60.0,
    )
    assert n == 1
    params = _inserts(db)[0][1]
    assert params[5] == TODAY + timedelta(minutes=6)  # second success: 6 "days" == 6 minutes


def test_apply_srs_updates_ignores_corrective_practice_even_when_enrolled():
    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 1, "ease": 2.5, "interval_days": 1,
        "due_on": TODAY, "last_reviewed_on": TODAY - timedelta(days=2),
    }])

    n = apply_srs_updates(
        db,
        "s1",
        [{"conceptId": "A", "correct": True, "activityType": "personalized_practice", "authoritativeResolved": True}],
        now=TODAY,
    )

    assert n == 0
    assert _inserts(db) == []
    assert _events(db) == []


def test_store_upsert_binds_all_columns():
    db = _FakeDB()
    upsert_srs_state(db, "s1", "B", SrsState(reps=3, ease=2.7, interval_days=16, due_on=_dt(2026, 2, 8), last_reviewed_on=_dt(2026, 2, 2)))
    sql, params = db.calls[0]
    assert "INSERT INTO student_vocab_srs" in sql and "ON CONFLICT" in sql
    assert params[:6] == ("s1", "B", 3, 2.7, 16, _dt(2026, 2, 8))
