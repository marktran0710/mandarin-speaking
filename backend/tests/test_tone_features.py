"""Unit tests for per-syllable tone features.

The properties tested here are the ones the model's ability to generalise
depends on: speaker normalisation (so it cannot learn voice identity as a
proxy for correctness), log scaling, and keeping "no evidence" distinct from
"measured zero".
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tone_scoring.alignment import SyllableSpan
from tone_scoring.features import (
    CONTOUR_POINTS,
    clean_pitch_contour,
    FEATURE_NAMES,
    declination_slope,
    features_to_vector,
    syllable_features,
    trim_consonant_onset,
    utterance_pitch_stats,
)


def ramp(start_hz, end_hz, t0=0.0, t1=0.4, n=20):
    return [
        (t0 + (t1 - t0) * i / (n - 1), start_hz + (end_hz - start_hz) * i / (n - 1))
        for i in range(n)
    ]


def log_ramp(start_hz, end_hz, t0=0.0, t1=2.0, n=200):
    """A ramp that is linear in log-F0, which is how declination actually
    behaves — and what a linear detrend can remove exactly. A ramp linear in
    Hz curves in log space and would leave a position-dependent residual."""
    ratio = end_hz / start_hz
    return [
        (t0 + (t1 - t0) * i / (n - 1), start_hz * ratio ** (i / (n - 1)))
        for i in range(n)
    ]


def features_for(contour, tone=2, span=None, **kwargs):
    mean, std = utterance_pitch_stats(contour)
    span = span or SyllableSpan(contour[0][0], contour[-1][0])
    return syllable_features(
        span, contour, tone, 0, 1, mean, std, **kwargs
    )


class TestUtterancePitchStats:
    def test_uses_log_pitch(self):
        mean, _ = utterance_pitch_stats([(0.0, 100.0), (0.1, 100.0)])
        assert mean == pytest.approx(math.log(100.0))

    def test_a_flat_utterance_does_not_divide_by_zero(self):
        _, deviation = utterance_pitch_stats([(0.0, 200.0), (0.1, 200.0)])
        assert deviation == 1.0


class TestSpeakerNormalisation:
    def test_two_voices_an_octave_apart_give_identical_features(self):
        """The model must not be able to learn voice identity as a proxy for
        correctness — that would collapse on unseen speakers, which is exactly
        what the speaker-disjoint folds are designed to expose."""
        low = features_for(ramp(100.0, 150.0))
        high = features_for(ramp(200.0, 300.0))
        for name in ("slope", "range", "start_z", "end_z", "curvature"):
            assert low[name] == pytest.approx(high[name], abs=1e-6), name

    def test_pitch_is_treated_logarithmically(self):
        """A 100->120 Hz rise and a 200->240 Hz rise are the same tonal
        movement; linear Hz would score the second as twice as large."""
        a = features_for(ramp(100.0, 120.0))
        b = features_for(ramp(200.0, 240.0))
        assert a["slope"] == pytest.approx(b["slope"], abs=1e-6)


class TestDeclinationDetrending:
    """Pitch drifts steadily downward across an utterance, which put a *level*
    tone 1 at -1.52 st of apparent fall on native speakers. Left in, the same
    correctly-produced tone measures differently depending only on where it
    sits in the sentence — pure nuisance variance.
    """

    def test_measures_the_downward_drift_of_an_utterance(self):
        falling = log_ramp(220.0, 110.0, 0.0, 2.0, n=100)
        slope, reference = declination_slope(falling)
        assert slope < 0
        assert reference == pytest.approx(1.0, abs=0.05)

    def test_a_level_utterance_has_no_drift(self):
        flat = [(i * 0.02, 180.0) for i in range(100)]
        slope, _ = declination_slope(flat)
        assert slope == pytest.approx(0.0, abs=1e-9)

    def test_returns_zero_when_there_is_too_little_data(self):
        assert declination_slope([(0.0, 100.0)]) == (0.0, 0.0)

    def test_a_level_tone_riding_on_declination_measures_as_level(self):
        """The whole point: remove the sentence-level drift and a flat tone
        reads flat, wherever in the utterance it occurs."""
        drifting = log_ramp(220.0, 110.0, 0.0, 2.0, n=200)
        slope, reference = declination_slope(drifting)
        span = SyllableSpan(1.2, 1.5)
        mean, std = utterance_pitch_stats(drifting, slope, reference)

        contaminated = syllable_features(span, drifting, 1, 3, 6, *utterance_pitch_stats(drifting))
        corrected = syllable_features(
            span, drifting, 1, 3, 6, mean, std,
            declination=slope, time_reference=reference,
        )
        assert contaminated["st_slope"] < -1.0        # apparent fall from drift
        assert corrected["st_slope"] == pytest.approx(0.0, abs=0.2)

    def test_the_same_tone_measures_alike_early_and_late(self):
        """Nuisance variance removed: position must stop changing the reading."""
        drifting = log_ramp(220.0, 110.0, 0.0, 2.0, n=200)
        slope, reference = declination_slope(drifting)
        mean, std = utterance_pitch_stats(drifting, slope, reference)
        early = syllable_features(
            SyllableSpan(0.2, 0.5), drifting, 1, 0, 6, mean, std,
            declination=slope, time_reference=reference,
        )
        late = syllable_features(
            SyllableSpan(1.5, 1.8), drifting, 1, 5, 6, mean, std,
            declination=slope, time_reference=reference,
        )
        assert early["st_slope"] == pytest.approx(late["st_slope"], abs=0.2)

    def test_detrending_preserves_a_real_rise(self):
        """Removing drift must not remove the tone itself."""
        drifting = log_ramp(220.0, 110.0, 0.0, 2.0, n=200)
        slope, reference = declination_slope(drifting)
        mean, std = utterance_pitch_stats(drifting, slope, reference)
        # A syllable that rises against the falling trend stays a rise.
        rising = drifting[:120] + log_ramp(140.0, 210.0, 1.2, 1.5, n=30) + drifting[150:]
        rising = sorted(rising)
        features = syllable_features(
            SyllableSpan(1.2, 1.5), rising, 2, 3, 6, mean, std,
            declination=slope, time_reference=reference,
        )
        assert features["st_slope"] > 1.0


class TestAbsoluteMagnitude:
    """Semitone features must preserve how much pitch actually moved.

    The z-scored features are scale-free by construction, so they cannot tell a
    full tonal excursion from a nearly flat one — but insufficient excursion is
    the classic L2 tone error, and it is exactly what a teacher marks wrong.
    """

    def test_a_flat_speaker_is_distinguishable_from_a_full_range_one(self):
        flat = features_for(ramp(150.0, 155.0))
        full = features_for(ramp(120.0, 240.0))
        assert flat["st_range"] < 1.0
        assert full["st_range"] > 10.0
        # The z-scored range cannot make this distinction, which is the whole
        # reason the semitone features exist.
        assert flat["range"] == pytest.approx(full["range"], abs=0.2)

    def test_semitones_are_voice_independent(self):
        """An octave is 12 semitones for any voice, so the same tonal movement
        gives the same value regardless of the speaker's absolute pitch.

        A long ramp is used so the 30 ms consonant-onset trim removes a
        negligible slice; on a short syllable the trim legitimately shortens
        the measured range."""
        low = features_for(ramp(100.0, 200.0, 0.0, 2.0, n=100))
        high = features_for(ramp(200.0, 400.0, 0.0, 2.0, n=100))
        assert low["st_range"] == pytest.approx(high["st_range"], abs=1e-6)
        assert low["st_range"] == pytest.approx(12.0, abs=0.5)

    def test_slope_sign_follows_direction(self):
        assert features_for(ramp(100.0, 200.0))["st_slope"] > 0
        assert features_for(ramp(200.0, 100.0))["st_slope"] < 0

    def test_range_ratio_relates_the_syllable_to_the_utterance(self):
        contour = ramp(100.0, 200.0, 0.0, 0.8, n=40)
        mean, std = utterance_pitch_stats(contour)
        half = syllable_features(
            SyllableSpan(0.0, 0.4), contour, 2, 0, 2, mean, std
        )
        assert 0.0 < half["st_range_ratio"] < 1.0
        assert half["st_utterance_range"] == pytest.approx(12.0, abs=0.5)


class TestPitchOutlierRejection:
    """Trackers lock onto a harmonic and report F0 an exact octave off, and
    creaky voice produces isolated wild values. The larynx cannot move F0
    several semitones between adjacent 10 ms frames, so such frames are not
    speech and no downstream step can undo them.
    """

    def test_removes_an_octave_tracking_error(self):
        frames = [(i * 0.01, 200.0) for i in range(11)]
        frames[5] = (0.05, 400.0)          # classic octave lock
        kept = clean_pitch_contour(frames)
        assert len(kept) == 10
        assert all(freq == pytest.approx(200.0) for _, freq in kept)

    def test_removes_a_creak_dropout(self):
        frames = [(i * 0.01, 200.0) for i in range(11)]
        frames[6] = (0.06, 70.0)
        assert len(clean_pitch_contour(frames)) == 10

    def test_keeps_a_genuine_tone_contour_intact(self):
        """A real rise moves far overall but only slightly between adjacent
        frames, so nothing should be dropped."""
        frames = [(i * 0.01, 150.0 * (1.5 ** (i / 20))) for i in range(21)]
        assert len(clean_pitch_contour(frames)) == 21

    def test_drops_rather_than_interpolates(self):
        """A fabricated frame is indistinguishable from a measured one
        downstream; this codebase has already been burned by a placeholder
        that later read as a real measurement."""
        frames = [(i * 0.01, 200.0) for i in range(11)]
        frames[5] = (0.05, 400.0)
        kept = clean_pitch_contour(frames)
        assert all(abs(t - 0.05) > 1e-9 for t, _ in kept)

    def test_leaves_a_very_short_contour_alone(self):
        frames = [(0.0, 200.0), (0.01, 400.0)]
        assert clean_pitch_contour(frames) == frames


class TestConsonantOnsetTrim:
    """A syllable-initial consonant perturbs F0 at vowel onset -- voiceless
    obstruents raise it, voiced ones lower it -- decaying over roughly the
    first 30-50 ms. Those frames carry consonant identity, not tone.
    """

    def test_drops_the_perturbed_opening_frames(self):
        frames = [(i * 0.01, 100.0) for i in range(20)]
        kept = trim_consonant_onset(frames)
        assert kept[0][0] == pytest.approx(0.03, abs=1e-9)
        assert len(kept) == 17

    def test_trims_by_absolute_time_not_by_a_fraction(self):
        """The perturbation is a physiological property of the consonant
        release, so it does not scale with syllable length: a long syllable
        must lose the same 30 ms as a short one, not a larger slice."""
        short = trim_consonant_onset([(i * 0.01, 100.0) for i in range(12)])
        long = trim_consonant_onset([(i * 0.01, 100.0) for i in range(60)])
        assert short[0][0] == pytest.approx(long[0][0], abs=1e-9)

    def test_a_short_syllable_keeps_all_its_frames(self):
        """Trimming a syllable down to two or three points trades one noise
        source for a worse one."""
        frames = [(i * 0.01, 100.0) for i in range(4)]
        assert trim_consonant_onset(frames) == frames

    def test_keeps_everything_when_trimming_would_leave_too_few(self):
        frames = [(i * 0.01, 100.0) for i in range(6)]
        kept = trim_consonant_onset(frames, window=0.05)
        assert kept == frames


class TestShape:
    def test_a_rise_and_a_fall_have_opposite_slope(self):
        assert features_for(ramp(100.0, 200.0))["slope"] > 0
        assert features_for(ramp(200.0, 100.0))["slope"] < 0

    def test_a_dip_is_distinguished_from_a_plain_fall(self):
        """Tone 3 dips and recovers; tone 4 falls throughout. They can share a
        start and end pitch, so endpoints alone cannot separate them."""
        dip = ramp(200.0, 120.0, 0.0, 0.2) + ramp(120.0, 200.0, 0.2, 0.4)
        fall = ramp(200.0, 120.0, 0.0, 0.4)
        assert features_for(dip)["curvature"] > features_for(fall)["curvature"]
        assert features_for(dip)["rise_after_dip"] > features_for(fall)["rise_after_dip"]

    def test_contour_is_resampled_to_a_fixed_length_preserving_shape(self):
        """Length must be fixed so every syllable yields the same column count,
        and the shape must survive resampling. The absolute z-values differ
        between sampling densities because the utterance normalisation stats
        are themselves computed from those samples — that is expected, so the
        invariant tested is monotonicity, not equality."""
        for count in (5, 40):
            features = features_for(ramp(100.0, 200.0, n=count))
            contour = [features[f"contour_{i}"] for i in range(CONTOUR_POINTS)]
            assert len(contour) == CONTOUR_POINTS
            assert contour == sorted(contour), f"rising ramp at n={count}"

        falling = features_for(ramp(200.0, 100.0, n=20))
        contour = [falling[f"contour_{i}"] for i in range(CONTOUR_POINTS)]
        assert contour == sorted(contour, reverse=True)


class TestUnfeaturizable:
    def test_returns_none_rather_than_zeros_when_there_is_too_little_pitch(self):
        """Zeros would be indistinguishable from a real measurement — the exact
        confusion that made the old scorer count unjudged syllables as
        failures."""
        contour = [(0.0, 100.0), (0.1, 110.0)]
        assert features_for(contour) is None

    def test_returns_none_when_the_span_contains_no_voiced_frames(self):
        contour = ramp(100.0, 200.0)
        span = SyllableSpan(5.0, 6.0)
        assert features_for(contour, span=span) is None


class TestContext:
    def test_neighbour_pitch_is_carried_for_coarticulation(self):
        contour = ramp(100.0, 200.0, 0.0, 0.8, n=40)
        mean, std = utterance_pitch_stats(contour)
        first, second = SyllableSpan(0.0, 0.4), SyllableSpan(0.4, 0.8)
        with_prev = syllable_features(
            second, contour, 2, 1, 2, mean, std, previous_span=first
        )
        without = syllable_features(second, contour, 2, 1, 2, mean, std)
        assert with_prev["prev_end_z"] != 0.0
        assert without["prev_end_z"] == 0.0

    def test_final_syllable_is_flagged(self):
        contour = ramp(100.0, 200.0)
        mean, std = utterance_pitch_stats(contour)
        span = SyllableSpan(contour[0][0], contour[-1][0])
        assert syllable_features(span, contour, 1, 1, 2, mean, std)["is_final"] == 1.0
        assert syllable_features(span, contour, 1, 0, 2, mean, std)["is_final"] == 0.0


class TestVector:
    def test_expected_tone_is_one_hot(self):
        features = features_for(ramp(100.0, 200.0), tone=3)
        assert features["expected_tone_3"] == 1.0
        assert features["expected_tone_1"] == 0.0

    def test_vector_follows_the_pinned_feature_order(self):
        """Column order is pinned so a stored model can never be fed columns in
        a different order than it was trained on — a silent failure that would
        still produce plausible-looking scores."""
        features = features_for(ramp(100.0, 200.0))
        vector = features_to_vector(features)
        assert len(vector) == len(FEATURE_NAMES)
        assert vector[FEATURE_NAMES.index("slope")] == pytest.approx(features["slope"])

    def test_missing_features_default_to_zero_without_raising(self):
        assert features_to_vector({}) == [0.0] * len(FEATURE_NAMES)
