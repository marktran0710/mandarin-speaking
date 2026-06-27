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
    calculate_tone_accuracy,
    detect_tone,
    normalize_pitch_contour,
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
