"""Offline, deterministic BKT calibration evaluation utilities.

This module deliberately does not import serving configuration or mutate it.
It evaluates a proposed global BKT fit against the current transparent BKT
defaults using student-grouped cross validation, then returns an audit-ready
plain dictionary for an external review process to decide whether to promote.
"""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
from math import log
from typing import Any, Iterable, Sequence

from .knowledge_tracing import BKT, BKTParameters, ResponseRecord, fit_bkt_parameters


FOLD_COUNT = 5
CALIBRATION_BINS = 10
PARAMETER_BOUNDS = {
    "prior": (0.01, 0.80),
    "learn": (0.001, 0.50),
    "guess": (0.01, 0.45),
    "slip": (0.01, 0.30),
}
BOUND_MARGIN = 0.005
MIN_DISCRIMINATION = 0.10


def _record_key(record: ResponseRecord) -> tuple[Any, ...]:
    """Stable ordering only for records sharing no caller-provided sequence."""
    occurred = record.occurred_at.isoformat() if record.occurred_at else ""
    return (occurred, record.attempt_id, record.question_index, record.student_id, record.concept_id)


def _canonical_records(records: Iterable[ResponseRecord]) -> list[ResponseRecord]:
    # The tracing API expects ordered histories. Sorting makes an offline run
    # repeatable when the caller supplies records from an unordered source.
    return sorted(records, key=_record_key)


def assign_student_folds(records: Iterable[ResponseRecord], *, fold_count: int = FOLD_COUNT) -> dict[str, int]:
    """Assign each student to exactly one deterministic, balanced fold."""
    if fold_count < 2:
        raise ValueError("fold_count must be at least 2")
    students = sorted({record.student_id for record in records})
    ranked = sorted(students, key=lambda student: (sha256(student.encode("utf-8")).hexdigest(), student))
    return {student: index % fold_count for index, student in enumerate(ranked)}


def _metrics(outcomes: Sequence[bool], predictions: Sequence[float], *, bins: int = CALIBRATION_BINS) -> dict[str, Any]:
    positives = sum(outcomes)
    negatives = len(outcomes) - positives
    if not outcomes:
        return {"n": 0, "positive_count": 0, "negative_count": 0, "log_loss": None, "brier": None,
                "calibration_error": None, "auc": None}
    log_loss = -sum(log(p if outcome else 1.0 - p) for p, outcome in zip(predictions, outcomes)) / len(outcomes)
    brier = sum((p - float(outcome)) ** 2 for p, outcome in zip(predictions, outcomes)) / len(outcomes)
    calibration_error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [i for i, p in enumerate(predictions) if low <= p < high or (index == bins - 1 and p == 1.0)]
        if members:
            observed = sum(outcomes[i] for i in members) / len(members)
            expected = sum(predictions[i] for i in members) / len(members)
            calibration_error += len(members) / len(outcomes) * abs(observed - expected)
    auc = None
    if positives and negatives:
        ranked = sorted(zip(predictions, outcomes), key=lambda pair: pair[0])
        rank_sum, index = 0.0, 0
        while index < len(ranked):
            end = index + 1
            while end < len(ranked) and ranked[end][0] == ranked[index][0]:
                end += 1
            rank_sum += (index + 1 + end) / 2.0 * sum(outcome for _, outcome in ranked[index:end])
            index = end
        auc = (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)
    return {"n": len(outcomes), "positive_count": positives, "negative_count": negatives, "log_loss": log_loss,
            "brier": brier, "calibration_error": calibration_error, "auc": auc}


def _score(records: Sequence[ResponseRecord], parameters: BKTParameters) -> tuple[list[bool], list[float]]:
    """Score records prequentially: each probability precedes its update."""
    tracer = BKT(parameters)
    outcomes: list[bool] = []
    predictions: list[float] = []
    for record in records:
        predictions.append(tracer.predict(record.student_id, record.concept_id))
        outcomes.append(record.correct)
        tracer.update(record)
    return outcomes, predictions


def parameter_constraints(parameters: BKTParameters) -> dict[str, bool]:
    """Return strict calibration-only viability checks for a fitted candidate."""
    checks = {
        name: low + BOUND_MARGIN < getattr(parameters, name) < high - BOUND_MARGIN
        for name, (low, high) in PARAMETER_BOUNDS.items()
    }
    checks["discrimination"] = 1.0 - parameters.slip - parameters.guess >= MIN_DISCRIMINATION
    checks["all"] = all(checks.values())
    return checks


def _counts(records: Sequence[ResponseRecord]) -> dict[str, int]:
    by_student = Counter(record.student_id for record in records)
    correct = sum(record.correct for record in records)
    return {
        "records": len(records), "students": len(by_student), "qualifying_students": sum(n >= 5 for n in by_student.values()),
        "concepts": len({record.concept_id for record in records}), "correct": correct, "incorrect": len(records) - correct,
    }


