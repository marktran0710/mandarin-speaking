"""Tests for the directional_tone_scores diagnosis pipeline. These protect
the diagnosis's own correctness -- the trace-consistency bug this pipeline
already caught once (an early version silently disagreed with production by
20-50 points because it reimplemented windowing instead of intercepting the
real call) is exactly the class of error a test should catch before the
next person trusts this module's output.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.directional_tone_diagnosis import (
    CANONICAL_CONTOURS,
    EXPECTED_MONOTONIC_ORDER,
    PERTURBATIONS,
    PREDICTIONS_CSV,
    _components,
    _trace_one_case,
    build_canonical_matrix,
    build_perturbation_table,
    check_monotonicity,
    distribution_audit,
    load_controlled_predictions,
)


class TestComponents:
    def test_flat_contour_has_zero_variance(self):
        comps = _components(np.array([0.5, 0.5, 0.5, 0.5, 0.5]))
        assert comps["variance"] == pytest.approx(0.0)

    def test_rise_and_fall_are_exact_opposites(self):
        comps = _components(np.array([0.1, 0.3, 0.5, 0.7, 0.9]))
        assert comps["rise"] == pytest.approx(-comps["fall"])

    def test_dip_depth_matches_hand_computation_for_the_canonical_t3_shape(self):
        # From the task's own canonical T3 contour.
        comps = _components(np.array([0.6, 0.35, 0.2, 0.35, 0.65]))
        assert comps["s_mean"] == pytest.approx(0.6)
        assert comps["e_mean"] == pytest.approx(0.65)
        assert comps["mid_min"] == pytest.approx(0.2)
        assert comps["dip_depth"] == pytest.approx((0.6 + 0.65) / 2 - 0.2)


class TestCanonicalMatrix:
    def test_matrix_has_16_rows(self):
        rows = build_canonical_matrix()
        assert len(rows) == 16  # 4 produced x 4 expected

    def test_every_diagonal_case_is_the_correct_tones_own_top_score(self):
        """A minimal sanity bar any non-broken scorer should clear: for a
        FIXED expected tone, the contour genuinely produced in that tone
        should score at least as high as every other produced tone against
        that same expected tone -- this doesn't by itself prove the scorer
        is well-calibrated (see the real audit's cross-tone-confusion
        findings), only that it isn't reversed."""
        rows = build_canonical_matrix()
        by_expected: dict[int, dict[int, float]] = {}
        for row in rows:
            by_expected.setdefault(row["expected_tone"], {})[row["produced_tone"]] = row["raw_score_unsmoothed"]
        for expected_tone, by_produced in by_expected.items():
            diagonal = by_produced[expected_tone]
            assert diagonal == max(by_produced.values())

    def test_t1_canonical_contour_scores_100_against_itself(self):
        rows = build_canonical_matrix()
        row = next(r for r in rows if r["produced_tone"] == 1 and r["expected_tone"] == 1)
        assert row["raw_score_unsmoothed"] == pytest.approx(100.0)

    def test_all_four_canonical_contours_are_defined(self):
        assert set(CANONICAL_CONTOURS) == {1, 2, 3, 4}
        assert all(len(v) == 5 for v in CANONICAL_CONTOURS.values())


class TestPerturbationTable:
    def test_every_tone_has_a_perturbation_family(self):
        assert set(PERTURBATIONS) == {1, 2, 3, 4}

    def test_expected_monotonic_order_only_references_real_labels(self):
        """Guards the pre-specified monotonicity check itself: every label
        named in EXPECTED_MONOTONIC_ORDER must actually exist in
        PERTURBATIONS, or the check would silently KeyError or -- worse --
        silently skip a tone if that were ever caught broadly."""
        for tone, order in EXPECTED_MONOTONIC_ORDER.items():
            available = {label for label, _ in PERTURBATIONS[tone]}
            assert set(order) <= available

    def test_build_perturbation_table_covers_every_declared_variant(self):
        rows = build_perturbation_table()
        expected_n = sum(len(variants) for variants in PERTURBATIONS.values())
        assert len(rows) == expected_n


