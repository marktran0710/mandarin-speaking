import math

import pytest

from analytics.knowledge_tracing import (
    BKT,
    BKTParameters,
    PFA,
    PFAParameters,
    ResponseRecord,
    evaluate_prequential,
    evaluate_vocab_attempts,
    fit_pfa_parameters,
    normalize_vocab_attempts,
)


def record(correct: bool, index: int = 0, student: str = "s1", concept: str = "c1") -> ResponseRecord:
    return ResponseRecord(student, concept, correct, None, "attempt", index)


def test_normalization_prefers_concept_orders_by_time_and_counts_legacy_fallback():
    normalized = normalize_vocab_attempts([
        {"id": "late", "studentId": "S1", "completedAt": "2026-01-02T00:00:00Z", "questionResults": [{"conceptId": " Concept-A ", "word": "ignored", "correct": True}]},
        {"id": "early", "studentId": "S1", "completedAt": "2026-01-01T00:00:00Z", "questionResults": [{"word": " 學習 ", "correct": False}]},
    ])
    assert [(item.concept_id, item.correct) for item in normalized.records] == [("學習", False), ("concept-a", True)]
    assert normalized.counters["legacy_word_fallback"] == 1
    assert normalized.counters["records_emitted"] == 2


def test_normalization_skips_invalid_and_legacy_data_without_coercing_outcomes():
    normalized = normalize_vocab_attempts([
        {"studentName": " Legacy Student ", "completedAt": "not-a-time", "questionResults": [
            {"word": "word", "correct": "true"}, {"correct": False}, {"word": "ok", "correct": True},
        ]},
        {"questionResults": [{"word": "orphan", "correct": True}]},
    ])
    assert len(normalized.records) == 1
    assert normalized.records[0].student_id == "legacy student"
    assert normalized.counters["skipped_invalid_correct"] == 1
    assert normalized.counters["skipped_missing_concept"] == 1
    assert normalized.counters["attempts_without_student"] == 1
    assert normalized.counters["invalid_timestamp"] == 1


def test_normalization_deduplicates_replayed_attempt_response_positions():
    payload = {
        "id": "same-attempt",
        "studentId": "s1",
        "completedAt": "2026-01-01T00:00:00Z",
        "questionResults": [{"conceptId": "c1", "correct": True}],
    }
    normalized = normalize_vocab_attempts([payload, payload])
    assert len(normalized.records) == 1
    assert normalized.counters["duplicate_responses"] == 1


def test_pfa_tracks_per_student_concept_counts_and_predictions():
    model = PFA(PFAParameters(intercept=0.0, success_weight=1.0, failure_weight=-1.0))
    assert model.predict("s1", "c1") == pytest.approx(0.5)
    model.update(record(True))
    model.update(record(False, 1))
    assert model.state_for("s1", "c1").to_dict() == {"successes": 1, "failures": 1}
    assert model.predict("other", "c1") == pytest.approx(0.5)
    assert 0.0 < model.predict("s1", "c1") < 1.0


def test_regularized_pfa_fit_returns_finite_global_parameters():
    parameters = fit_pfa_parameters([record(False, 0), record(True, 1), record(True, 2)])
    assert parameters.l2 == 1.0
    assert all(math.isfinite(value) for value in parameters.to_dict().values())


def test_bkt_correct_and_incorrect_updates_are_bayesian_and_bounded():
    model = BKT(BKTParameters(prior=0.2, learn=0.1, guess=0.2, slip=0.1))
    predicted = model.predict("s1", "c1")
    correct = model.update(record(True))
    incorrect = model.update(record(False, 1))
    assert predicted == pytest.approx(0.34)
    assert correct["posterior_mastery"] > 0.2
    assert incorrect["posterior_mastery"] < correct["mastery"]
    assert all(0.0 < value < 1.0 for value in incorrect.values())


def test_prequential_evaluation_has_bounded_metrics_and_optional_auc():
    records = [record(bool(index % 2), index) for index in range(8)]
    result = evaluate_prequential(records, model="pfa", train_fraction=0.5, include_auc=False)
    metrics = result["metrics"]
    assert result["train_n"] == 4
    assert metrics["n"] == 4
    assert metrics["auc"] is None
    assert metrics["log_loss"] >= 0.0
    assert 0.0 <= metrics["brier"] <= 1.0
    assert 0.0 <= metrics["calibration_error"] <= 1.0
    assert all(math.isfinite(value) for key, value in metrics.items() if value is not None and key != "n")


def test_bkt_evaluation_and_parameter_validation():
    result = evaluate_prequential([record(True, 0), record(False, 1)], model="bkt", train_fraction=0.0)
    assert result["metrics"]["n"] == 2
    with pytest.raises(ValueError):
        BKTParameters(guess=1.1)
    with pytest.raises(ValueError):
        evaluate_prequential([], model="unknown")


def test_dict_friendly_evaluation_reports_normalization_quality():
    result = evaluate_vocab_attempts([
        {"studentId": "s1", "completedAt": "2026-01-01T00:00:00Z", "questionResults": [{"conceptId": "c1", "correct": True}]},
        {"studentId": "s1", "completedAt": "2026-01-02T00:00:00Z", "questionResults": [{"word": "legacy", "correct": False}]},
    ], model="bkt", train_fraction=0.5)
    assert result["metrics"]["n"] == 1
    assert result["data_quality"]["records_emitted"] == 2
    assert result["data_quality"]["legacy_word_fallback"] == 1
