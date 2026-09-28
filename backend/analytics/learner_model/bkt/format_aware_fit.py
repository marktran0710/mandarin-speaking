"""Offline fit and evaluation of the format-aware BKT model served in production.

``calibration.py`` fits the legacy single guess/slip pair and so can never be
promoted (production scores multiple-choice and typed answers with separate
pairs). This module fits the same six parameters production uses:

    P(L0), P(T), MCQ guess/slip, typed guess/slip

with the exact update arithmetic of :mod:`analytics.learner_model.bkt.core`
(clamped prior, posterior from guess/slip, then the learning transition), and
evaluates the candidate against the current serving parameters with the same
student-grouped 5-fold split, metrics and gates as the legacy report.

Identifiability is checked before fitting and reported:

* P(T) only affects a prediction once the same student answers the same word
  again. Without enough repeat answers it is held at the baseline value
  instead of being "fitted" to noise.
* A format's guess/slip pair is held at baseline when that format has too few
  answers (or no wrong / no right answers) to inform it.
* With one answer per student-word, P(L0) and guess/slip are only weakly
  separable (one accuracy number per format, several unknowns); the small
  penalty toward the baseline then decides the split, and the report flags it.

Nothing here reads or changes serving configuration.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from math import exp, isfinite, log
from typing import Any, Iterable, Sequence

import numpy as np
from scipy.optimize import minimize

from analytics.learner_model.bkt.calibration import (
    BOUND_MARGIN,
    CALIBRATION_BINS,
    FOLD_COUNT,
    MIN_DISCRIMINATION,
    _canonical_records,
    _counts,
    _metrics,
    assign_student_folds,
)
from analytics.learner_model.bkt.core import (
    BKT_CONFIG,
    BKT_MAX_PROBABILITY,
    BKT_MIN_DISCRIMINATION,
    BKT_MIN_PROBABILITY,
    BKT_MODEL_VERSION,
    TYPED_QUESTION_TYPES,
    BktConfig,
)
from analytics.learner_model.knowledge_tracing import ResponseRecord


FORMAT_AWARE_MODEL_SCOPE = BKT_MODEL_VERSION
FORMAT_AWARE_CALIBRATION_VERSION = "format-aware-bkt-calibration-v1"

PARAMETER_NAMES = ("prior", "learn", "guess", "slip", "guess_typed", "slip_typed")
# Plausibility bounds for the promotion gate (not optimizer bounds). A typed
# answer can legitimately be almost impossible to guess, so its lower guess
# bound is 0 rather than the multiple-choice 0.01.
FORMAT_AWARE_BOUNDS = {
    "prior": (0.01, 0.80),
    "learn": (0.001, 0.50),
    "guess": (0.01, 0.45),
    "slip": (0.01, 0.30),
    "guess_typed": (0.0, 0.45),
    "slip_typed": (0.01, 0.30),
}

# Identifiability thresholds (evidence needed before a parameter is fitted
# rather than held at the baseline).
MIN_TRANSITIONS_FOR_LEARN = 100
MIN_REPEAT_SEQUENCES_FOR_LEARN = 20
MIN_FORMAT_RESPONSES = 100
MIN_FORMAT_OUTCOME = 20

REGULARIZATION = 0.05
_PREDICTION_EPSILON = 1e-9


def is_typed(question_kind: str | None) -> bool:
    return bool(question_kind) and str(question_kind).strip().lower() in TYPED_QUESTION_TYPES


def baseline_parameters(config: BktConfig = BKT_CONFIG) -> dict[str, float]:
    return {
        "prior": config.initial_mastery,
        "learn": config.learn_rate,
        "guess": config.guess_rate,
        "slip": config.slip_rate,
        "guess_typed": config.guess_rate_typed,
        "slip_typed": config.slip_rate_typed,
    }


def registry_parameters(parameters: dict[str, float]) -> dict[str, float]:
    """The exact six-decimal values the NUMERIC(8,6) registry can serve."""
    return {
        name: float(Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
        for name, value in parameters.items()
    }


def config_from_parameters(parameters: dict[str, float], base: BktConfig = BKT_CONFIG) -> BktConfig:
    """Build a serving config: fitted model parameters, unchanged policy fields."""
    return BktConfig(
        initial_mastery=float(parameters["prior"]),
        learn_rate=float(parameters["learn"]),
        guess_rate=float(parameters["guess"]),
        slip_rate=float(parameters["slip"]),
        guess_rate_typed=float(parameters["guess_typed"]),
        slip_rate_typed=float(parameters["slip_typed"]),
        mastery_threshold=base.mastery_threshold,
        minimum_observations=base.minimum_observations,
        required_diagnostic_quizzes=base.required_diagnostic_quizzes,
        review_count=base.review_count,
    )


@dataclass(frozen=True)
class _Sequences:
    """Student-word answer sequences padded to a (sequence, position) grid."""

    correct: np.ndarray  # float, 1.0 / 0.0
    typed: np.ndarray  # bool
    present: np.ndarray  # bool
    count: int

    @classmethod
    def build(cls, records: Sequence[ResponseRecord]) -> "_Sequences":
        grouped: dict[tuple[str, str], list[ResponseRecord]] = {}
        for record in records:
            grouped.setdefault((record.student_id, record.concept_id), []).append(record)
        histories = list(grouped.values())
        length = max((len(history) for history in histories), default=0)
        correct = np.zeros((len(histories), length))
        typed = np.zeros((len(histories), length), dtype=bool)
        present = np.zeros((len(histories), length), dtype=bool)
        for row, history in enumerate(histories):
            for column, record in enumerate(history):
                correct[row, column] = 1.0 if record.correct else 0.0
                typed[row, column] = is_typed(record.question_kind)
                present[row, column] = True
        return cls(correct, typed, present, int(present.sum()))


def _replay(sequences: _Sequences, p: dict[str, float]) -> np.ndarray:
    """Pre-update P(correct) for every answer, using production arithmetic."""
    rows, columns = sequences.correct.shape
    predictions = np.zeros((rows, columns))
    mastery = np.full(rows, p["prior"])
    for column in range(columns):
        live = sequences.present[:, column]
        typed = sequences.typed[:, column]
        guess = np.where(typed, p["guess_typed"], p["guess"])
        slip = np.where(typed, p["slip_typed"], p["slip"])
        prior = np.clip(mastery, BKT_MIN_PROBABILITY, BKT_MAX_PROBABILITY)
        known_correct = prior * (1.0 - slip)
        probability = known_correct + (1.0 - prior) * guess
        predictions[:, column] = probability
        correct = sequences.correct[:, column] == 1.0
        numerator = np.where(correct, known_correct, prior * slip)
        denominator = np.where(correct, probability, 1.0 - probability)
        posterior = np.divide(numerator, denominator, out=prior.copy(), where=denominator > 0.0)
        updated = np.clip(posterior + (1.0 - posterior) * p["learn"], BKT_MIN_PROBABILITY, BKT_MAX_PROBABILITY)
        mastery = np.where(live, updated, mastery)
    return predictions


def _log_loss(sequences: _Sequences, p: dict[str, float]) -> float:
    if not sequences.count:
        return 0.0
    predictions = np.clip(_replay(sequences, p), _PREDICTION_EPSILON, 1.0 - _PREDICTION_EPSILON)
    likelihood = np.where(sequences.correct == 1.0, predictions, 1.0 - predictions)
    return float(-np.log(likelihood[sequences.present]).sum() / sequences.count)


def score_records(records: Sequence[ResponseRecord], parameters: dict[str, float]) -> tuple[list[bool], list[float]]:
    """Prequential (outcome, prediction) pairs in sequence order."""
    sequences = _Sequences.build(records)
    predictions = _replay(sequences, parameters)
    mask = sequences.present
    return [bool(value) for value in sequences.correct[mask]], [float(value) for value in predictions[mask]]


def identifiability(records: Sequence[ResponseRecord]) -> dict[str, Any]:
    """Which parameters this evidence can actually inform."""
    lengths = Counter((record.student_id, record.concept_id) for record in records)
    transitions = sum(length - 1 for length in lengths.values())
    repeat_sequences = sum(1 for length in lengths.values() if length >= 2)
    by_format: dict[str, dict[str, int]] = {"mcq": {"responses": 0, "correct": 0}, "typed": {"responses": 0, "correct": 0}}
    for record in records:
        bucket = by_format["typed" if is_typed(record.question_kind) else "mcq"]
        bucket["responses"] += 1
        bucket["correct"] += int(record.correct)
    for bucket in by_format.values():
        bucket["incorrect"] = bucket["responses"] - bucket["correct"]

    def format_ok(name: str) -> bool:
        bucket = by_format[name]
        return (
            bucket["responses"] >= MIN_FORMAT_RESPONSES
            and bucket["correct"] >= MIN_FORMAT_OUTCOME
            and bucket["incorrect"] >= MIN_FORMAT_OUTCOME
        )

    learn_free = transitions >= MIN_TRANSITIONS_FOR_LEARN and repeat_sequences >= MIN_REPEAT_SEQUENCES_FOR_LEARN
    free = {
        "prior": bool(records),
        "learn": learn_free,
        "mcq_pair": format_ok("mcq"),
        "typed_pair": format_ok("typed"),
    }
    warnings: list[str] = []
    if not learn_free:
        warnings.append(
            f"P(T) held at baseline: {transitions} repeat answers across {repeat_sequences} student-word "
            f"sequences (needs >= {MIN_TRANSITIONS_FOR_LEARN} and >= {MIN_REPEAT_SEQUENCES_FOR_LEARN})."
        )
    for name, key in (("MCQ", "mcq"), ("typed", "typed")):
        if not free[f"{key}_pair"]:
            bucket = by_format[key]
            warnings.append(
                f"{name} guess/slip held at baseline: {bucket['responses']} answers "
                f"({bucket['correct']} correct / {bucket['incorrect']} wrong)."
            )
    if records and repeat_sequences < max(1, len(lengths) // 2):
        warnings.append(
            "Most student-word sequences have a single answer, so P(L0) and guess/slip are only weakly "
            "separable; the split between them leans on the baseline penalty."
        )
    return {
        "sequences": len(lengths),
        "repeat_sequences": repeat_sequences,
        "transitions": transitions,
        "max_sequence_length": max(lengths.values(), default=0),
        "by_format": by_format,
        "free": free,
        "warnings": warnings,
    }


def _logit(value: float) -> float:
    clipped = min(1.0 - 1e-9, max(1e-9, value))
    return log(clipped / (1.0 - clipped))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + exp(-value))
    z = exp(value)
    return z / (1.0 + z)


def _pair_to_raw(guess: float, slip: float) -> tuple[float, float]:
    # Guess is scaled into [0, 1 - d); the second coordinate places p(correct |
    # learned) strictly above guess, so every candidate keeps 1 - slip > guess.
    d = BKT_MIN_DISCRIMINATION
    known_correct = 1.0 - slip
    return (
        _logit(guess / (1.0 - d)),
        _logit((known_correct - guess - d) / (1.0 - d - guess)),
    )


def _raw_to_pair(raw_guess: float, raw_known: float) -> tuple[float, float]:
    d = BKT_MIN_DISCRIMINATION
    guess = _sigmoid(raw_guess) * (1.0 - d)
    known_correct = guess + d + (1.0 - d - guess) * _sigmoid(raw_known)
    return guess, 1.0 - known_correct


def fit_format_aware_parameters(
    records: Sequence[ResponseRecord],
    *,
    baseline: dict[str, float] | None = None,
    iterations: int = 200,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Maximum-likelihood fit of the free parameters; the rest stay at baseline."""
    base = dict(baseline or baseline_parameters())
    ordered = _canonical_records(records)
    if not ordered:
        return base, {"status": "not_run", "optimizer": "L-BFGS-B", "message": "No training records.",
                      "iterations": 0, "objective": None, "finite": True, "free": []}
    ident = identifiability(ordered)
    free = ident["free"]
    sequences = _Sequences.build(ordered)

    blocks: list[tuple[str, ...]] = []
    if free["prior"]:
        blocks.append(("prior",))
    if free["learn"]:
        blocks.append(("learn",))
    if free["mcq_pair"]:
        blocks.append(("guess", "slip"))
    if free["typed_pair"]:
        blocks.append(("guess_typed", "slip_typed"))
    free_names = [name for block in blocks for name in block]
    if not blocks:
        return base, {"status": "not_run", "optimizer": "L-BFGS-B", "message": "No identifiable parameters.",
                      "iterations": 0, "objective": None, "finite": True, "free": []}

    def pack(p: dict[str, float]) -> list[float]:
        values: list[float] = []
        for block in blocks:
            if len(block) == 1:
                values.append(_logit(p[block[0]]))
            else:
                values.extend(_pair_to_raw(p[block[0]], p[block[1]]))
        return values

    def unpack(values: Sequence[float]) -> dict[str, float]:
        p = dict(base)
        index = 0
        for block in blocks:
            if len(block) == 1:
                p[block[0]] = _sigmoid(float(values[index]))
                index += 1
            else:
                p[block[0]], p[block[1]] = _raw_to_pair(float(values[index]), float(values[index + 1]))
                index += 2
        return p

    anchor = pack(base)

    def objective(values: np.ndarray) -> float:
        loss = _log_loss(sequences, unpack(values))
        penalty = REGULARIZATION * sum((value - center) ** 2 for value, center in zip(values, anchor)) / len(anchor)
        total = loss + penalty
        return total if isfinite(total) else float("inf")

    # A few deterministic starts guard against the local optima BKT is known
    # for; the best finite objective wins.
    starts = [anchor]
    for shift in (-1.0, 1.0):
        starts.append([value + shift for value in anchor])
    best = None
    for start in starts:
        try:
            result = minimize(objective, np.array(start), method="L-BFGS-B",
                              bounds=[(-12.0, 12.0)] * len(anchor), options={"maxiter": max(1, iterations)})
        except Exception as error:  # a scipy failure must never become a silent default fit
            return base, {"status": "failed", "optimizer": "L-BFGS-B", "message": str(error),
                          "iterations": 0, "objective": None, "finite": False, "free": free_names}
        if isfinite(float(result.fun)) and (best is None or float(result.fun) < float(best.fun)):
            best = result
    if best is None:
        return base, {"status": "failed", "optimizer": "L-BFGS-B", "message": "No finite objective.",
                      "iterations": 0, "objective": None, "finite": False, "free": free_names}
    fitted = unpack(best.x)
    finite = all(isfinite(value) for value in fitted.values())
    successful = bool(best.success and finite)
    return (fitted if successful else base), {
        "status": "success" if successful else "failed",
        "optimizer": "L-BFGS-B",
        "message": str(best.message),
        "iterations": int(getattr(best, "nit", 0) or 0),
        "objective": float(best.fun),
        "finite": finite,
        "free": free_names,
    }


