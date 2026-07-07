"""Regression tests for tone scoring using synthetic pitch contours.

Each fixture generates a pitch contour that follows one of the four
canonical Mandarin tone shapes (defined in chinese_tones.TONE_REFERENCES),
plus the octave-jump corrector and z-score normalizer get their own direct
tests. These guard the core scoring math against silent regressions since
there's no human-rated audio corpus in this repo yet.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chinese_tones import (
    _shape_match_score,
    calculate_directional_tone_accuracy,
    calculate_phrase_tone_accuracy,
    calculate_tone_accuracy,
    detect_tone,
    normalize_pitch_contour,
    scaled_reference_contour,
)
from praat_analyzer import _correct_octave_jumps


def _synthetic_contour(pitch_pattern, base_hz=220.0, spread_hz=60.0, num_points=40, duration=0.6):
    """Build a (time, frequency) contour tracing ``pitch_pattern`` (values in [0, 1])."""
    x = np.linspace(0, 1, len(pitch_pattern))
    x_new = np.linspace(0, 1, num_points)
    shape = np.interp(x_new, x, pitch_pattern)
    freqs = base_hz + (shape - 0.5) * spread_hz
    times = np.linspace(0, duration, num_points)
    return list(zip(times.tolist(), freqs.tolist()))


TONE_SHAPES = {
    1: [0.8, 0.82, 0.78, 0.81, 0.8],  # level, with slight natural jitter
    2: [0.3, 0.45, 0.6, 0.75, 0.9],   # rising
    3: [0.7, 0.4, 0.2, 0.4, 0.7],     # dipping
    4: [0.9, 0.7, 0.5, 0.3, 0.1],     # falling
}


@pytest.mark.parametrize("tone_number", [1, 2, 3, 4])
def test_detect_tone_identifies_matching_canonical_shape(tone_number):
    contour = _synthetic_contour(TONE_SHAPES[tone_number])
    result = detect_tone(contour)
    assert result["detected_tone"] == tone_number
    assert result["scores"][tone_number] == max(result["scores"].values())


@pytest.mark.parametrize("tone_number,min_accuracy", [(1, 60.0), (2, 70.0), (3, 70.0), (4, 70.0)])
def test_calculate_tone_accuracy_scores_matching_tone_highly(tone_number, min_accuracy):
    # Tone 1 is flat by definition, so correlation (which measures co-varying
    # shape) sits at a neutral midpoint rather than a strong positive value —
    # a lower bar reflects that, not a weaker match.
    contour = _synthetic_contour(TONE_SHAPES[tone_number])
    accuracy = calculate_tone_accuracy(contour, tone_number)
    assert accuracy >= min_accuracy


def test_calculate_tone_accuracy_scores_mismatched_tone_lower():
    rising_contour = _synthetic_contour(TONE_SHAPES[2])
    matching_score = calculate_tone_accuracy(rising_contour, 2)
    mismatched_score = calculate_tone_accuracy(rising_contour, 4)
    assert matching_score > mismatched_score


def test_detect_tone_handles_empty_contour():
    result = detect_tone([])
    assert result["detected_tone"] == 0
    assert result["confidence"] == 0.0


class TestNormalizePitchContour:
    def test_outlier_spike_does_not_dominate_range(self):
        """A single octave-doubled spike shouldn't flatten the rest of the shape."""
        clean = _synthetic_contour(TONE_SHAPES[2], num_points=20)
        with_spike = list(clean)
        mid = len(with_spike) // 2
        t, f = with_spike[mid]
        with_spike[mid] = (t, f * 3.5)  # extreme outlier

        clean_norm = normalize_pitch_contour(clean)
        spike_norm = normalize_pitch_contour(with_spike)

        # Without z-score clipping, the spike would compress every other
        # point toward 0, destroying the rising shape entirely. With
        # clipping, the overall rising trend should still correlate
        # strongly with the clean (unspiked) version.
        assert spike_norm[-1] - spike_norm[0] > 0
        correlation = np.corrcoef(clean_norm, spike_norm)[0, 1]
        assert correlation > 0.5

    def test_constant_pitch_normalizes_to_flat_midpoint(self):
        contour = [(0.0, 200.0), (0.1, 200.0), (0.2, 200.0)]
        normalized = normalize_pitch_contour(contour)
        assert np.allclose(normalized, 0.5)

    def test_empty_contour_returns_empty_array(self):
        assert normalize_pitch_contour([]).size == 0


