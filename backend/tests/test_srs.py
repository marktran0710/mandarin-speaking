from datetime import date

from analytics.srs import (
    INITIAL_EASE,
    MIN_EASE,
    SrsState,
    is_due,
    quality_from_response,
    review,
    should_advance,
)


def test_quality_from_response_maps_correctness_and_speed():
    assert quality_from_response(False, 500, 5000) == 2       # wrong -> reset grade
    assert quality_from_response(True, 900, 5000) == 5        # correct + fast
    assert quality_from_response(True, 9000, 5000) == 4       # correct + slow
    assert quality_from_response(True, None, 5000) == 4       # correct, no timing


def test_sm2_expands_intervals_on_success_then_resets_on_failure():
    """Walks the worked 錢包 example: 1 -> 6 -> 16 days, then a miss resets to 1."""
    state = SrsState()  # reps=0, ease=2.5

    # Day 0: correct + fast (q=5). First success -> 1 day; ease nudges to 2.6.
    state = review(state, 5, date(2026, 1, 1))
    assert state.reps == 1
    assert state.interval_days == 1
    assert round(state.ease, 2) == 2.6
    assert state.due_on == date(2026, 1, 2)

    # Day 1: correct + slow (q=4). Second success -> 6 days; ease unchanged at 2.6.
    state = review(state, 4, date(2026, 1, 2))
    assert state.reps == 2
    assert state.interval_days == 6
    assert round(state.ease, 2) == 2.6
    assert state.due_on == date(2026, 1, 8)

    # Day 7: correct + fast (q=5). round(6 * 2.6) = 16 days; ease -> 2.7.
    state = review(state, 5, date(2026, 1, 8))
    assert state.reps == 3
    assert state.interval_days == 16
    assert round(state.ease, 2) == 2.7

    # A miss (q=2): reset to 1 day, reps 0, ease drops (2.7 - 0.32 = 2.38).
    missed = review(state, 2, date(2026, 1, 24))
    assert missed.reps == 0
    assert missed.interval_days == 1
    assert round(missed.ease, 2) == 2.38


def test_ease_never_drops_below_floor():
    state = SrsState(reps=5, ease=1.35, interval_days=40)
    for _ in range(10):
        state = review(state, 2, date(2026, 1, 1))  # repeated failures
    assert state.ease == MIN_EASE


def test_should_advance_blocks_a_second_review_the_same_day():
    today = date(2026, 1, 1)
    state = review(SrsState(), 5, today)
    assert should_advance(state, today) is False           # already reviewed today
    assert should_advance(state, date(2026, 1, 2)) is True  # a new day


def test_is_due_uses_the_scheduled_date():
    assert is_due(SrsState(), date(2026, 1, 1)) is True                       # never scheduled
    scheduled = SrsState(due_on=date(2026, 1, 10))
    assert is_due(scheduled, date(2026, 1, 9)) is False
    assert is_due(scheduled, date(2026, 1, 10)) is True
    assert is_due(scheduled, date(2026, 1, 11)) is True


def test_first_state_uses_documented_defaults():
    assert SrsState().ease == INITIAL_EASE
    assert SrsState().reps == 0
    assert SrsState().due_on is None