def parameter_constraints(parameters: dict[str, float]) -> dict[str, bool]:
    checks = {}
    for name, (low, high) in FORMAT_AWARE_BOUNDS.items():
        value = parameters[name]
        checks[name] = (low + BOUND_MARGIN if low > 0 else low) < value < high - BOUND_MARGIN
    checks["discrimination_mcq"] = 1.0 - parameters["slip"] - parameters["guess"] >= MIN_DISCRIMINATION
    checks["discrimination_typed"] = 1.0 - parameters["slip_typed"] - parameters["guess_typed"] >= MIN_DISCRIMINATION
    checks["all"] = all(checks.values())
    return checks


def _digest(records: Sequence[ResponseRecord]) -> str:
    rows = [
        {"student_id": r.student_id, "concept_id": r.concept_id, "correct": r.correct,
         "question_kind": r.question_kind, "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None,
         "attempt_id": r.attempt_id, "question_index": r.question_index}
        for r in records
    ]
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def calibrate_format_aware_bkt(
    records: Iterable[ResponseRecord],
    *,
    synthetic: bool = False,
    iterations: int = 200,
    production: BktConfig = BKT_CONFIG,
    calibration_bins: int = CALIBRATION_BINS,
) -> dict[str, Any]:
    """Fit a format-aware candidate and compare it with ``production`` out of sample."""
    ordered = _canonical_records(records)
    baseline = baseline_parameters(production)
    assignments = assign_student_folds(ordered, fold_count=FOLD_COUNT) if ordered else {}
    candidate_pairs: tuple[list[bool], list[float]] = ([], [])
    production_pairs: tuple[list[bool], list[float]] = ([], [])
    folds: list[dict[str, Any]] = []
    fold_diagnostics: list[dict[str, Any]] = []
    for fold in range(FOLD_COUNT):
        training = [record for record in ordered if assignments[record.student_id] != fold]
        held_out = [record for record in ordered if assignments[record.student_id] == fold]
        fitted, diagnostic = fit_format_aware_parameters(training, baseline=baseline, iterations=iterations)
        fitted = registry_parameters(fitted)
        outcomes, predictions = score_records(held_out, fitted)
        base_outcomes, base_predictions = score_records(held_out, baseline)
        candidate_pairs[0].extend(outcomes)
        candidate_pairs[1].extend(predictions)
        production_pairs[0].extend(base_outcomes)
        production_pairs[1].extend(base_predictions)
        fold_diagnostics.append({"fold": fold, **diagnostic})
        train_students = {record.student_id for record in training}
        test_students = {record.student_id for record in held_out}
        folds.append({
            "fold": fold, "train_records": len(training), "held_out_records": len(held_out),
            "student_overlap": sorted(train_students & test_students),
            "candidate_parameters": fitted, "fit_diagnostic": diagnostic,
            "candidate_metrics": _metrics(outcomes, predictions, bins=calibration_bins),
            "production_metrics": _metrics(base_outcomes, base_predictions, bins=calibration_bins),
        })

    final, final_diagnostic = fit_format_aware_parameters(ordered, baseline=baseline, iterations=iterations)
    final = registry_parameters(final)
    candidate_metrics = _metrics(*candidate_pairs, bins=calibration_bins)
    production_metrics = _metrics(*production_pairs, bins=calibration_bins)
    counts = _counts(ordered)
    constraints = parameter_constraints(final)
    ident = identifiability(ordered)
    converged = bool(ordered) and final_diagnostic["status"] == "success" and all(
        diagnostic["status"] in {"success", "not_run"} for diagnostic in fold_diagnostics
    )

    def not_worse(metric: str, slack: float) -> bool:
        candidate, current = candidate_metrics[metric], production_metrics[metric]
        return candidate is not None and current is not None and candidate <= current + slack

    gates = {
        "minimum_qualifying_students": counts["qualifying_students"] >= 25,
        "minimum_records": counts["records"] >= 500,
        "minimum_concepts": counts["concepts"] >= 10,
        "minimum_correct": counts["correct"] >= 100,
        "minimum_incorrect": counts["incorrect"] >= 100,
        "zero_student_overlap": all(not fold["student_overlap"] for fold in folds),
        "all_optimizers_converged": converged,
        "parameter_constraints": constraints["all"],
        "candidate_log_loss": not_worse("log_loss", 0.01),
        "candidate_brier": not_worse("brier", 0.01),
        "candidate_calibration_error": not_worse("calibration_error", 0.02),
        "production_model_compatibility": True,
    }
    gates_passed = all(gates.values())
    return {
        "version": FORMAT_AWARE_CALIBRATION_VERSION,
        "model_scope": FORMAT_AWARE_MODEL_SCOPE,
        "production_model_scope": FORMAT_AWARE_MODEL_SCOPE,
        "synthetic": synthetic,
        "gates_passed": gates_passed,
        # Only real learner evidence may ever be marked promotable; the
        # database enforces the same rule.
        "promotable": gates_passed and not synthetic,
        "digest": _digest(ordered),
        "split_spec": {"strategy": "deterministic_student_grouped", "fold_count": FOLD_COUNT,
                       "prediction_timing": "before_update", "calibration_bins": calibration_bins},
        "counts": counts,
        "identifiability": ident,
        "fold_assignments": dict(sorted(assignments.items())),
        "folds": folds,
        "production_parameters": baseline,
        "candidate_parameters": final,
        "diagnostics": {"folds": fold_diagnostics, "final": final_diagnostic},
        "parameter_constraints": constraints,
        "metrics": {"candidate": candidate_metrics, "production": production_metrics},
        "gates": gates,
    }
