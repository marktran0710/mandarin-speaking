"""Pure Bayesian Knowledge Tracing primitives used by vocabulary review.

This module intentionally contains no database or HTTP code.  It is the one
place where the production recommendation path performs the BKT calculation.
The defaults are engineering defaults for the first research version, not
validated or calibrated cutoffs.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite
from typing import Iterable


BKT_MIN_PROBABILITY = 0.000001
BKT_MAX_PROBABILITY = 0.999999
BKT_MIN_DISCRIMINATION = 0.001


def _validate_probability(name: str, value: float) -> None:
    if not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a finite probability in [0, 1]")


def _validate_guess_slip(guess_name: str, guess: float, slip_name: str, slip: float) -> None:
    _validate_probability(guess_name, guess)
    _validate_probability(slip_name, slip)
    if 1.0 - slip < guess + BKT_MIN_DISCRIMINATION:
        raise ValueError(
            f"BKT requires 1 - {slip_name} to be meaningfully greater than {guess_name}"
        )


@dataclass(frozen=True)
class BktConfig:
    initial_mastery: float = 0.20
    # guess_rate/slip_rate are the multiple-choice defaults. Free-text (typed)
    # answers are near-impossible to guess but easy to slip on (a tone mark, a
    # space), so they take their own pair — see guess_slip_for(). One global
    # pair muddied both formats at once (a correct typed answer was
    # under-rewarded; a typo was over-punished).
    learn_rate: float = 0.15
    guess_rate: float = 0.20
    slip_rate: float = 0.10
    guess_rate_typed: float = 0.05
    slip_rate_typed: float = 0.15
    mastery_threshold: float = 0.95
    minimum_observations: int = 3
    required_diagnostic_quizzes: int = 3
    review_count: int = 5

# Question types whose answer is free text the learner types (no options to
# guess from). Everything else is treated as multiple choice.
TYPED_QUESTION_TYPES = frozenset({
    "character_to_pinyin_typing",
    "contextual_productive_recall",
    "productive_recall",
})


BKT_SUPPORTED_QUESTION_TYPES = frozenset({
    "basic_meaning_mcq",
    "context_cloze_mcq",
    *TYPED_QUESTION_TYPES,
})
BKT_QUESTION_ANSWER_FORMATS = {
    "basic_meaning_mcq": "single_choice",
    "context_cloze_mcq": "single_choice",
    "character_to_pinyin_typing": "free_text",
    "contextual_productive_recall": "free_text",
    "productive_recall": "free_text",
}


# TODO: replace with pilot-calibrated/frozen BKT parameters before the main
# experiment. These transparent temporary defaults are not research-validated.
BKT_CONFIG = BktConfig()
# Versioned provenance for persisted cache rows. Changing this intentionally
# requires a reviewed model release; it does not alter the BKT calculation.
BKT_MODEL_VERSION = "format-aware-bkt-v2"


def bkt_parameter_fingerprint(params: BktConfig = BKT_CONFIG) -> str:
    """Stable fingerprint of the exact configuration used for a replay."""
    values = {name: getattr(params, name) for name in BktConfig.__dataclass_fields__}
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()

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
    for name in ("initial_mastery", "learn_rate", "mastery_threshold"):
        _validate_probability(name, getattr(params, name))
    _validate_guess_slip("guess_rate", params.guess_rate, "slip_rate", params.slip_rate)
    _validate_guess_slip("guess_rate_typed", params.guess_rate_typed, "slip_rate_typed", params.slip_rate_typed)
    if params.minimum_observations < 1 or params.required_diagnostic_quizzes < 1 or params.review_count < 1:
        raise ValueError("BKT count settings must be positive")


def guess_slip_for(question_type: str | None, params: BktConfig = BKT_CONFIG) -> tuple[float, float]:
    """The (guess, slip) pair for one observation, chosen by answer format.

    Typed free-text answers use the typed pair (near-zero guess, higher slip);
    multiple choice uses the default pair.
    """
    if question_type and str(question_type).strip().lower() in TYPED_QUESTION_TYPES:
        return params.guess_rate_typed, params.slip_rate_typed
    return params.guess_rate, params.slip_rate


def is_supported_bkt_question_shape(question_type: str | None, answer_format: str | None = None) -> bool:
    kind = str(question_type or "").strip().lower()
    if kind not in BKT_SUPPORTED_QUESTION_TYPES:
        return False
    if not answer_format:
        return True
    return str(answer_format).strip().lower() == BKT_QUESTION_ANSWER_FORMATS[kind]


def update_bkt(
    current_mastery: float,
    correct: bool,
    params: BktConfig = BKT_CONFIG,
    *,
    guess: float | None = None,
    slip: float | None = None,
) -> float:
    """Return the next P(Learned) after one binary response.

    The observation update is standard BKT: infer a posterior from guess/slip,
    then apply the learning transition. Response time is deliberately absent.
    ``guess``/``slip`` override the config pair for a single observation (used
    to apply format-aware rates — see guess_slip_for); omitted, they fall back
    to the config's multiple-choice defaults.
    """
    _validate_config(params)
    g = params.guess_rate if guess is None else guess
    s = params.slip_rate if slip is None else slip
    _validate_guess_slip("guess", g, "slip", s)
    p = clamp_probability(current_mastery)
    if correct:
        numerator = p * (1.0 - s)
        denominator = numerator + (1.0 - p) * g
    else:
        numerator = p * s
        denominator = numerator + (1.0 - p) * (1.0 - g)
    posterior = numerator / denominator if denominator > 0.0 else p
    return clamp_probability(posterior + (1.0 - posterior) * params.learn_rate)


def replay_bkt(
    responses: Iterable[bool],
    params: BktConfig = BKT_CONFIG,
    *,
    initial_mastery: float | None = None,
) -> float:
    """Replay binary correct/incorrect with the default (multiple-choice) rates.

    Retained for callers without per-response question types; the format-aware
    path is replay_bkt_typed.
    """
    mastery = params.initial_mastery if initial_mastery is None else initial_mastery
    for correct in responses:
        mastery = update_bkt(mastery, correct, params)
    return clamp_probability(mastery)


def replay_bkt_typed(
    responses: Iterable[tuple[bool, str | None]],
    params: BktConfig = BKT_CONFIG,
    *,
    initial_mastery: float | None = None,
) -> float:
    """Replay (correct, question_type) responses with format-aware guess/slip."""
    mastery = params.initial_mastery if initial_mastery is None else initial_mastery
    for correct, question_type in responses:
        guess, slip = guess_slip_for(question_type, params)
        mastery = update_bkt(mastery, bool(correct), params, guess=guess, slip=slip)
    return clamp_probability(mastery)


def mastery_status(observation_count: int, p_learned: float, *, selected_for_review: bool = False, params: BktConfig = BKT_CONFIG) -> str:
    """Return the BKT/model status, not a durable learner achievement.

    Personalized-practice completion and scheduled review are separate state
    machines.  A high probability is therefore reported as ``STRONG`` and
    never as a durable completion label.
    """
    if observation_count < params.minimum_observations:
        return "UNASSESSED"
    if p_learned >= params.mastery_threshold:
        return "STRONG"
    if selected_for_review:
        return "NEEDS_PRACTICE"
    return "DEVELOPING"
