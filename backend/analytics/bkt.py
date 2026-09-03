"""Pure Bayesian Knowledge Tracing primitives used by vocabulary review.

This module intentionally contains no database or HTTP code.  It is the one
place where the production recommendation path performs the BKT calculation.
The defaults are engineering defaults for the first research version, not
validated or calibrated cutoffs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable


BKT_MIN_PROBABILITY = 0.000001
BKT_MAX_PROBABILITY = 0.999999


@dataclass(frozen=True)
class BktConfig:
    initial_mastery: float = 0.20
    learn_rate: float = 0.15
    guess_rate: float = 0.20
    slip_rate: float = 0.10
    mastery_threshold: float = 0.95
    minimum_observations: int = 3
    required_diagnostic_quizzes: int = 3
    review_count: int = 5


# TODO: replace with pilot-calibrated/frozen BKT parameters before the main
# experiment. These transparent temporary defaults are not research-validated.
BKT_CONFIG = BktConfig()

# Named aliases keep the research controls easy to find for admin tooling and
# future calibration work while the dataclass remains the single source of
# truth for runtime behavior.
BKT_MASTERY_THRESHOLD = BKT_CONFIG.mastery_threshold
MIN_OBSERVATIONS = BKT_CONFIG.minimum_observations
REQUIRED_DIAGNOSTIC_QUIZZES = BKT_CONFIG.required_diagnostic_quizzes
WEAK_WORD_REVIEW_COUNT = BKT_CONFIG.review_count


def clamp_probability(value: float) -> float:
    if not isfinite(value):
        raise ValueError("BKT probability must be finite")
    return min(BKT_MAX_PROBABILITY, max(BKT_MIN_PROBABILITY, value))


def _validate_config(params: BktConfig) -> None:
    for name in ("initial_mastery", "learn_rate", "guess_rate", "slip_rate", "mastery_threshold"):
        value = getattr(params, name)
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be a finite probability in [0, 1]")
    if params.minimum_observations < 1 or params.required_diagnostic_quizzes < 1 or params.review_count < 1:
        raise ValueError("BKT count settings must be positive")


def update_bkt(current_mastery: float, correct: bool, params: BktConfig = BKT_CONFIG) -> float:
    """Return the next P(Learned) after one binary response.

    The observation update is standard BKT: infer a posterior from guess/slip,
    then apply the learning transition. Response time is deliberately absent.
    """
    _validate_config(params)
    p = clamp_probability(current_mastery)
    if correct:
        numerator = p * (1.0 - params.slip_rate)
        denominator = numerator + (1.0 - p) * params.guess_rate
    else:
        numerator = p * params.slip_rate
        denominator = numerator + (1.0 - p) * (1.0 - params.guess_rate)
    posterior = numerator / denominator if denominator > 0.0 else p
    return clamp_probability(posterior + (1.0 - posterior) * params.learn_rate)


def replay_bkt(responses: Iterable[bool], params: BktConfig = BKT_CONFIG) -> float:
    mastery = params.initial_mastery
    for correct in responses:
        mastery = update_bkt(mastery, correct, params)
    return clamp_probability(mastery)


def mastery_status(observation_count: int, p_learned: float, *, selected_for_review: bool = False, params: BktConfig = BKT_CONFIG) -> str:
    if observation_count < params.minimum_observations:
        return "UNASSESSED"
    if p_learned >= params.mastery_threshold:
        return "MASTERED"
    if selected_for_review:
        return "NEEDS_REVIEW"
    return "DEVELOPING"
