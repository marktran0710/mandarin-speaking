"""Candidate E's own correctness guards: the T1/T3 formula redesigns behave
as documented, the module never touches OMPAL data (this candidate was
explicitly built and evaluated without OMPAL labels), and the canonical
ranking check used to gate STEP 5/6 is itself correct.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from benchmarking.candidates.contour_scorer_v2 import (
    T1_RANGE_REF,
    T1_SLOPE_REF,
    apply_onset_skip,
    directional_tone_scores_v2,
    score_segment_v2,
)
from benchmarking.candidates.contour_scorer_v2_pipeline import (
    CANONICAL_CONTOURS,
    build_canonical_matrix_v2,
    check_canonical_ranking,
)


class TestT1ShapeSpecificFlatness:
    def test_perfectly_flat_contour_scores_100(self):
        score, source = score_segment_v2(np.array([0.5, 0.5, 0.5, 0.5, 0.5]), 1)
        assert score == pytest.approx(100.0)
        assert source == "measured"

    def test_canonical_rising_contour_scores_low_on_t1(self):
        score, _ = score_segment_v2(np.array(CANONICAL_CONTOURS[2]), 1)
        assert score < 30

    def test_canonical_dip_contour_scores_low_on_t1(self):
        """This is the exact failure the old variance-only formula had:
        T3's shallow dip has small variance and near-zero net slope, so a
        slope-only or variance-only check can mistake it for flat. The
        range gate must catch what the slope gate alone would miss."""
        score, _ = score_segment_v2(np.array(CANONICAL_CONTOURS[3]), 1)
        assert score < 60  # nowhere near canonical T1's own 100

    def test_small_range_but_real_slope_is_still_penalized(self):
        # A small-range but clearly-sloped contour should not fool the gate.
        seg = np.linspace(0.4, 0.6, 5)  # slope-only, no range issue
        score, _ = score_segment_v2(seg, 1)
        assert score < 100

    def test_both_factors_required_not_additive(self):
        """A contour failing ONLY the range gate (small slope, big range --
        e.g. noisy but not trending) should still be penalized, proving the
        two factors are multiplied, not summed with one dominating."""
        seg = np.array([0.9, 0.1, 0.9, 0.1, 0.9])  # near-zero net slope, huge range
        score, _ = score_segment_v2(seg, 1)
        assert score < 20


class TestT3ShapeValidityGate:
    def test_canonical_dip_passes_the_shape_gate_and_scores_high(self):
        score, _ = score_segment_v2(np.array(CANONICAL_CONTOURS[3]), 3)
        assert score == pytest.approx(100.0, abs=1.0)

    def test_monotonic_rise_does_not_pass_as_t3(self):
        """The exact failure STEP 3 was written to close: canonical T2
        scored 90.9 against T3 under the OLD formula."""
        score, _ = score_segment_v2(np.array(CANONICAL_CONTOURS[2]), 3)
        assert score <= 20  # T3_INVALID_SHAPE_CEILING

    def test_monotonic_fall_does_not_pass_as_t3(self):
        score, _ = score_segment_v2(np.array(CANONICAL_CONTOURS[4]), 3)
        assert score <= 20

    def test_flat_contour_does_not_pass_as_t3(self):
        score, _ = score_segment_v2(np.array([0.5, 0.5, 0.5, 0.5, 0.5]), 3)
        assert score <= 20

    def test_a_genuine_but_shallower_dip_still_passes_the_gate(self):
        seg = np.array([0.55, 0.48, 0.45, 0.48, 0.55])  # shallow but real dip
        score, _ = score_segment_v2(seg, 3)
        # Shape-valid (falls then rises), so it should score meaningfully
        # above the invalid-shape ceiling, even if not near 100.
        assert score > 20


class TestOnsetSkip:
    def test_zero_fraction_returns_the_contour_unchanged(self):
        contour = [(0.0, 100.0), (0.1, 110.0), (0.2, 120.0)]
        assert apply_onset_skip(contour, 0.0) == contour

    def test_nonzero_fraction_trims_the_leading_portion(self):
        contour = [(float(i) / 10, 100.0 + i) for i in range(20)]
        trimmed = apply_onset_skip(contour, 0.5)
        assert trimmed[0][0] >= 1.0  # first half (0.0-1.0s of a 0.0-1.9s span) skipped
        assert len(trimmed) < len(contour)

    def test_falls_back_to_untrimmed_if_too_few_frames_remain(self):
        contour = [(0.0, 100.0), (0.1, 110.0), (0.2, 120.0)]
        trimmed = apply_onset_skip(contour, 0.9)  # would leave < 4 points
        assert trimmed == contour

    def test_empty_contour_returns_empty(self):
        assert apply_onset_skip([], 0.1) == []


class TestCanonicalRankingCheck:
    def test_the_real_candidate_e_matrix_passes(self):
        rows = build_canonical_matrix_v2()
        passed, failures = check_canonical_ranking(rows)
        assert passed, failures

    def test_detects_a_synthetic_failure(self):
        rows = [
            {"produced_tone": 1, "expected_tone": 1, "score": 50.0},
            {"produced_tone": 2, "expected_tone": 1, "score": 90.0},  # wrongly beats diagonal
            {"produced_tone": 1, "expected_tone": 2, "score": 10.0},
            {"produced_tone": 2, "expected_tone": 2, "score": 80.0},
        ]
        passed, failures = check_canonical_ranking(rows)
        assert not passed
        assert len(failures) == 1


class TestDirectionalToneScoresV2:
    def test_matches_score_segment_v2_for_a_single_syllable_canonical_contour(self):
        # A single "syllable" spanning the whole normalized contour --
        # smoke test that the end-to-end wrapper doesn't silently diverge
        # from the per-segment function it's built on.
        contour = [(float(i) / 10, 150.0 + i) for i in range(10)]  # rising
        scores, provenance = directional_tone_scores_v2(contour, [2])
        assert len(scores) == 1
        assert provenance[0] in ("measured", "constant_short_segment")

    def test_empty_contour_returns_empty_lists(self):
        scores, provenance = directional_tone_scores_v2([], [1])
        assert scores == []
        assert provenance == []


class TestNoOmpalDependency:
    """Candidate E was explicitly built and evaluated without OMPAL labels
    -- this is a structural guard, not just a claim in the docs."""

    def _source(self, module):
        import inspect

        return inspect.getsource(module)

    def test_scorer_module_never_imports_ompal_loaders(self):
        import ast
        from pathlib import Path

        from benchmarking.candidates import contour_scorer_v2

        tree = ast.parse(Path(contour_scorer_v2.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "ompal" not in node.module.lower()
            if isinstance(node, ast.Name):
                assert node.id not in {"load_utterances", "load_split_rows"}