class TestMonotonicityCheck:
    def test_detects_a_genuinely_monotonic_sequence(self):
        rows = [
            {"expected_tone": 1, "perturbation_label": "a", "score": 10.0},
            {"expected_tone": 1, "perturbation_label": "b", "score": 20.0},
        ]
        order_backup = dict(EXPECTED_MONOTONIC_ORDER)
        try:
            EXPECTED_MONOTONIC_ORDER.clear()
            EXPECTED_MONOTONIC_ORDER[1] = ["a", "b"]
            result = check_monotonicity(rows)
            assert result[1]["is_monotonic"] is True
            assert result[1]["violations"] == []
        finally:
            EXPECTED_MONOTONIC_ORDER.clear()
            EXPECTED_MONOTONIC_ORDER.update(order_backup)

    def test_detects_a_violation(self):
        rows = [
            {"expected_tone": 1, "perturbation_label": "a", "score": 20.0},
            {"expected_tone": 1, "perturbation_label": "b", "score": 10.0},
        ]
        order_backup = dict(EXPECTED_MONOTONIC_ORDER)
        try:
            EXPECTED_MONOTONIC_ORDER.clear()
            EXPECTED_MONOTONIC_ORDER[1] = ["a", "b"]
            result = check_monotonicity(rows)
            assert result[1]["is_monotonic"] is False
            assert result[1]["violations"] == [("a", "b", 20.0, 10.0)]
        finally:
            EXPECTED_MONOTONIC_ORDER.clear()
            EXPECTED_MONOTONIC_ORDER.update(order_backup)


class TestDistributionAudit:
    def _rows(self):
        return [
            {"reference_tone": "2", "current_score": "30.0", "expected_tone_correct": "1"},
            {"reference_tone": "2", "current_score": "80.0", "expected_tone_correct": "0"},
        ]

    def test_separates_matched_and_mismatched_scores(self):
        result = distribution_audit(self._rows())
        assert result[2]["matched_scores"] == [30.0]
        assert result[2]["mismatched_scores"] == [80.0]

    def test_matched_all_below_58_flag(self):
        result = distribution_audit(self._rows())
        assert result[2]["matched_all_below_58"] is True

    def test_ranges_overlap_detection(self):
        # matched max 30 < mismatched min 80 -> no overlap in this toy case
        result = distribution_audit(self._rows())
        assert result[2]["ranges_overlap"] is False

    def test_empty_tone_group_returns_none_fields_not_errors(self):
        result = distribution_audit(self._rows())
        assert result[1]["matched_all_below_58"] is None
        assert result[1]["n"] == 0


@pytest.mark.skipif(not PREDICTIONS_CSV.exists(), reason="controlled_tone_predictions.csv not generated yet")
class TestTraceMatchesProduction:
    """Regression guard for the exact bug this diagnosis pipeline caught in
    itself: an earlier version of `_trace_one_case` reimplemented
    `estimate_word_prosody`'s windowing by hand and silently disagreed with
    the real score by 20-50 points, because it didn't know about the
    word-span slicing and 12% onset-skip. The fix was to intercept the real
    call chain via monkeypatching instead of reconstructing it -- this test
    is what would have caught the original bug, and what protects against
    a regression back to hand-reconstruction."""

    def test_every_traced_case_matches_its_recorded_score(self):
        rows = load_controlled_predictions()
        # A handful is enough to catch a systematic windowing mismatch --
        # every case would be wrong the same way, not spot-fail.
        for row in rows[:6]:
            traced = _trace_one_case(row)
            assert traced["matches_recorded_score"] is True, (
                f"{row['case_id']}: recomputed {traced['final_score']} vs "
                f"recorded {row['current_score']}"
            )

    def test_trace_restores_the_original_chinese_tones_functions_afterward(self):
        """The monkeypatch must not leak -- a case run here must not affect
        any other test or a later real call."""
        import chinese_tones

        original_normalize = chinese_tones.normalize_pitch_contour
        original_score_segment = chinese_tones._score_segment

        rows = load_controlled_predictions()
        _trace_one_case(rows[0])

        assert chinese_tones.normalize_pitch_contour is original_normalize
        assert chinese_tones._score_segment is original_score_segment
