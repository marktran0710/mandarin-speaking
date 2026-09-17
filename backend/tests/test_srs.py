from datetime import datetime, timedelta, timezone

from analytics.srs import (
    DAY_SECONDS,
    INITIAL_EASE,
    MIN_EASE,
    SrsState,
    is_due,
    quality_from_response,
    review,
    should_advance,
)


def _dt(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_quality_from_response_is_format_agnostic_and_ignores_timing():
    assert quality_from_response(False, 500, 5000) == 2
    assert quality_from_response(True, 900, 5000) == 4
    assert quality_from_response(True, 9000, 5000) == 4
    assert quality_from_response(True, None, 5000) == 4


def test_sm2_expands_intervals_on_success_then_resets_on_failure():
    """Walks the worked 錢包 example: 1 -> 6 -> 16 days, then a miss resets to 1."""
    state = SrsState()  # reps=0, ease=2.5

    # Day 0: correct + fast (q=5). First success -> 1 day; ease nudges to 2.6.
    state = review(state, 4, _dt(2026, 1, 1))
    assert state.reps == 1
    assert state.interval_days == 1
    assert round(state.ease, 2) == 2.5
    assert state.due_on == _dt(2026, 1, 2)

    # Day 1: correct + slow (q=4). Second success -> 6 days; ease unchanged at 2.6.
    state = review(state, 4, _dt(2026, 1, 2))
    assert state.reps == 2
    assert state.interval_days == 6
    assert round(state.ease, 2) == 2.5
    assert state.due_on == _dt(2026, 1, 8)

    # Day 7: correct + fast (q=5). round(6 * 2.6) = 16 days; ease -> 2.7.
    state = review(state, 4, _dt(2026, 1, 8))
    assert state.reps == 3
    assert state.interval_days == 15
    assert round(state.ease, 2) == 2.5

    # A miss (q=2): reset to 1 day, reps 0, ease drops (2.7 - 0.32 = 2.38).
    missed = review(state, 2, _dt(2026, 1, 24))
    assert missed.reps == 0
    assert missed.interval_days == 1
    assert round(missed.ease, 2) == 2.18


def test_ease_never_drops_below_floor():
    state = SrsState(reps=5, ease=1.35, interval_days=40)
    for _ in range(10):
        state = review(state, 2, _dt(2026, 1, 1))  # repeated failures
    assert state.ease == MIN_EASE


def test_should_advance_blocks_a_second_review_the_same_day():
    now = _dt(2026, 1, 1)
    state = review(SrsState(), 5, now)
    assert should_advance(state, now) is False                      # immediately after
    assert should_advance(state, now + timedelta(hours=23)) is False  # still within the day
    assert should_advance(state, now + timedelta(days=1)) is True     # a full day later


def test_is_due_uses_the_scheduled_time():
    assert is_due(SrsState(), _dt(2026, 1, 1)) is True                        # never scheduled
    scheduled = SrsState(due_on=_dt(2026, 1, 10))
    assert is_due(scheduled, _dt(2026, 1, 9)) is False
    assert is_due(scheduled, _dt(2026, 1, 10)) is True
    assert is_due(scheduled, _dt(2026, 1, 11)) is True


def test_first_state_uses_documented_defaults():
    assert SrsState().ease == INITIAL_EASE
    assert SrsState().reps == 0
    assert SrsState().due_on is None


def test_day_seconds_compresses_the_whole_cycle_without_changing_interval_counts():
    """A dev/demo speedup: the same 1 -> 6 -> 16 day-count progression, but each
    "day" only lasts a minute of wall-clock time — for watching the schedule
    advance live instead of waiting real days."""
    one_minute = 60.0
    now = _dt(2026, 1, 1, 0, 0)

    state = review(SrsState(), 5, now, day_seconds=one_minute)
    assert state.interval_days == 1
    assert state.due_on == now + timedelta(minutes=1)
    assert is_due(state, now + timedelta(seconds=30)) is False
    assert is_due(state, now + timedelta(minutes=1)) is True

    # "Once per compressed day": a second review 30s later must not advance,
    # but one a full compressed day later does.
    assert should_advance(state, now + timedelta(seconds=30), day_seconds=one_minute) is False
    assert should_advance(state, now + timedelta(minutes=1), day_seconds=one_minute) is True

    state = review(state, 4, now + timedelta(minutes=1), day_seconds=one_minute)
    assert state.interval_days == 6
    assert state.due_on == now + timedelta(minutes=7)


def test_default_day_seconds_is_a_real_24h_day():
    assert DAY_SECONDS == 86400.0
