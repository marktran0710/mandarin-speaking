"""Per-syllable pass gate for word prosody.

The word-level tone/shape scores average across syllables, which lets a
clean second syllable hide a wrong-direction first one (the exact case that
motivated the gate: 在家 said as rising+level scoring 73% overall). These
tests pin the per-syllable breakdown (`syllables`) and the min-rule verdict
(`passed`) that estimate_word_prosody now attaches to each Chinese word.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chinese_tones import directional_tone_scores
from praat_analyzer import SYLLABLE_PASS_THRESHOLD, estimate_word_prosody


def _contour(pitch_pattern, base_hz=220.0, spread_hz=160.0, num_points=60, duration=0.8):
    x = np.linspace(0, 1, len(pitch_pattern))
    x_new = np.linspace(0, 1, num_points)
    shape = np.interp(x_new, x, pitch_pattern)
    freqs = base_hz + (shape - 0.5) * spread_hz
    times = np.linspace(0, duration, num_points)
    return list(zip(times.tolist(), freqs.tolist()))


# 在家 = T4 (falling) + T1 (level). The fall spans the first half; the
# reset up to the level syllable is centered on the 50% boundary so the
# jump doesn't bleed into either syllable's scoring window. The plateau
# carries mild jitter (like real speech) so the MAD-based normalizer sees a
# genuine pitch range rather than collapsing the whole word to "flat".
_CORRECT_ZAIJIA = [0.95, 0.75, 0.55, 0.35, 0.79, 0.75, 0.78, 0.74]
# The bug report's shape: a steady rise across both syllables.
_RISING_ZAIJIA = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def test_directional_tone_scores_returns_one_score_per_tone():
    scores = directional_tone_scores(_contour(_CORRECT_ZAIJIA), [4, 1])
    assert len(scores) == 2
    assert all(0.0 <= s <= 100.0 for s in scores)


def test_directional_tone_scores_empty_for_no_input():
    assert directional_tone_scores([], [4, 1]) == []
    assert directional_tone_scores(_contour(_CORRECT_ZAIJIA), []) == []


def test_correct_zaijia_passes_both_syllables():
    segments = estimate_word_prosody(_contour(_CORRECT_ZAIJIA), "在家")
    assert len(segments) == 1
    word = segments[0]
    assert [s["char"] for s in word["syllables"]] == ["在", "家"]
    assert [s["tone"] for s in word["syllables"]] == [4, 1]
    assert all(s["passed"] for s in word["syllables"])
    assert word["passed"] is True


def test_rising_zaijia_fails_first_syllable_and_word():
    """A rise where T4 should fall must fail 在 — and the word — even though
    the whole-word average can look acceptable."""
    segments = estimate_word_prosody(_contour(_RISING_ZAIJIA), "在家")
    assert len(segments) == 1
    word = segments[0]
    zai = word["syllables"][0]
    assert zai["char"] == "在"
    assert zai["passed"] is False
    assert zai["score"] < SYLLABLE_PASS_THRESHOLD
    assert word["passed"] is False


def test_syllable_verdict_uses_min_not_mean():
    segments = estimate_word_prosody(_contour(_RISING_ZAIJIA), "在家")
    word = segments[0]
    scores = [s["score"] for s in word["syllables"]]
    # The failing syllable is below the bar even if the mean is above it —
    # the verdict must follow the min.
    assert min(scores) < SYLLABLE_PASS_THRESHOLD
    assert word["passed"] is (min(scores) >= SYLLABLE_PASS_THRESHOLD)


def test_short_segment_gets_benefit_of_the_doubt():
    # Two words share a tiny contour: each word's slice is too short to
    # judge, so syllables carry the neutral 65 and the word passes.
    contour = _contour([0.5, 0.5, 0.5], num_points=7, duration=0.1)
    segments = estimate_word_prosody(contour, "在家 很好")
    for word in segments:
        if word["syllables"]:
            assert word["passed"] is not None


def test_non_chinese_token_has_no_gate():
    segments = estimate_word_prosody(_contour(_CORRECT_ZAIJIA), "OK")
    assert len(segments) == 1
    assert segments[0]["syllables"] == []
    assert segments[0]["passed"] is None
