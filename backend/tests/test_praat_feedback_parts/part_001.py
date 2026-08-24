"""Unit tests for the Praat prosody feedback pipeline.

Tests cover every public and internal function that produces human-readable
feedback text, graded from unit-level (single-function) to integration-level
(full generate_comprehensive_feedback).

Key invariants guarded here:
  1. Feedback text NEVER contradicts the numeric score shown alongside it.
  2. Threshold boundaries behave as documented (exact cutoffs included).
  3. Edge cases (empty input, single word, all-neutral tones, zero speech
     rate) never crash and always return a non-empty string.
  4. The "Good match" string in _word_prosody_feedback is stable — the
     frontend's prosodyImprovementTip keyes off startsWith("Good match").
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chinese_tones import (
    generate_comprehensive_feedback,
    generate_phrase_tone_feedback,
    get_tone_feedback,
)
from praat_analyzer import (
    _classify_content_word,
    _contour_shape,
    _word_prosody_feedback,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_contour(pattern, base_hz=200.0, spread_hz=60.0, n=40, duration=0.5):
    """Build a (time, freq) list that traces *pattern* (values 0-1)."""
    x = np.linspace(0, 1, len(pattern))
    xn = np.linspace(0, 1, n)
    shape = np.interp(xn, x, pattern)
    freqs = base_hz + (shape - 0.5) * spread_hz
    times = np.linspace(0, duration, n)
    return list(zip(times.tolist(), freqs.tolist()))


def _make_freq_array(pattern, base=200.0, spread=60.0, n=20):
    """Return a bare numpy array of frequencies (for _contour_shape)."""
    x = np.linspace(0, 1, len(pattern))
    xn = np.linspace(0, 1, n)
    shape = np.interp(xn, x, pattern)
    return np.array(base + (shape - 0.5) * spread)


def _word(token, tones, tone_accuracy):
    return {
        "token": token,
        "expected_tones": tones,
        "tone_accuracy": tone_accuracy,
    }


# ---------------------------------------------------------------------------
# _contour_shape
# ---------------------------------------------------------------------------

class TestContourShape:
    def test_dip_when_middle_lower_than_both_ends(self):
        freqs = _make_freq_array([0.8, 0.5, 0.1, 0.5, 0.8])  # V shape
        slope = float(freqs[-1] - freqs[0])
        pitch_range = float(np.max(freqs) - np.min(freqs))
        assert _contour_shape(freqs, slope, pitch_range) == "dip"

    def test_dip_priority_over_slope(self):
        # Even if end > start (positive slope), dip wins when middle is lowest
        freqs = _make_freq_array([0.6, 0.2, 0.1, 0.4, 0.8])
        slope = float(freqs[-1] - freqs[0])
        pitch_range = float(np.max(freqs) - np.min(freqs))
        assert _contour_shape(freqs, slope, pitch_range) == "dip"

    def test_level_when_small_pitch_range(self):
        # Range < 18 Hz regardless of slope → level
        freqs = np.array([200.0, 201.0, 200.5, 202.0, 201.5])
        slope = float(freqs[-1] - freqs[0])
        pitch_range = float(np.max(freqs) - np.min(freqs))
        assert pitch_range < 18
        assert _contour_shape(freqs, slope, pitch_range) == "level"

    def test_rising_when_slope_above_threshold(self):
        freqs = _make_freq_array([0.1, 0.4, 0.7, 0.9, 1.0])
        slope = float(freqs[-1] - freqs[0])
        pitch_range = float(np.max(freqs) - np.min(freqs))
        assert slope > 12
        assert _contour_shape(freqs, slope, pitch_range) == "rising"

    def test_falling_when_slope_below_negative_threshold(self):
        freqs = _make_freq_array([1.0, 0.7, 0.4, 0.2, 0.0])
        slope = float(freqs[-1] - freqs[0])
        pitch_range = float(np.max(freqs) - np.min(freqs))
        assert slope < -12
        assert _contour_shape(freqs, slope, pitch_range) == "falling"

    def test_variable_when_no_clear_direction(self):
        # Range ≥ 18 Hz but no dominant slope, middle not lowest
        freqs = np.array([200.0, 220.0, 240.0, 210.0, 230.0])
        slope = float(freqs[-1] - freqs[0])   # +30 Hz but noisy
        pitch_range = float(np.max(freqs) - np.min(freqs))  # 40 Hz
        # slope=30 > 12, so this will be "rising" — let's pick a truly ambiguous case
        freqs2 = np.array([210.0, 230.0, 240.0, 220.0, 215.0])
        slope2 = float(freqs2[-1] - freqs2[0])   # +5 Hz
        pitch_range2 = float(np.max(freqs2) - np.min(freqs2))  # 30 Hz
        # middle (index 2) = 240 which is > both ends → not a dip
        assert _contour_shape(freqs2, slope2, pitch_range2) == "variable"

    def test_short_array_handled(self):
        # Arrays shorter than 3 cannot form a dip — must not crash
        freqs = np.array([200.0, 180.0])
        slope = float(freqs[-1] - freqs[0])
        pitch_range = float(np.max(freqs) - np.min(freqs))
        shape = _contour_shape(freqs, slope, pitch_range)
        assert isinstance(shape, str)


# ---------------------------------------------------------------------------
# _word_prosody_feedback — threshold invariants
# ---------------------------------------------------------------------------

class TestWordProsodyFeedback:
    """The feedback string must never contradict the numeric score.

    Frontend note: prosodyImprovementTip in StoryRecorder.tsx keys off
    feedback.startsWith("Good match") to decide whether to show a tip.
    That string must remain stable.
    """

    # ── with expected_tones ──────────────────────────────────────────────────

    @pytest.mark.parametrize("score", [68.0, 75.0, 90.0, 100.0])
    def test_good_match_at_and_above_68(self, score):
        fb = _word_prosody_feedback("rising", 40.0, [2], score)
        assert fb.startswith("Good match"), (
            f"score={score}: expected 'Good match...', got {fb!r}"
        )

    @pytest.mark.parametrize("score", [48.0, 55.0, 67.9])
    def test_recognizable_between_48_and_68(self, score):
        fb = _word_prosody_feedback("falling", 50.0, [4], score)
        assert "Recognizable" in fb, (
            f"score={score}: expected 'Recognizable...', got {fb!r}"
        )
        assert "contrast" in fb.lower()

    @pytest.mark.parametrize("score", [0.0, 30.0, 47.9])
    def test_doesnt_match_below_48(self, score):
        fb = _word_prosody_feedback("level", 10.0, [1], score)
        assert "Expected" in fb and "doesn't match" in fb, (
            f"score={score}: expected 'Expected ... doesn't match', got {fb!r}"
        )

    def test_exact_boundary_68_is_good_not_recognizable(self):
        fb = _word_prosody_feedback("dip", 30.0, [3], 68.0)
        assert fb.startswith("Good match")

    def test_exact_boundary_48_is_recognizable_not_doesnt_match(self):
        fb = _word_prosody_feedback("rising", 40.0, [2], 48.0)
        assert "Recognizable" in fb
        assert "doesn't match" not in fb

    def test_multi_tone_label_joined_with_plus(self):
        # 媽媽 has tones [1, 1] → label "Tone 1 (level)+Tone 1 (level)"
        fb = _word_prosody_feedback("level", 5.0, [1, 1], 80.0)
        assert "+" in fb, f"Multi-tone label should use '+', got {fb!r}"

    def test_neutral_tone_5_label(self):
        fb = _word_prosody_feedback("level", 5.0, [5], 70.0)
        assert "neutral" in fb.lower()

    # ── without expected_tones (open-vocabulary) ─────────────────────────────

    @pytest.mark.parametrize("shape,expected_substring", [
        ("level",    "Stable pitch"),
        ("rising",   "rises"),
        ("falling",  "falls"),
        ("dip",      "dips"),
    ])
    def test_contour_shape_variants_without_expected_tones(self, shape, expected_substring):
        fb = _word_prosody_feedback(shape, 40.0, None, 0.0)
        assert expected_substring.lower() in fb.lower(), (
            f"shape={shape!r}: expected {expected_substring!r} in {fb!r}"
        )

    def test_large_pitch_range_without_expected_tones(self):
        fb = _word_prosody_feedback("variable", 100.0, None, 0.0)
        assert "Large pitch movement" in fb

    def test_small_pitch_range_variable_without_expected_tones(self):
        fb = _word_prosody_feedback("variable", 30.0, None, 0.0)
        assert "Some pitch movement" in fb

    def test_empty_expected_tones_list_treated_as_no_tones(self):
        # [] is falsy — should fall through to contour_shape branch
        fb = _word_prosody_feedback("rising", 40.0, [], 85.0)
        assert "rises" in fb.lower()


# ---------------------------------------------------------------------------
# generate_phrase_tone_feedback — lead, weakest, strongest
# ---------------------------------------------------------------------------

class TestGeneratePhraseToneFeedback:

    # ── lead sentence ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize("accuracy,expected_lead", [
        (76.0,  "Excellent"),
        (100.0, "Excellent"),
        (75.1,  "Excellent"),
        (75.0,  "Good"),          # boundary: ≤75 is NOT "Excellent"
        (58.1,  "Good"),
        (58.0,  "recognizable"),  # boundary: ≤58 is NOT "Good"
        (44.1,  "recognizable"),
        (44.0,  "contrast"),      # boundary: ≤44 is NOT "recognizable"
        (0.0,   "contrast"),
    ])
    def test_lead_matches_accuracy_band(self, accuracy, expected_lead):
        words = [_word("媽", [1], accuracy)]
        fb = generate_phrase_tone_feedback(words, accuracy)
        assert expected_lead.lower() in fb.lower(), (
            f"accuracy={accuracy}: expected {expected_lead!r} in lead, got {fb!r}"
        )

    # ── no scored words ───────────────────────────────────────────────────────

    def test_empty_word_prosody_returns_fallback(self):
        fb = generate_phrase_tone_feedback([], 80.0)
        assert "No clear tone" in fb

    def test_all_words_lack_expected_tones_returns_fallback(self):
        words = [{"token": "a", "expected_tones": [], "tone_accuracy": 90.0},
                 {"token": "b", "expected_tones": None, "tone_accuracy": 90.0}]
        fb = generate_phrase_tone_feedback(words, 90.0)
        assert "No clear tone" in fb

    # ── weakest word ──────────────────────────────────────────────────────────

    def test_weakest_word_mentioned_when_score_below_58(self):
        words = [_word("好", [3], 80.0), _word("嗎", [5], 40.0)]
        fb = generate_phrase_tone_feedback(words, 60.0)
        assert "嗎" in fb
        assert "needs the clearest work" in fb

    def test_weakest_word_not_mentioned_when_score_at_or_above_58(self):
        words = [_word("媽", [1], 80.0), _word("麻", [2], 58.0)]
        fb = generate_phrase_tone_feedback(words, 69.0)
        # 58.0 is NOT < 58 → no "needs the clearest work"
        assert "needs the clearest work" not in fb

    def test_weakest_word_just_below_58(self):
        words = [_word("馬", [3], 57.9)]
        fb = generate_phrase_tone_feedback(words, 57.9)
        assert "馬" in fb and "needs the clearest work" in fb

    # ── strongest word ────────────────────────────────────────────────────────

    def test_strongest_word_praised_when_different_from_weakest_and_above_68(self):
        words = [_word("好", [3], 30.0), _word("媽", [1], 85.0)]
        fb = generate_phrase_tone_feedback(words, 57.5)
        assert "媽" in fb and "sounded solid" in fb

    def test_strongest_word_not_praised_when_same_as_weakest(self):
        words = [_word("好", [3], 80.0)]  # only one word
        fb = generate_phrase_tone_feedback(words, 80.0)
        assert "sounded solid" not in fb

    def test_strongest_not_praised_when_score_below_68(self):
        words = [_word("好", [3], 30.0), _word("嗎", [5], 65.0)]
        fb = generate_phrase_tone_feedback(words, 47.5)
        assert "sounded solid" not in fb

    # ── tone labels ───────────────────────────────────────────────────────────

    def test_weakest_word_tone_label_present(self):
        words = [_word("馬", [3], 40.0)]
        fb = generate_phrase_tone_feedback(words, 40.0)
        # _tone_label(3) → TONE_REFERENCES[3]["name"] = "Falling-Rising"
        assert "馬" in fb
        assert "(" in fb and ")" in fb  # label wrapped in parens

    def test_multi_tone_word_label_joined_with_plus(self):
        words = [_word("媽媽", [1, 1], 35.0)]
        fb = generate_phrase_tone_feedback(words, 35.0)
        assert "+" in fb, f"Multi-tone label missing '+': {fb!r}"

    # ── consistency invariant ─────────────────────────────────────────────────

    def test_feedback_never_says_excellent_when_accuracy_is_low(self):
        words = [_word("好", [3], 20.0)]
        fb = generate_phrase_tone_feedback(words, 20.0)
        assert "Excellent" not in fb

    def test_feedback_result_is_always_non_empty_string(self):
        for accuracy in [0.0, 44.0, 58.0, 75.0, 100.0]:
            words = [_word("好", [3], accuracy)]
            fb = generate_phrase_tone_feedback(words, accuracy)
            assert isinstance(fb, str) and len(fb) > 0


class TestConnectedSpeechCalibration:
    """Option A: connected speech (multiple words) uses relaxed grading bands
    because adjacent tones compress and declination lowers the whole phrase, so
    a fluent sentence tops out ~10 pts below an isolated syllable. Single words
    keep the strict isolated-syllable bands.

    Bands: 1 word → 75/58/44; 2 words → 70/54/41; 3+ words → 65/50/38.
    """

    def _phrase(self, n_words, avg_accuracy):
        """n scored words whose scores average to avg_accuracy."""
        return [_word(f"字{i}", [1], avg_accuracy) for i in range(n_words)]

    def test_three_word_phrase_at_66_is_excellent(self):
        # 66 > 65 (3-word Excellent band) but < 75 (single-word band)
        fb = generate_phrase_tone_feedback(self._phrase(3, 66.0), 66.0)
        assert "Excellent" in fb

    def test_same_66_score_as_single_word_is_only_good(self):
        # Identical score, but one word → strict band → NOT excellent
        fb = generate_phrase_tone_feedback([_word("媽", [1], 66.0)], 66.0)
        assert "Excellent" not in fb
        assert "Good" in fb

    def test_two_word_band_boundary_at_70(self):
        assert "Excellent" in generate_phrase_tone_feedback(self._phrase(2, 71.0), 71.0)
        assert "Excellent" not in generate_phrase_tone_feedback(self._phrase(2, 70.0), 70.0)

    def test_three_word_band_boundary_at_65(self):
        assert "Excellent" in generate_phrase_tone_feedback(self._phrase(3, 66.0), 66.0)
        assert "Excellent" not in generate_phrase_tone_feedback(self._phrase(3, 65.0), 65.0)

    def test_relaxed_bands_never_exceed_single_word_strictness(self):
        # A multi-word phrase should never be graded STRICTER than a single word
        for score in [40.0, 50.0, 60.0, 70.0, 80.0]:
            single = generate_phrase_tone_feedback([_word("媽", [1], score)], score)
            multi = generate_phrase_tone_feedback(self._phrase(4, score), score)
            rank = {"Excellent": 3, "Good": 2, "recognizable": 1}
            def band(fb):
                for k, v in rank.items():
                    if k.lower() in fb.lower():
                        return v
                return 0
            assert band(multi) >= band(single), (
                f"score={score}: multi-word band should be ≥ single-word band"
            )

    def test_low_connected_speech_still_flags_contrast(self):
        # Even relaxed, a genuinely poor phrase (below the 3+ word floor of 38)
        # must still say tones need contrast — calibration is not a free pass.
        fb = generate_phrase_tone_feedback(self._phrase(3, 30.0), 30.0)
        assert "contrast" in fb.lower()


# ---------------------------------------------------------------------------
# generate_comprehensive_feedback — integration
# ---------------------------------------------------------------------------

class TestGenerateComprehensiveFeedback:
    """Integration tests: the top-level function that combines tone, rate, and
    fluency feedback into a single paragraph."""

    _contour = _make_contour([0.5, 0.6, 0.7, 0.8, 0.9])  # rising
    _words = [_word("媽", [1], 80.0)]

    def test_uses_phrase_feedback_when_word_prosody_provided(self):
        fb = generate_comprehensive_feedback(
            detected_tone=1, tone_accuracy=80.0,
            speech_rate=4.0, fluency=85.0,
            pitch_contour=self._contour,
            word_prosody=self._words,
        )
        # phrase feedback leads with "Excellent" (accuracy=80 > 75)
        assert "Excellent tone accuracy" in fb

    def test_falls_back_to_get_tone_feedback_when_no_word_prosody(self):
        fb = generate_comprehensive_feedback(
            detected_tone=2, tone_accuracy=90.0,
            speech_rate=4.0, fluency=85.0,
            pitch_contour=self._contour,
            word_prosody=None,
        )
        # get_tone_feedback for T2 with accuracy 90 → "Excellent Rising tone."
        assert "Excellent" in fb and "Rising" in fb

    # ── speech rate bands ─────────────────────────────────────────────────────

    @pytest.mark.parametrize("rate,substring", [
        (2.0, "faster"),
        (3.5, "comfortable"),
        (4.5, "comfortable"),
        (5.5, "comfortable"),
        (6.0, "Slow down"),
    ])
    def test_speech_rate_feedback(self, rate, substring):
        fb = generate_comprehensive_feedback(
            detected_tone=1, tone_accuracy=80.0,
            speech_rate=rate, fluency=85.0,
            pitch_contour=self._contour,
            word_prosody=self._words,
        )
        assert substring.lower() in fb.lower(), (
            f"rate={rate}: expected {substring!r} in feedback, got {fb!r}"
        )

    def test_zero_speech_rate_omitted(self):
        fb = generate_comprehensive_feedback(
            detected_tone=1, tone_accuracy=80.0,
            speech_rate=0.0, fluency=85.0,
            pitch_contour=self._contour,
            word_prosody=self._words,
        )
        assert "syllables/sec" not in fb

    def test_speech_rate_exact_boundary_3_5_is_comfortable(self):
        fb = generate_comprehensive_feedback(
            detected_tone=1, tone_accuracy=80.0,
            speech_rate=3.5, fluency=85.0,
            pitch_contour=self._contour,
            word_prosody=self._words,
        )
        assert "comfortable" in fb.lower()

    def test_speech_rate_exact_boundary_5_5_is_comfortable(self):
        fb = generate_comprehensive_feedback(
            detected_tone=1, tone_accuracy=80.0,
            speech_rate=5.5, fluency=85.0,
            pitch_contour=self._contour,
            word_prosody=self._words,
        )
        assert "comfortable" in fb.lower()

    # ── fluency bands ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize("fluency,substring", [
        (81.0, "smooth"),
        (80.1, "smooth"),
        (80.0, "smoother"),   # boundary: ≤80 is NOT "smooth"
        (65.0, "smoother"),
        (60.1, "smoother"),
        (60.0, "shorter"),    # boundary: ≤60 is NOT "smoother"
        (0.0,  "shorter"),
    ])
    def test_fluency_bands(self, fluency, substring):
        fb = generate_comprehensive_feedback(
            detected_tone=1, tone_accuracy=80.0,
            speech_rate=4.0, fluency=fluency,
            pitch_contour=self._contour,
            word_prosody=self._words,
        )
        assert substring.lower() in fb.lower(), (
            f"fluency={fluency}: expected {substring!r} in {fb!r}"
        )

    def test_output_is_non_empty_string_for_all_inputs(self):
        """Must never crash or return empty, regardless of inputs."""
        fb = generate_comprehensive_feedback(
            detected_tone=0, tone_accuracy=0.0,
            speech_rate=0.0, fluency=0.0,
            pitch_contour=[],
            word_prosody=[],
        )
        assert isinstance(fb, str) and len(fb) > 0