def _digest(records: Sequence[ResponseRecord]) -> str:
    rows = [
        {"student_id": r.student_id, "concept_id": r.concept_id, "correct": r.correct,
         "occurred_at": r.occurred_at.isoformat() if r.occurred_at else None, "attempt_id": r.attempt_id,
         "question_index": r.question_index}
        for r in records
    ]
    import json
    return sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def calibrate_bkt(
    records: Iterable[ResponseRecord], *, synthetic: bool = False, fold_count: int = FOLD_COUNT,
    iterations: int = 80, calibration_bins: int = CALIBRATION_BINS,
    production_parameters: BKTParameters = BKTParameters(),
) -> dict[str, Any]:
    """Fit and evaluate a BKT candidate without changing production behavior.

    Each held-out student starts with the global prior, so no response from a
    held-out student can influence either fitting or their prediction history.
    """
    if fold_count != FOLD_COUNT:
        raise ValueError("BKT calibration requires exactly 5 folds")
    if calibration_bins < 1:
        raise ValueError("calibration_bins must be at least 1")
    ordered = _canonical_records(records)
    assignments = assign_student_folds(ordered, fold_count=fold_count)
    candidate_outcomes: list[bool] = []
    candidate_predictions: list[float] = []
    baseline_outcomes: list[bool] = []
    baseline_predictions: list[float] = []
    folds: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for fold in range(fold_count):
        training = [record for record in ordered if assignments[record.student_id] != fold]
        held_out = [record for record in ordered if assignments[record.student_id] == fold]
        train_students = {record.student_id for record in training}
        test_students = {record.student_id for record in held_out}
        overlap = sorted(train_students & test_students)
        if training:
            fitted, fit_diagnostic = fit_bkt_parameters(training, initial=production_parameters, iterations=iterations, include_diagnostics=True)
        else:
            fitted, fit_diagnostic = production_parameters, {"status": "not_run", "optimizer": "L-BFGS-B", "message": "No training records.", "iterations": 0, "objective": None, "finite": True}
        outcomes, predictions = _score(held_out, fitted)
        baseline_fold_outcomes, baseline_fold_predictions = _score(held_out, production_parameters)
        candidate_outcomes.extend(outcomes)
        candidate_predictions.extend(predictions)
        baseline_outcomes.extend(baseline_fold_outcomes)
        baseline_predictions.extend(baseline_fold_predictions)
        diagnostics.append({"fold": fold, **fit_diagnostic})
        folds.append({
            "fold": fold, "train_records": len(training), "held_out_records": len(held_out),
            "train_students": sorted(train_students), "held_out_students": sorted(test_students), "student_overlap": overlap,
            "candidate_parameters": fitted.to_dict(), "fit_diagnostic": fit_diagnostic,
            "candidate_metrics": _metrics(outcomes, predictions, bins=calibration_bins),
            "production_metrics": _metrics(baseline_fold_outcomes, baseline_fold_predictions, bins=calibration_bins),
        })

    if ordered:
        final_parameters, final_diagnostic = fit_bkt_parameters(ordered, initial=production_parameters, iterations=iterations, include_diagnostics=True)
    else:
        final_parameters, final_diagnostic = production_parameters, {"status": "not_run", "optimizer": "L-BFGS-B", "message": "No records.", "iterations": 0, "objective": None, "finite": True}
    candidate_metrics = _metrics(candidate_outcomes, candidate_predictions, bins=calibration_bins)
    production_metrics = _metrics(baseline_outcomes, baseline_predictions, bins=calibration_bins)
    counts = _counts(ordered)
    constraint_checks = parameter_constraints(final_parameters)
    all_converged = bool(ordered) and final_diagnostic["status"] == "success" and all(diagnostic["status"] == "success" for diagnostic in diagnostics)
    gates = {
        "minimum_qualifying_students": counts["qualifying_students"] >= 25,
        "minimum_records": counts["records"] >= 500,
        "minimum_concepts": counts["concepts"] >= 10,
        "minimum_correct": counts["correct"] >= 100,
        "minimum_incorrect": counts["incorrect"] >= 100,
        "zero_student_overlap": all(not fold["student_overlap"] for fold in folds),
        "all_optimizers_converged": all_converged,
        "parameter_constraints": constraint_checks["all"],
        "candidate_log_loss": candidate_metrics["log_loss"] is not None and candidate_metrics["log_loss"] <= production_metrics["log_loss"] + 0.01,
        "candidate_brier": candidate_metrics["brier"] is not None and candidate_metrics["brier"] <= production_metrics["brier"] + 0.01,
        "candidate_calibration_error": candidate_metrics["calibration_error"] is not None and candidate_metrics["calibration_error"] <= production_metrics["calibration_error"] + 0.02,
    }
    promotable = not synthetic and all(gates.values())
    return {
        "version": "bkt-calibration-v1", "synthetic": synthetic, "promotable": promotable,
        "digest": _digest(ordered), "split_spec": {"strategy": "deterministic_student_grouped", "fold_count": fold_count, "prediction_timing": "before_update", "calibration_bins": calibration_bins},
        "counts": counts, "fold_assignments": dict(sorted(assignments.items())), "folds": folds,
        "production_parameters": production_parameters.to_dict(), "candidate_parameters": final_parameters.to_dict(),
        "diagnostics": {"folds": diagnostics, "final": final_diagnostic}, "parameter_constraints": constraint_checks,
        "metrics": {"candidate": candidate_metrics, "production": production_metrics}, "gates": gates,
    }


# Clear noun-first alias for callers that prefer a report-oriented name.
build_bkt_calibration_report = calibrate_bkt
run_bkt_calibration = calibrate_bkt
