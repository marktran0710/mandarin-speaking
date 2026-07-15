"""The trust invariant behind the per-word tone card: the two curves the UI
draws (user_curve / target_curve) must be the *same arrays* the shape score
compared — so "looks matching" and "scores high" can never disagree — and
estimate_word_prosody must actually ship them with each scored word."""
import numpy as np

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chinese_tones import (
    _shape_match_score,
    calculate_phrase_shape_accuracy,
    phrase_shape_curves,
)
from praat_analyzer import estimate_word_prosody


def _contour(values, duration=0.8):
    times = np.linspace(0.0, duration, len(values))
    return [(float(t), float(v)) for t, v in zip(times, values)]


RISING = _contour(np.linspace(180, 300, 40))
FLAT = _contour(np.full(40, 200.0))


class TestPhraseShapeCurves:
    def test_score_recomputed_from_returned_curves_matches_exactly(self):
        user, target = phrase_shape_curves(RISING, [2])
        recomputed = _shape_match_score(np.asarray(user), np.asarray(target))
        assert recomputed == calculate_phrase_shape_accuracy(RISING, [2])

    def test_curves_are_equal_length_and_normalized(self):
        user, target = phrase_shape_curves(RISING, [2])
        assert len(user) == len(target) > 0
        assert all(0.0 <= v <= 1.0 for v in user + target)

    def test_unscorable_inputs_return_empty(self):
        assert phrase_shape_curves([], [2]) == ([], [])
        assert phrase_shape_curves(RISING, []) == ([], [])

    def test_flat_attempt_no_longer_flattens_the_target(self):
        # The old raw-Hz overlay rescaled the target into the student's own
        # pitch band, so a flat attempt squashed the target flat too and the
        # chart lied "matching" while the score said otherwise. The
        # normalized target must keep its full swing regardless of how flat
        # the student's curve is.
        user, target = phrase_shape_curves(FLAT, [4])
        assert max(user) - min(user) < 0.05  # student: flat midline
        assert max(target) - min(target) > 0.2  # target: real falling swing

    def test_wrong_direction_scores_below_right_direction(self):
        rising_score = calculate_phrase_shape_accuracy(RISING, [2])
        falling_score = calculate_phrase_shape_accuracy(RISING, [4])
        assert rising_score > falling_score


class TestEstimateWordProsodyCurves:
    def test_segments_carry_matching_curves_and_shape_score(self):
        segments = estimate_word_prosody(RISING, "馬")
        assert len(segments) == 1
        seg = segments[0]
        assert len(seg["user_curve"]) == len(seg["target_curve"]) > 0
        assert "shape_accuracy" in seg

        # Rounding to 3 decimals for the payload may shift the recomputed
        # score marginally, but it must stay the same judgment.
        recomputed = _shape_match_score(
            np.asarray(seg["user_curve"]), np.asarray(seg["target_curve"])
        )
        assert abs(recomputed - seg["shape_accuracy"]) < 1.0

    def test_non_chinese_token_has_empty_curves(self):
        segments = estimate_word_prosody(RISING, "hello")
        assert segments[0]["user_curve"] == []
        assert segments[0]["target_curve"] == []
