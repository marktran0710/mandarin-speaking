"""Modified SM-2 spaced-repetition scheduler for vocabulary review.

Pure SCHEDULING only: this decides which words are due and when to show them
again. It never touches BKT mastery (``p_learned``) or its calibration — a
review's correctness still flows into BKT unchanged (see analytics/bkt_mastery).

Algorithm: the SM-2 scheme from P. Woźniak, "Optimization of learning"
(SuperMemo, 1990) — an ease factor plus expanding intervals. The learner UI
grades answers correct/incorrect (not the SM-2 0..5 self-rating), and the
quality grade is fixed at q=4 for correct or q=2 for incorrect.

Timing runs on real ``datetime`` instants, not calendar ``date``s, so a "day"
can be compressed for fast manual/demo testing (see ``day_seconds`` below)
without losing sub-day precision. ``interval_days`` keeps counting whole "day"
units exactly as before — only how long one such unit lasts in wall-clock time
changes. Every function defaults to a real 24h day, so existing callers that
never pass ``day_seconds`` are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

INITIAL_EASE = 2.5
MIN_EASE = 1.3
FIRST_INTERVAL_DAYS = 1
SECOND_INTERVAL_DAYS = 6
PASS_QUALITY = 3  # q >= 3 counts as a successful recall
# Binary UI results use q=4 for correct and q=2 for incorrect. Response time
# is retained in the event data but does not affect the schedule.
SRS_ALGORITHM_VERSION = "modified-sm2-v1"
# How long one scheduling "day" lasts in real time. Callers may pass a smaller
# value (e.g. from an env-configured dev setting) to compress the whole SM-2
# cycle into minutes/hours for manual testing or a live demo, without changing
# the interval-count math at all — see ``review``/``should_advance`` below.
DAY_SECONDS = 86400.0


@dataclass(frozen=True)
class SrsState:
    reps: int = 0
    ease: float = INITIAL_EASE
    interval_days: int = 0
    due_on: datetime | None = None
    last_reviewed_on: datetime | None = None


def quality_from_response(
    correct: bool,
    _time_ms: int | None = None,
    _fast_threshold_ms: int | None = None,
) -> int:
    """Map binary correctness to the research scheduler quality.

    Timing arguments remain accepted for compatibility with older callers but
    are intentionally ignored. A single speed threshold is not comparable
    across MCQ, pinyin typing, and contextual tasks.
    """
    return 4 if correct else 2


def _updated_ease(ease: float, q: int) -> float:
    ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    return max(MIN_EASE, ease)


def review(state: SrsState, q: int, now: datetime, *, day_seconds: float = DAY_SECONDS) -> SrsState:
    """Apply one modified-SM-2 review, returning the next state.

    ``interval_days`` is still a plain count of "day" units (1, 6, then
    ease-scaled); ``day_seconds`` only sets how long one unit lasts in real
    time when converting that count into ``due_on``. Callers enforce "advance
    at most once per day" with ``should_advance`` so that repeated practice
    within a session does not keep pushing the interval out — SM-2 assumes a
    single graded review per due cycle.
    """
    previous_ease = state.ease
    if q >= PASS_QUALITY:
        if state.reps == 0:
            interval = FIRST_INTERVAL_DAYS
        elif state.reps == 1:
            interval = SECOND_INTERVAL_DAYS
        else:
            interval = max(1, round(state.interval_days * previous_ease))
        reps = state.reps + 1
    else:
        reps = 0
        interval = FIRST_INTERVAL_DAYS
    ease = _updated_ease(previous_ease, q)
    return SrsState(
        reps=reps,
        ease=ease,
        interval_days=interval,
        due_on=now + timedelta(seconds=interval * day_seconds),
        last_reviewed_on=now,
    )


def should_advance(state: SrsState, now: datetime, *, day_seconds: float = DAY_SECONDS) -> bool:
    """Whether a graded review should move the schedule now.

    SM-2 grades one review per due cycle; within-cycle repeats keep practicing
    but must not advance the interval again. A full ``day_seconds`` must have
    elapsed since the last graded review, rather than checking for a different
    calendar date — the latter breaks down once a "day" is compressed to
    minutes, where several cycles can fall on the same calendar date.
    """
    return state.last_reviewed_on is None or (now - state.last_reviewed_on) >= timedelta(seconds=day_seconds)


def is_due(state: SrsState, now: datetime) -> bool:
    """A word is due when its scheduled time has arrived (or it has none yet)."""
    return state.due_on is None or state.due_on <= now
