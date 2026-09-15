"""SM-2 spaced-repetition scheduler for vocabulary review.

Pure SCHEDULING only: this decides which words are due and when to show them
again. It never touches BKT mastery (``p_learned``) or its calibration — a
review's correctness still flows into BKT unchanged (see analytics/bkt_mastery).

Algorithm: the SM-2 scheme from P. Woźniak, "Optimization of learning"
(SuperMemo, 1990) — an ease factor plus expanding intervals. The learner UI
grades answers correct/incorrect (not the SM-2 0..5 self-rating), so the quality
grade ``q`` is derived from that binary result plus response time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

INITIAL_EASE = 2.5
MIN_EASE = 1.3
FIRST_INTERVAL_DAYS = 1
SECOND_INTERVAL_DAYS = 6
PASS_QUALITY = 3  # q >= 3 counts as a successful recall
# A correct answer at or under this many ms grades as a confident recall (q=5);
# slower-but-correct grades q=4. Between the MCQ (~5s) and typed (~10s) pace.
FAST_RESPONSE_MS = 5000


@dataclass(frozen=True)
class SrsState:
    reps: int = 0
    ease: float = INITIAL_EASE
    interval_days: int = 0
    due_on: date | None = None
    last_reviewed_on: date | None = None


def quality_from_response(correct: bool, time_ms: int | None, fast_threshold_ms: int) -> int:
    """Derive an SM-2 quality grade (0..5) from a binary answer + response time.

    Wrong -> 2 (a reset, but not a total blackout: an MCQ still leaves partial
    familiarity). Correct and fast -> 5; correct but slow, or with no timing,
    -> 4. This keeps the ease-factor update meaningful without adding a
    self-rating step to the UI.
    """
    if not correct:
        return 2
    if time_ms is not None and time_ms <= fast_threshold_ms:
        return 5
    return 4


def _updated_ease(ease: float, q: int) -> float:
    ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    return max(MIN_EASE, ease)


def review(state: SrsState, q: int, today: date) -> SrsState:
    """Apply one graded SM-2 review, returning the next state (intervals in days).

    Callers enforce "advance at most once per day" with ``should_advance`` so
    that repeated practice within a session does not keep pushing the interval
    out — SM-2 assumes a single graded review per due date.
    """
    ease = _updated_ease(state.ease, q)
    if q >= PASS_QUALITY:
        if state.reps == 0:
            interval = FIRST_INTERVAL_DAYS
        elif state.reps == 1:
            interval = SECOND_INTERVAL_DAYS
        else:
            interval = max(1, round(state.interval_days * ease))
        reps = state.reps + 1
    else:
        reps = 0
        interval = FIRST_INTERVAL_DAYS
    return SrsState(
        reps=reps,
        ease=ease,
        interval_days=interval,
        due_on=today + timedelta(days=interval),
        last_reviewed_on=today,
    )


def should_advance(state: SrsState, today: date) -> bool:
    """Whether a graded review should move the schedule today.

    SM-2 grades one review per due date; within-day repeats keep practicing but
    must not advance the interval again.
    """
    return state.last_reviewed_on != today


def is_due(state: SrsState, today: date) -> bool:
    """A word is due when its scheduled date has arrived (or it has none yet)."""
    return state.due_on is None or state.due_on <= today