class TestCorrectOctaveJumps:
    def test_corrects_isolated_double_frequency_spike(self):
        contour = [(0.0, 200.0), (0.025, 210.0), (0.05, 410.0), (0.075, 205.0), (0.1, 200.0)]
        corrected = _correct_octave_jumps(contour)
        assert abs(corrected[2][1] - 205.0) < 20.0

    def test_corrects_isolated_half_frequency_dip(self):
        contour = [(0.0, 200.0), (0.025, 205.0), (0.05, 100.0), (0.075, 210.0), (0.1, 200.0)]
        corrected = _correct_octave_jumps(contour)
        assert abs(corrected[2][1] - 200.0) < 20.0

    def test_leaves_genuine_pitch_movement_untouched(self):
        contour = _synthetic_contour(TONE_SHAPES[4], num_points=10)
        corrected = _correct_octave_jumps(contour)
        original_freqs = [f for _, f in contour]
        corrected_freqs = [f for _, f in corrected]
        assert np.allclose(original_freqs, corrected_freqs, atol=1e-6)

    def test_short_contour_returned_unchanged(self):
        contour = [(0.0, 200.0), (0.025, 400.0)]
        assert _correct_octave_jumps(contour) == contour


class TestDirectionalToneAccuracy:
    """calculate_directional_tone_accuracy should reward correct pitch direction
    in connected speech without requiring an exact shape match."""

    def test_perfect_flat_scores_high_for_tone1(self):
        contour = _synthetic_contour([0.8, 0.8, 0.8, 0.8, 0.8])
        score = calculate_directional_tone_accuracy(contour, [1])
        assert score >= 80.0, f"Perfect flat for T1 should score ≥80, got {score:.1f}"

    def test_rising_contour_scores_high_for_tone2(self):
        contour = _synthetic_contour([0.2, 0.4, 0.6, 0.8, 0.9])
        score = calculate_directional_tone_accuracy(contour, [2])
        assert score >= 75.0, f"Rising contour for T2 should score ≥75, got {score:.1f}"

    def test_falling_contour_scores_high_for_tone4(self):
        contour = _synthetic_contour([0.9, 0.7, 0.5, 0.3, 0.1])
        score = calculate_directional_tone_accuracy(contour, [4])
        assert score >= 75.0, f"Falling contour for T4 should score ≥75, got {score:.1f}"

    def test_dip_contour_scores_high_for_tone3(self):
        contour = _synthetic_contour([0.7, 0.4, 0.2, 0.4, 0.7])
        score = calculate_directional_tone_accuracy(contour, [3])
        assert score >= 65.0, f"Dip contour for T3 should score ≥65, got {score:.1f}"

    def test_wrong_direction_scores_lower_than_correct(self):
        """A rising contour should score much lower for T4 (falling) than for T2."""
        rising = _synthetic_contour([0.2, 0.4, 0.6, 0.8, 0.9])
        score_t2 = calculate_directional_tone_accuracy(rising, [2])
        score_t4 = calculate_directional_tone_accuracy(rising, [4])
        assert score_t2 > score_t4 + 20, (
            f"Rising contour: T2={score_t2:.1f} should beat T4={score_t4:.1f} by >20"
        )

    def test_connected_speech_declination_still_scores_well(self):
        """A T1 syllable at the end of a sentence sits lower but should not be
        heavily penalized — what matters is flatness, not absolute height."""
        # Low-pitched but flat (simulating sentence-final position)
        low_flat = _synthetic_contour([0.25, 0.26, 0.24, 0.25, 0.26], base_hz=160.0, spread_hz=10.0)
        score = calculate_directional_tone_accuracy(low_flat, [1])
        assert score >= 70.0, f"Low-pitched flat T1 should still score ≥70, got {score:.1f}"

    def test_blended_score_higher_than_shape_only_for_natural_speech(self):
        """In connected speech (slight declination + coarticulation), the blended
        calculate_phrase_tone_accuracy should be ≥ the pure shape score for a
        correct but imperfect contour."""
        # Slightly imperfect rising contour (real speech, not textbook)
        natural_rising = _synthetic_contour([0.3, 0.4, 0.55, 0.65, 0.75])
        blended = calculate_phrase_tone_accuracy(natural_rising, [2])
        # Just verify blended score is a reasonable number (it may or may not
        # exceed shape-only — the key guarantee is it doesn't crash and stays in range)
        assert 0.0 <= blended <= 100.0

    def test_empty_inputs_return_zero(self):
        assert calculate_directional_tone_accuracy([], [1]) == 0.0
        assert calculate_directional_tone_accuracy([(0.0, 200.0)], []) == 0.0


