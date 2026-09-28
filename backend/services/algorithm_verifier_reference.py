"""Independent mathematical oracles for the admin Algorithm Verifier.

This module deliberately has no imports from the learner model.  It accepts
plain numeric inputs so a production regression cannot make the oracle drift
with it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from typing import Any, Iterable


def _probability(value: float) -> float:
    if not isfinite(value):
        raise ValueError("probability must be finite")
    return min(0.999999, max(0.000001, float(value)))


def bkt_step(
    prior: float,
    correct: bool,
    *,
    learn_rate: float,
    guess: float,
    slip: float,
) -> dict[str, float]:
    """Return a standard BKT observation posterior and learning transition."""
    p = _probability(prior)
    if correct:
        numerator = p * (1.0 - slip)
        denominator = numerator + (1.0 - p) * guess
    else:
        numerator = p * slip
        denominator = numerator + (1.0 - p) * (1.0 - guess)
    posterior = numerator / denominator if denominator else p
    result = _probability(posterior + (1.0 - posterior) * learn_rate)
    return {
        "prior": p,
        "numerator": numerator,
        "denominator": denominator,
        "posterior": posterior,
        "resultingMastery": result,
    }


def bkt_sequence(
    observations: Iterable[dict[str, Any]],
    *,
    initial_mastery: float,
    learn_rate: float,
    mcq_guess: float,
    mcq_slip: float,
    typed_guess: float,
    typed_slip: float,
    typed_question_types: frozenset[str] = frozenset({
        "character_to_pinyin_typing",
        "contextual_productive_recall",
        "productive_recall",
    }),
) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    prior = initial_mastery
    for index, observation in enumerate(observations, start=1):
        question_type = str(observation.get("questionType") or observation.get("questionFormat") or "").strip().lower()
        typed = question_type in typed_question_types or question_type == "typed"
        guess = float(observation.get("guess", typed_guess if typed else mcq_guess))
        slip = float(observation.get("slip", typed_slip if typed else mcq_slip))
        step = bkt_step(
            prior,
            bool(observation.get("correct")),
            learn_rate=learn_rate,
            guess=guess,
            slip=slip,
        )
        trace.append({
            "step": index,
            "observation": "Correct" if observation.get("correct") else "Incorrect",
            "correct": bool(observation.get("correct")),
            "questionType": observation.get("questionType"),
            "guess": guess,
            "slip": slip,
            "learningTransition": learn_rate,
            **step,
        })
        prior = step["resultingMastery"]
    return trace


def sm2_ease(ease: float, quality: int, *, minimum_ease: float = 1.3) -> float:
    updated = float(ease) + 0.1 - (5 - int(quality)) * (0.08 + (5 - int(quality)) * 0.02)
    return max(float(minimum_ease), updated)


def sm2_transition(
    *,
    repetitions: int,
    interval_days: int,
    ease: float,
    quality: int,
    now: datetime,
    day_seconds: float,
    initial_ease: float = 2.5,
    minimum_ease: float = 1.3,
    first_interval_days: int = 1,
    second_interval_days: int = 6,
    pass_quality: int = 3,
) -> dict[str, Any]:
    """Independent modified-SM-2 transition with Python's round semantics."""
    previous_ease = float(ease)
    if quality >= pass_quality:
        if repetitions == 0:
            next_interval = first_interval_days
        elif repetitions == 1:
            next_interval = second_interval_days
        else:
            raw_interval = interval_days * previous_ease
            next_interval = max(1, round(raw_interval))
    else:
        next_interval = first_interval_days
    next_repetitions = repetitions + 1 if quality >= pass_quality else 0
    next_ease = sm2_ease(previous_ease, quality, minimum_ease=minimum_ease)
    next_due = now + timedelta(seconds=next_interval * day_seconds)
    return {
        "repetitions": next_repetitions,
        "intervalDays": next_interval,
        "ease": next_ease,
        "nextDue": next_due,
        "rawInterval": interval_days * previous_ease if repetitions >= 2 and quality >= pass_quality else None,
    }


def sm2_enrollment(*, now: datetime, day_seconds: float, initial_ease: float = 2.5, interval_days: int = 1) -> dict[str, Any]:
    """Return the independent first schedule created for a strong word."""
    next_due = now + timedelta(seconds=interval_days * day_seconds)
    return {
        "repetitions": 1,
        "intervalDays": interval_days,
        "ease": float(initial_ease),
        "nextDue": next_due,
        "lastReviewedOn": now,
    }
