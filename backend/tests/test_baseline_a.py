"""Baseline A's per-split evaluation — must read the verified CSV columns
directly and reuse the already-tested stats primitives, never re-derive a
verdict from anything else."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.baseline_a import evaluate


def _row(system_correct: str, human_correct: str, score: str = "70.0"):
    return {
        "system_tone_correct": system_correct,
        "human_majority_tone_correct": human_correct,
        "system_character_score": score,
    }


class TestEvaluate:
    def test_empty_rows_is_n_zero_not_an_error(self):
        assert evaluate([]) == {"n": 0}

    def test_reads_the_literal_csv_columns(self):
        rows = [
            _row("1", "1", "90"),  # TP
            _row("0", "0", "10"),  # TN
            _row("1", "0", "60"),  # FP
            _row("0", "1", "30"),  # FN
        ]
        metrics = evaluate(rows)
        assert metrics["true_positive"] == 1
        assert metrics["true_negative"] == 1
        assert metrics["false_positive"] == 1
        assert metrics["false_negative"] == 1
        assert metrics["accuracy"] == pytest.approx(0.5)

    def test_includes_balanced_accuracy_and_mcc_from_stats(self):
        rows = [_row("1", "1"), _row("1", "1"), _row("0", "0")]
        metrics = evaluate(rows)
        assert "balanced_accuracy" in metrics
        assert "matthews_correlation" in metrics

    def test_auc_uses_the_continuous_score_against_the_human_label(self):
        rows = [
            _row("0", "0", "10"),
            _row("0", "0", "20"),
            _row("1", "1", "90"),
            _row("1", "1", "95"),
        ]
        assert evaluate(rows)["auc"] == pytest.approx(1.0)

    def test_na_scores_are_excluded_from_auc_not_treated_as_zero(self):
        rows = [_row("1", "1", "NA"), _row("0", "0", "NA")]
        assert evaluate(rows)["auc"] is None