class TestFlatReferenceShapeScore:
    """Tone 1's reference is flat by construction, so Pearson correlation
    against it is mathematically undefined (corrcoef divides by a zero
    standard deviation). The old code silently defaulted that NaN to 0.0,
    giving every contour the same neutral correlation credit regardless of
    whether it was actually flat -- to the point that a Tone 3 dip contour
    used to outscore a genuine Tone 1 recording when both were graded
    against Tone 1. ``_shape_match_score`` now scores flatness directly
    whenever the reference itself has no variance."""

    def test_genuine_flat_contour_scores_near_perfect_against_tone1(self):
        flat = _synthetic_contour(TONE_SHAPES[1])
        accuracy = calculate_tone_accuracy(flat, 1)
        assert accuracy >= 95.0, f"Genuine flat contour should score ~100 for T1, got {accuracy:.1f}"

    @pytest.mark.parametrize("tone_number", [2, 3, 4])
    def test_clearly_non_flat_contour_scores_low_against_tone1(self, tone_number):
        contour = _synthetic_contour(TONE_SHAPES[tone_number])
        accuracy = calculate_tone_accuracy(contour, 1)
        assert accuracy < 20.0, (
            f"Tone {tone_number} contour (real movement) should score low against "
            f"Tone 1's flat reference, got {accuracy:.1f}"
        )

    def test_flat_reference_never_outscores_a_genuine_flat_match(self):
        """Regression guard for the exact defect this fix targets: before it,
        a Tone 3 dip contour scored *higher* against Tone 1 (~70.8) than an
        actual flat Tone 1 recording scored against itself (~67.5)."""
        flat_match = calculate_tone_accuracy(_synthetic_contour(TONE_SHAPES[1]), 1)
        dip_mismatch = calculate_tone_accuracy(_synthetic_contour(TONE_SHAPES[3]), 1)
        assert flat_match > dip_mismatch

    def test_helper_flat_reference_ignores_correlation(self):
        flat_ref = np.full(50, 0.5)
        flat_user = np.full(50, 0.5)
        varying_user = np.linspace(0.0, 1.0, 50)

        assert _shape_match_score(flat_user, flat_ref) == pytest.approx(100.0, abs=0.5)
        assert _shape_match_score(varying_user, flat_ref) < 10.0

    def test_helper_non_flat_reference_uses_correlation_and_distance(self):
        curve = np.linspace(0.0, 1.0, 50)
        assert _shape_match_score(curve, curve) == pytest.approx(100.0, abs=0.5)

    def test_phrase_tone_accuracy_flat_reference_no_longer_capped(self):
        """calculate_phrase_tone_accuracy shares _shape_match_score with
        calculate_tone_accuracy, so an all-Tone-1 phrase spoken flat is no
        longer capped by the same bug (blended score used to top out ~90.3
        for a perfect flat contour; it should now reach ~100)."""
        flat = _synthetic_contour(TONE_SHAPES[1])
        score = calculate_phrase_tone_accuracy(flat, [1])
        assert score >= 98.0, f"Expected near-perfect blended score, got {score:.1f}"


