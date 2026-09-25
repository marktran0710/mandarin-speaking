"""Which words in a story are actually still "weak" for a given student.

Replaces a plain "wrong on the most recent attempt" check with a score
built from four signals:

- **ability**: this student's overall vocab-quiz ability (theta) vs. this
  word's own difficulty (b), from the joint Rasch/time fit in
  analytics/joint_time.py — gives an *expected* accuracy for this specific
  student on this specific word, so a strong student missing an easy word
  outranks a weak student missing a hard word, which raw wrong/right can't
  tell apart.
- **accuracy**: this student's own observed accuracy on the word.
- **history**: accuracy is recency-weighted across every past attempt
  (not just the latest), so one old slip doesn't outweigh a real recent
  recovery, and vice versa.
- **response time**: even a correct answer that took much longer than this
  student's own norm signals effortful, not-yet-automatic recall.

A word is still flagged "weak" unconditionally if the most recent attempt
got it wrong — this preserves the old, simpler contract as a floor. The
model can additionally flag a word that was answered *correctly* last time
but looks fragile on the combined signal; it never un-flags a word that's
currently wrong for lack of history.
"""

from dataclasses import dataclass
from math import exp, log
from statistics import median
from typing import Dict, List

# A slip several attempts back should count for much less than a recent
# one, but not for nothing — 0.65 roughly halves an occurrence's weight
# every ~1.6 attempts back.
RECENCY_DECAY = 0.65

# Below this many exposures there isn't enough history to trust the
# ability-adjusted gap or the time signal — fall back to "last attempt
# wrong" only, same as the original behavior.
MIN_EXPOSURES_FOR_MODEL = 2

# How far below the ability-expected accuracy counts as "weak" (in
# probability points). 0.15 means "this student is doing about 15 points
# worse on this word than their overall ability predicts."
GAP_THRESHOLD = 0.15

# How far above this student's own median time-residual (natural-log
# units) on correct answers counts as "unusually slow for them."
# log(1.42) ~= 0.35, i.e. ~42% slower than their own norm.
TIME_RESIDUAL_THRESHOLD = 0.35

# Flat contribution added to the weak score when the time signal fires —
# deliberately not a continuously scaled term, since the time model is the
# least precise of the four signals (no absolute intercept, see below).
TIME_BONUS = 0.15


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


@dataclass
class WordOccurrence:
    correct: bool
    time_ms: int


@dataclass
class WeakWordScore:
    word: str
    weak: bool
    weak_score: float
    p_expected: float
    p_observed: float
    exposures: int


def _recency_weighted_accuracy(occurrences: List[WordOccurrence]) -> float:
    n = len(occurrences)
    weights = [RECENCY_DECAY ** (n - 1 - i) for i in range(n)]
    total_weight = sum(weights)
    return sum(w * (1.0 if occ.correct else 0.0) for w, occ in zip(weights, occurrences)) / total_weight


def score_weak_words(
    occurrences_by_word: Dict[str, List[WordOccurrence]],
    ability: float,
    speed: float,
    difficulty_by_word: Dict[str, float],
    time_intensity_by_word: Dict[str, float],
) -> List[WeakWordScore]:
    """occurrences_by_word: chronological (oldest first) per word, across
    every past attempt for one student in one story. difficulty_by_word /
    time_intensity_by_word: this story's per-word fit values, already
    resolved by the caller (missing words default to 0.0 = "average").
    """
    # Pass 1: per-word gap and (unshifted) time residual. The time fit has
    # no absolute intercept — item_time_intensity - student_speed predicts
    # log(time) up to a missing constant shared by every response, so a raw
    # residual isn't directly interpretable. It's fine for ranking, though:
    # the missing constant is the same for every word this student sees, so
    # comparing this student's own words to their own median residual (pass
    # 2) cancels it out cleanly, no need to estimate it separately.
    raw: Dict[str, dict] = {}
    residuals: List[float] = []
    for word, occurrences in occurrences_by_word.items():
        n = len(occurrences)
        last_wrong = not occurrences[-1].correct
        p_observed = _recency_weighted_accuracy(occurrences)
        p_expected = sigmoid(ability - difficulty_by_word.get(word, 0.0))
        gap = p_expected - p_observed

        correct_times = [o.time_ms for o in occurrences if o.correct]
        residual = None
        if correct_times:
            predicted_log_time = time_intensity_by_word.get(word, 0.0) - speed
            observed_log_time = log(max(sum(correct_times) / len(correct_times), 1.0))
            residual = observed_log_time - predicted_log_time
            residuals.append(residual)

        raw[word] = {
            "n": n,
            "last_wrong": last_wrong,
            "p_observed": p_observed,
            "p_expected": p_expected,
            "gap": gap,
            "residual": residual,
        }

    # Pass 2: center time residuals on this student's own median, then
    # finalize each word's score and weak/not-weak call.
    baseline_residual = median(residuals) if residuals else 0.0

    results: List[WeakWordScore] = []
    for word, r in raw.items():
        has_model = r["n"] >= MIN_EXPOSURES_FOR_MODEL
        time_flag = (
            has_model
            and r["residual"] is not None
            and (r["residual"] - baseline_residual) > TIME_RESIDUAL_THRESHOLD
        )
        weak_score = r["gap"] + (TIME_BONUS if time_flag else 0.0) if has_model else 0.0
        # Time is a signal in its own right, not just a tiebreaker on the
        # accuracy gap — a word answered correctly every time but always
        # much slower than this student's norm is exactly the "not yet
        # automatic" case time is meant to catch, and a strongly negative
        # gap (near-perfect accuracy) would otherwise always outweigh it if
        # the two were only ever summed before thresholding.
        weak = r["last_wrong"] or (has_model and (r["gap"] > GAP_THRESHOLD or time_flag))
        results.append(
            WeakWordScore(
                word=word,
                weak=weak,
                weak_score=weak_score if has_model else (1.0 if r["last_wrong"] else 0.0),
                p_expected=r["p_expected"],
                p_observed=r["p_observed"],
                exposures=r["n"],
            )
        )

    return results
