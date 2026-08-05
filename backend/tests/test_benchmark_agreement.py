"""Unit tests for inter-rater ("human ceiling") agreement metrics.

A system-vs-teacher kappa is uninterpretable on its own. If four experts only
agree with each other at 0.60, a system scoring 0.58 against their consensus
is performing at human level -- not badly. These metrics supply that ceiling.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.agreement import (
    fleiss_kappa,
    majority_label,
    mean_pairwise_kappa,
    rater_agreement_summary,
)


class TestMajorityLabel:
    def test_takes_the_majority_of_an_odd_panel(self):
        assert majority_label([True, False, True]) is True
        assert majority_label([False, False, True]) is False

    def test_breaks_an_even_split_toward_incorrect(self):
        """A tie means the panel did not agree the syllable was correct.
        Resolving toward "correct" would silently inflate the pass rate that
        the system is then measured against."""
        assert majority_label([True, False]) is False

    def test_returns_none_for_an_empty_panel(self):
        assert majority_label([]) is None


class TestMeanPairwiseKappa:
    def test_perfectly_consistent_raters_reach_one(self):
        raters = [
            [True, False, True, False],
            [True, False, True, False],
            [True, False, True, False],
        ]
        assert mean_pairwise_kappa(raters) == pytest.approx(1.0)

    def test_averages_every_unique_rater_pair(self):
        """Three raters yield three pairs; the reported ceiling is their mean."""
        raters = [
            [True, True, False, False],
            [True, True, False, False],
            [True, False, True, False],
        ]
        result = mean_pairwise_kappa(raters)
        assert result is not None
        assert 0.0 < result < 1.0

    def test_needs_at_least_two_raters(self):
        assert mean_pairwise_kappa([[True, False]]) is None

    def test_rejects_ragged_rater_rows(self):
        with pytest.raises(ValueError):
            mean_pairwise_kappa([[True, False], [True]])


class TestFleissKappa:
    def test_total_agreement_reaches_one(self):
        raters = [
            [True, False, True],
            [True, False, True],
            [True, False, True],
        ]
        assert fleiss_kappa(raters) == pytest.approx(1.0)

    def test_is_none_when_every_item_has_the_same_label(self):
        """With no variation there is no chance-corrected agreement to report;
        returning 0.0 would misleadingly suggest raters disagreed."""
        raters = [[True, True], [True, True]]
        assert fleiss_kappa(raters) is None

    def test_perfect_systematic_disagreement_is_exactly_negative_one(self):
        """Hand-computed: every item splits 1/1, so observed agreement is 0
        while expected is 0.5, giving (0 - 0.5) / (1 - 0.5) = -1. Locking the
        exact value guards against a subtly wrong formula, which in a
        statistics module would otherwise be invisible."""
        raters = [
            [True, False, True, False],
            [False, True, False, True],
        ]
        assert fleiss_kappa(raters) == pytest.approx(-1.0)


class TestRaterAgreementSummary:
    def test_reports_ceiling_alongside_panel_shape(self):
        raters = [
            [True, True, False, True],
            [True, False, False, True],
            [True, True, False, True],
        ]
        summary = rater_agreement_summary(raters)
        assert summary["rater_count"] == 3
        assert summary["item_count"] == 4
        assert summary["mean_pairwise_cohen_kappa"] is not None
        assert "fleiss_kappa" in summary
        # One of four items drew a split vote (item index 1).
        assert summary["unanimous_item_count"] == 3

    def test_handles_an_empty_panel_without_crashing(self):
        summary = rater_agreement_summary([])
        assert summary["rater_count"] == 0
        assert summary["mean_pairwise_cohen_kappa"] is None
