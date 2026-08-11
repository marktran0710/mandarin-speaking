"""Unit tests for the shared benchmark statistics primitives.

These back both the system-vs-teacher comparison and the teacher-vs-teacher
(human ceiling) comparison, so they must be correct and symmetric.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.stats import (
    binary_agreement,
    confusion_counts,
    error_rates,
    matthews_correlation,
    pearson,
    rank,
    roc_auc,
    safe_divide,
    spearman,
    summary_stats,
)


class TestSafeDivide:
    def test_returns_none_rather_than_zero_for_undefined_rates(self):
        """A missing metric must stay visibly missing, never read as a real 0."""
        assert safe_divide(5, 0) is None
        assert safe_divide(0, 0) is None

    def test_divides_normally(self):
        assert safe_divide(1, 4) == 0.25


class TestConfusionCounts:
    def test_counts_each_quadrant(self):
        predicted = [True, True, False, False]
        actual = [True, False, True, False]
        assert confusion_counts(predicted, actual) == (1, 1, 1, 1)

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError):
            confusion_counts([True], [True, False])


class TestBinaryAgreement:
    def test_perfect_agreement_gives_kappa_of_one(self):
        labels = [True, False, True, True, False]
        result = binary_agreement(labels, labels)
        assert result["accuracy"] == 1.0
        assert result["cohen_kappa"] == pytest.approx(1.0)
        assert result["n"] == 5

    def test_kappa_is_symmetric_so_it_serves_human_vs_human_too(self):
        """The ceiling metric is only comparable to the system metric if the
        same function computes both; Cohen's kappa is symmetric, so it does."""
        first = [True, True, False, True, False, False]
        second = [True, False, False, True, True, False]
        assert binary_agreement(first, second)["cohen_kappa"] == pytest.approx(
            binary_agreement(second, first)["cohen_kappa"]
        )

    def test_high_accuracy_on_an_imbalanced_set_still_yields_low_kappa(self):
        """The whole point of reporting kappa: a scorer that says "correct" to
        everything looks ~90% accurate on a corpus that is 90% correct, but
        carries no information. Kappa must expose that."""
        actual = [True] * 18 + [False] * 2
        always_pass = [True] * 20
        result = binary_agreement(always_pass, actual)
        assert result["accuracy"] == pytest.approx(0.9)
        assert result["cohen_kappa"] == pytest.approx(0.0)

    def test_undefined_precision_is_none_not_zero(self):
        actual = [False, False]
        predicted = [False, False]
        assert binary_agreement(predicted, actual)["precision"] is None


class TestRank:
    def test_ties_share_their_average_rank(self):
        assert rank([10, 20, 20, 40]) == [1.0, 2.5, 2.5, 4.0]

    def test_ranks_are_ascending(self):
        assert rank([5, 1, 3]) == [3.0, 1.0, 2.0]


class TestCorrelation:
    def test_pearson_detects_a_perfect_linear_relationship(self):
        assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)

    def test_pearson_is_none_without_spread(self):
        assert pearson([3, 3, 3], [1, 2, 3]) is None

    def test_pearson_is_none_below_two_points(self):
        assert pearson([1], [2]) is None

    def test_spearman_sees_a_monotonic_but_non_linear_match(self):
        """The 1-5 teacher rubric and the 0-100 system score are not linearly
        related, so rank correlation is the honest comparison."""
        teacher = [1, 2, 3, 4, 5]
        system = [10, 12, 40, 90, 99]
        assert spearman(system, teacher) == pytest.approx(1.0)

    def test_spearman_detects_reversed_ordering(self):
        assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)


class TestSpecificityAndErrorRates:
    def test_specificity_complements_recall_on_the_negative_class(self):
        # actual=False at indices 1,2,4; predicted matches at 1,4 but not 2 ->
        # 2 true negatives, 1 false positive -> specificity 2/3.
        metrics = binary_agreement(
            [True, False, True, True, False],
            [True, False, False, True, False],
        )
        assert metrics["specificity"] == pytest.approx(2 / 3)

    def test_false_acceptance_and_rejection_use_the_human_label_as_denominator(self):
        rates = error_rates(
            true_positive=6, true_negative=1, false_positive=3, false_negative=2
        )
        # False acceptance: out of everything humans marked incorrect (TN+FP).
        assert rates["false_acceptance_denominator"] == 4
        assert rates["false_acceptance_rate"] == pytest.approx(3 / 4)
        # False rejection: out of everything humans marked correct (TP+FN).
        assert rates["false_rejection_denominator"] == 8
        assert rates["false_rejection_rate"] == pytest.approx(2 / 8)

    def test_zero_denominator_is_none_not_zero(self):
        rates = error_rates(true_positive=5, true_negative=0, false_positive=0, false_negative=0)
        assert rates["false_acceptance_denominator"] == 0
        assert rates["false_acceptance_rate"] is None