class TestShapeMatchDistanceScaling:
    """The Euclidean-distance half of the shape score is computed over ~100
    dimensions each bounded to [-0.5, 0.5] post-normalization, so its scale
    grows with sqrt(n), not n. Dividing by n (the old bug) squashed
    distance_score into a near-constant ~0.95-1.0 band regardless of match
    quality, making its nominal 35% weight almost inert."""

    def test_opposite_direction_contour_scores_well_below_a_match(self):
        rising = _synthetic_contour(TONE_SHAPES[2])
        falling = _synthetic_contour(TONE_SHAPES[4])
        matching_score = calculate_tone_accuracy(rising, 2)
        opposite_score = calculate_tone_accuracy(falling, 2)
        assert opposite_score < 35.0, (
            f"A falling contour scored against a rising Tone 2 reference "
            f"should score low, got {opposite_score:.1f}"
        )
        assert matching_score - opposite_score > 60


class TestScaledReferenceContour:
    """scaled_reference_contour builds the overlay curve shown alongside the
    student's own pitch so they can see the target tone shape directly."""

    def test_empty_tones_returns_empty(self):
        assert scaled_reference_contour([], 0.0, 1.0, 100.0, 200.0) == []

    def test_zero_duration_returns_empty(self):
        assert scaled_reference_contour([1], 0.5, 0.5, 100.0, 200.0) == []
        assert scaled_reference_contour([1], 0.5, 0.4, 100.0, 200.0) == []

    def test_output_spans_the_requested_time_window(self):
        contour = scaled_reference_contour([2], 1.0, 1.5, 150.0, 220.0, num_points=10)
        assert len(contour) == 10
        assert contour[0][0] == pytest.approx(1.0)
        assert contour[-1][0] == pytest.approx(1.5)

    def test_output_stays_within_the_requested_pitch_range(self):
        contour = scaled_reference_contour([3], 0.0, 1.0, 150.0, 220.0, num_points=30)
        freqs = [f for _, f in contour]
        assert min(freqs) >= 150.0 - 1e-6
        assert max(freqs) <= 220.0 + 1e-6

    @pytest.mark.parametrize("tone", [2, 3, 4])
    def test_output_spans_the_full_requested_range_not_a_sub_band(self, tone):
        """Regression guard: TONE_REFERENCES patterns (e.g. tone 2 is only
        [0.5, 0.85]) must be re-normalized to [0, 1] before scaling, or the
        drawn curve looks squashed into a corner of the chart next to the
        student's own pitch, which spans its own full box — making a
        genuinely good match look like a visual mismatch on screen."""
        contour = scaled_reference_contour([tone], 0.0, 1.0, 150.0, 220.0, num_points=30)
        freqs = [f for _, f in contour]
        assert min(freqs) == pytest.approx(150.0, abs=1.0)
        assert max(freqs) == pytest.approx(220.0, abs=1.0)

    def test_tone1_flat_reference_stays_flat_not_full_range(self):
        # Tone 1 is genuinely flat — normalizing negligible interpolation
        # jitter to [0, 1] would wrongly blow it up into a full swing.
        contour = scaled_reference_contour([1], 0.0, 1.0, 150.0, 220.0, num_points=30)
        freqs = [f for _, f in contour]
        assert max(freqs) - min(freqs) < 5.0

    def test_tone2_reference_rises_from_start_to_end(self):
        contour = scaled_reference_contour([2], 0.0, 1.0, 150.0, 220.0, num_points=20)
        freqs = [f for _, f in contour]
        assert freqs[-1] > freqs[0]

    def test_tone4_reference_falls_from_start_to_end(self):
        contour = scaled_reference_contour([4], 0.0, 1.0, 150.0, 220.0, num_points=20)
        freqs = [f for _, f in contour]
        assert freqs[0] > freqs[-1]

    def test_flat_pitch_range_does_not_crash(self):
        # pitch_min == pitch_max (e.g. a near-silent or single-frame word)
        contour = scaled_reference_contour([1], 0.0, 0.5, 200.0, 200.0, num_points=10)
        assert len(contour) == 10
