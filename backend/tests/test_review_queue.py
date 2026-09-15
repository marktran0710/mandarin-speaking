from datetime import date

from analytics.review_queue import combine_review_queue
from analytics.srs import SrsState
from analytics.srs_store import apply_srs_updates, load_srs_states, upsert_srs_state


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor(self._rows)


TODAY = date(2026, 2, 10)


def _mastery(word_id, obs, status="NEEDS_REVIEW", p=0.4):
    return {"wordId": word_id, "word": word_id, "observationCount": obs, "pLearned": p, "status": status}


def test_combine_puts_due_words_first_then_weak_and_tags_reasons():
    weak = [_mastery("A", 5)]                       # genuinely weak (BKT)
    mastery = [_mastery("A", 5), _mastery("B", 8, "MASTERED", 0.98), _mastery("C", 3, "MASTERED", 0.97)]
    srs = {
        "B": SrsState(reps=3, ease=2.7, interval_days=16, due_on=date(2026, 2, 8)),   # overdue
        "C": SrsState(reps=2, ease=2.6, interval_days=6, due_on=date(2026, 2, 20)),   # not due yet
    }

    queue = combine_review_queue(weak, mastery, srs, TODAY)

    # B (due) comes before A (weak); C is not due so it is absent.
    assert [row["wordId"] for row in queue] == ["B", "A"]
    assert queue[0]["reviewReason"] == "due" and queue[0]["dueOn"] == "2026-02-08"
    assert queue[1]["reviewReason"] == "weak"
    # A mastered-but-due word is NEVER relabelled weak.
    assert queue[0]["status"] == "MASTERED"


def test_combine_orders_multiple_due_by_most_overdue_first():
    mastery = [_mastery("X", 4, "MASTERED"), _mastery("Y", 4, "MASTERED")]
    srs = {
        "X": SrsState(reps=2, ease=2.5, interval_days=6, due_on=date(2026, 2, 9)),
        "Y": SrsState(reps=2, ease=2.5, interval_days=6, due_on=date(2026, 2, 1)),  # more overdue
    }
    queue = combine_review_queue([], mastery, srs, TODAY)
    assert [row["wordId"] for row in queue] == ["Y", "X"]


def test_combine_skips_due_word_with_no_mastery_or_zero_observations():
    srs = {"ghost": SrsState(reps=1, ease=2.5, interval_days=1, due_on=date(2026, 2, 1))}
    assert combine_review_queue([], [], srs, TODAY) == []
    assert combine_review_queue([], [_mastery("ghost", 0)], srs, TODAY) == []


def test_combine_does_not_duplicate_a_word_that_is_both_weak_and_due():
    weak = [_mastery("A", 5)]
    srs = {"A": SrsState(reps=1, ease=2.5, interval_days=1, due_on=date(2026, 2, 1))}
    queue = combine_review_queue(weak, [_mastery("A", 5)], srs, TODAY)
    assert [row["wordId"] for row in queue] == ["A"]
    assert queue[0]["reviewReason"] == "weak"   # weak wins the dedup


def test_store_loads_states_and_parses_dates():
    db = _FakeDB(rows=[{
        "word_id": "B", "reps": 3, "ease": 2.7, "interval_days": 16,
        "due_on": date(2026, 2, 8), "last_reviewed_on": "2026-01-23T00:00:00Z",
    }])
    states = load_srs_states(db, "s1", ["B"])
    assert states["B"] == SrsState(reps=3, ease=2.7, interval_days=16,
                                    due_on=date(2026, 2, 8), last_reviewed_on=date(2026, 1, 23))
    # Scoped query binds the id list.
    assert "ANY(%s)" in db.calls[0][0] and db.calls[0][1] == ("s1", ["B"])


def test_store_empty_word_scope_skips_query():
    db = _FakeDB()
    assert load_srs_states(db, "s1", []) == {}
    assert db.calls == []


def _inserts(db):
    return [c for c in db.calls if "INSERT INTO student_vocab_srs" in c[0]]


def test_apply_srs_updates_schedules_a_new_word_on_correct():
    db = _FakeDB(rows=[])  # no existing schedule
    n = apply_srs_updates(db, "s1", [{"conceptId": "A", "correct": True, "timeMs": 900}], today=TODAY)
    assert n == 1
    params = _inserts(db)[0][1]
    # (student, word, reps, ease, interval, due_on, last_reviewed_on, ...)
    assert params[1] == "A" and params[2] == 1 and params[4] == 1
    assert params[5] == date(2026, 2, 11) and params[6] == TODAY


def test_apply_srs_updates_takes_the_last_answer_for_a_word():
    db = _FakeDB(rows=[])
    n = apply_srs_updates(db, "s1", [
        {"conceptId": "A", "correct": False, "timeMs": 100},
        {"conceptId": "A", "correct": True, "timeMs": 100},
    ], today=TODAY)
    assert n == 1 and len(_inserts(db)) == 1  # one word, last (correct) answer wins


def test_apply_srs_updates_skips_a_word_already_reviewed_today():
    db = _FakeDB(rows=[{
        "word_id": "A", "reps": 2, "ease": 2.6, "interval_days": 6,
        "due_on": date(2026, 2, 16), "last_reviewed_on": TODAY,
    }])
    n = apply_srs_updates(db, "s1", [{"conceptId": "A", "correct": True, "timeMs": 100}], today=TODAY)
    assert n == 0 and _inserts(db) == []


def test_apply_srs_updates_ignores_results_without_word_or_correctness():
    db = _FakeDB(rows=[])
    n = apply_srs_updates(db, "s1", [{"correct": True}, {"conceptId": "A"}], today=TODAY)
    assert n == 0 and _inserts(db) == []


def test_store_upsert_binds_all_columns():
    db = _FakeDB()
    upsert_srs_state(db, "s1", "B", SrsState(reps=3, ease=2.7, interval_days=16, due_on=date(2026, 2, 8), last_reviewed_on=date(2026, 2, 2)))
    sql, params = db.calls[0]
    assert "INSERT INTO student_vocab_srs" in sql and "ON CONFLICT" in sql
    assert params[:6] == ("s1", "B", 3, 2.7, 16, date(2026, 2, 8))
