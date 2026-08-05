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
    pearson,
    rank,
    safe_divide,
    spearman,
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