class TestRocAuc:
    def test_perfect_separation_is_one(self):
        assert roc_auc([1, 2, 3, 10, 11, 12], [False, False, False, True, True, True]) == 1.0

    def test_perfect_inversion_is_zero(self):
        assert roc_auc([10, 11, 12, 1, 2, 3], [False, False, False, True, True, True]) == 0.0

    def test_no_signal_is_one_half(self):
        # Interleaved so every positive/negative pair is a tie -> chance level.
        assert roc_auc([1, 1, 2, 2, 3, 3], [True, False, True, False, True, False]) == pytest.approx(0.5)

    def test_matches_brute_force_pair_counting(self):
        scores = [0.1, 0.4, 0.35, 0.8, 0.9, 0.2, 0.6, 0.55]
        labels = [False, False, True, True, True, False, True, False]
        positives = [s for s, l in zip(scores, labels) if l]
        negatives = [s for s, l in zip(scores, labels) if not l]
        brute = sum(
            1.0 if p > n else 0.5 if p == n else 0.0
            for p in positives
            for n in negatives
        ) / (len(positives) * len(negatives))
        assert roc_auc(scores, labels) == pytest.approx(brute)

    def test_none_when_one_class_is_empty(self):
        assert roc_auc([1, 2, 3], [True, True, True]) is None
        assert roc_auc([], []) is None

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError):
            roc_auc([1, 2], [True])


class TestSummaryStats:
    def test_matches_numpy_quantile_convention(self):
        stats = summary_stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert stats["n"] == 10
        assert stats["median"] == pytest.approx(5.5)
        assert stats["q1"] == pytest.approx(3.25)
        assert stats["q3"] == pytest.approx(7.75)
        assert stats["iqr"] == pytest.approx(4.5)
        assert stats["mean"] == pytest.approx(5.5)

    def test_empty_input_is_all_none(self):
        stats = summary_stats([])
        assert stats["n"] == 0
        assert stats["median"] is None

    def test_single_value_has_zero_spread(self):
        stats = summary_stats([7.0])
        assert stats["n"] == 1
        assert stats["mean"] == 7.0
        assert stats["sd"] == 0.0
        assert stats["iqr"] == 0.0


class TestBalancedAccuracyAndMcc:
    def test_perfect_agreement_is_one(self):
        metrics = binary_agreement([True, True, False, False], [True, True, False, False])
        assert metrics["matthews_correlation"] == pytest.approx(1.0)
        assert metrics["balanced_accuracy"] == pytest.approx(1.0)

    def test_perfect_disagreement_is_minus_one_and_zero(self):
        metrics = binary_agreement([True, True, False, False], [False, False, True, True])
        assert metrics["matthews_correlation"] == pytest.approx(-1.0)
        assert metrics["balanced_accuracy"] == pytest.approx(0.0)

    def test_balanced_accuracy_exposes_a_majority_class_predictor_that_accuracy_hides(self):
        # Predicts True regardless of input on a 9:1 imbalanced set. Plain
        # accuracy rewards this (0.9); balanced accuracy and MCC must not.
        predicted = [True] * 10
        actual = [True] * 9 + [False]
        metrics = binary_agreement(predicted, actual)
        assert metrics["accuracy"] == pytest.approx(0.9)
        assert metrics["balanced_accuracy"] == pytest.approx(0.5)
        # Undefined (zero variance on the predicted side) rather than a
        # fabricated 0 — matches safe_divide's contract everywhere else.
        assert metrics["matthews_correlation"] is None

    def test_matthews_correlation_matches_the_textbook_formula(self):
        tp, tn, fp, fn = 5, 3, 2, 1
        expected = (tp * tn - fp * fn) / ((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn)) ** 0.5
        assert matthews_correlation(tp, tn, fp, fn) == pytest.approx(expected)

    def test_none_when_a_confusion_margin_is_empty(self):
        # No actual positives at all (TP=FN=0): the (TP+FN) margin is zero,
        # so the denominator is zero and the coefficient is undefined.
        assert matthews_correlation(0, 3, 2, 0) is None
