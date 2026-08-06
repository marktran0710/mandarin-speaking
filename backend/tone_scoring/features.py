"""Per-syllable acoustic features for the learned tone scorer.

Design constraints that matter here:

*Speaker normalisation.* Mandarin tone is carried by pitch movement relative to
a speaker's own range, not by absolute Hz. A 180 Hz syllable is high for one
voice and low for another. Every pitch feature is therefore expressed in
z-scored log-F0 within the utterance, so the model cannot learn "this speaker
is female" as a proxy for "this tone is correct" -- which would collapse the
moment it met a new speaker, exactly what the speaker-disjoint folds exist to
catch.

*Log, not linear.* Pitch is perceived roughly logarithmically, so a rise from
100 to 120 Hz and one from 200 to 240 Hz are the same tonal movement. Linear Hz
would make the second look twice as large.

*Shape, not just endpoints.* A tone 3 dips and recovers; a tone 4 falls
throughout. Both can share a start and end pitch, so the contour is resampled
to fixed points and handed over whole rather than reduced to a slope.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# Points the syllable contour is resampled to. Enough to distinguish a dip from
# a monotonic fall, few enough not to model frame-level noise on short syllables.
CONTOUR_POINTS = 8
# Fewer voiced frames than this cannot express a tone shape; the syllable is
# reported unfeaturizable rather than given fabricated values.
MIN_FRAMES = 4
# Semitones per unit of natural log: 12 / ln(2).
SEMITONES_PER_LOG = 12.0 / math.log(2.0)

FEATURE_NAMES: List[str] = (
    [f"contour_{i}" for i in range(CONTOUR_POINTS)]
    + [
        "slope",
        "curvature",
        "range",
        "mean_pitch_z",
        "start_z",
        "end_z",
        "min_z",
        "max_z",
        "dip_depth",
        "rise_after_dip",
        "st_range",
        "st_slope",
        "st_dip_depth",
        "st_rise_after_dip",
        "st_utterance_range",
        "st_range_ratio",
        "duration",
        "duration_ratio",
        "frame_count",
        "voiced_density",
        "position_ratio",
        "is_final",
        "prev_end_z",
        "next_start_z",
        "intensity_mean_z",
        "intensity_slope",
    ]
    + [f"expected_tone_{tone}" for tone in (1, 2, 3, 4)]
)


def declination_slope(pitch_contour: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """Least-squares drift of log-F0 across the utterance, and its time origin.

    Pitch drifts steadily downward over an utterance (declination). Measured on
    native speakers, that drift put a *level* tone 1 at -1.52 semitones of
    apparent fall in non-final position and -0.49 in final position -- the tone
    had not changed, only where it sat in the sentence.

    Left in, this is pure nuisance variance: the same correctly-produced tone 2
    measures -1.08 early in an utterance and +0.32 at the end, a 1.4 semitone
    swing that reflects position rather than pronunciation. Removing the trend
    does not change the gap between two tones (a common offset cancels), but it
    strips a large source of within-tone variance that a classifier would
    otherwise have to treat as noise.

    Returns (slope in log-units per second, reference time). Slope is 0.0 when
    there is too little data or no time spread to fit.
    """
    points = [
        (float(time), math.log(float(freq)))
        for time, freq in pitch_contour
        if float(freq) > 0
    ]
    if len(points) < 3:
        return 0.0, 0.0
    times = np.asarray([t for t, _ in points], dtype=float)
    logs = np.asarray([v for _, v in points], dtype=float)
    time_reference = float(times.mean())
    centered = times - time_reference
    denominator = float(np.sum(centered**2))
    if denominator <= 1e-9:
        return 0.0, time_reference
    slope = float(np.sum(centered * (logs - logs.mean())) / denominator)
    return slope, time_reference


def _detrended_logs(
    frames: Sequence[Tuple[float, float]], declination: float, time_reference: float
) -> np.ndarray:
    """log-F0 with the utterance's declination removed.

    Only the time-varying part is subtracted, so the speaker's overall pitch
    level is preserved and the features stay interpretable.
    """
    times = np.asarray([t for t, _ in frames], dtype=float)
    logs = np.log(np.asarray([f for _, f in frames], dtype=float))
    return logs - declination * (times - time_reference)


def regression_slope(times: Sequence[float], values: Sequence[float]) -> float:
    """Least-squares slope of ``values`` against ``times``, per unit time.

    This replaces a mean-of-last-quarter minus mean-of-first-quarter estimate.
    That endpoint difference throws away the middle of the contour and rests on
    two small samples, so its variance is far higher than a line fitted through
    every frame -- and variance, not the mean, is what makes the tone
    measurement unusable (correctly-produced T1 and T2 separate by 1.04
    semitones against a pooled spread of 5.57).

    This is a property of the estimator, not a tuning choice: averaging n
    points beats averaging n/4 of them regardless of corpus, so it should
    transfer to any speaker rather than fit this one.
    """
    if len(times) < 2:
        return 0.0
    time_array = np.asarray(times, dtype=float)
    value_array = np.asarray(values, dtype=float)
    centered = time_array - time_array.mean()
    denominator = float(np.sum(centered**2))
    if denominator <= 1e-12:
        return 0.0
    return float(np.sum(centered * (value_array - value_array.mean())) / denominator)


def _resample(values: Sequence[float], points: int) -> List[float]:
    """Resample a contour to a fixed number of points by linear interpolation."""
    if len(values) == 1:
        return [float(values[0])] * points
    source = np.linspace(0.0, 1.0, num=len(values))
    target = np.linspace(0.0, 1.0, num=points)
    return [float(v) for v in np.interp(target, source, values)]


def utterance_pitch_stats(
    pitch_contour: Sequence[Tuple[float, float]],
    declination: float = 0.0,
    time_reference: float = 0.0,
) -> Tuple[float, float]:
    """Mean and standard deviation of log-F0 across the whole utterance.

    The normalisation reference is the utterance rather than a global constant,
    so the features describe movement within this speaker's range on this
    recording. When a declination slope is supplied the statistics are taken
    over the detrended signal, so they match the values the syllable features
    are z-scored against.
    """
    frames = [
        (float(time), float(freq)) for time, freq in pitch_contour if float(freq) > 0
    ]
    if not frames:
        return 0.0, 1.0
    values = _detrended_logs(frames, declination, time_reference)
    mean = float(np.mean(values))
    deviation = float(np.std(values))
    # A flat utterance would otherwise divide by zero and produce infinities.
    return mean, deviation if deviation > 1e-6 else 1.0


def syllable_features(
    span,
    pitch_contour: Sequence[Tuple[float, float]],
    expected_tone: int,
    index: int,
    total: int,
    pitch_mean: float,
    pitch_std: float,
    intensity: Optional[Sequence[Tuple[float, float]]] = None,
    previous_span=None,
    next_span=None,
    declination: float = 0.0,
    time_reference: float = 0.0,
) -> Optional[Dict[str, float]]:
    """Features for one syllable, or None when it cannot be featurized.

    Returning None rather than zeros keeps "no evidence" distinct from
    "measured as zero" -- conflating the two is what made the previous scorer
    count 19% of syllables as failures it had never actually judged.
    """
    frames = [(t, f) for t, f in span.frames(pitch_contour) if f > 0]
    if len(frames) < MIN_FRAMES:
        return None

    detrended = _detrended_logs(frames, declination, time_reference)
    z_values = [(value - pitch_mean) / pitch_std for value in detrended]
    if len(z_values) < MIN_FRAMES:
        return None

    contour = _resample(z_values, CONTOUR_POINTS)
    array = np.asarray(z_values, dtype=float)
    quarter = max(1, len(array) // 4)
    start_z = float(np.mean(array[:quarter]))
    end_z = float(np.mean(array[-quarter:]))
    middle = array[quarter : len(array) - quarter] if len(array) > 2 * quarter else array

    features: Dict[str, float] = {
        f"contour_{i}": value for i, value in enumerate(contour)
    }
    # Slope over the whole syllable, fitted rather than differenced. Expressed
    # as total change across the syllable so the units match the previous
    # endpoint estimate and downstream thresholds keep their meaning.
    frame_times = [t for t, _ in frames]
    span_seconds = max(frame_times[-1] - frame_times[0], 1e-6)
    features["slope"] = regression_slope(frame_times, z_values)
    # Positive curvature = dips in the middle (tone 3); negative = arches.
    features["curvature"] = float((start_z + end_z) / 2.0 - np.mean(middle))
    features["range"] = float(array.max() - array.min())
    features["mean_pitch_z"] = float(array.mean())
    features["start_z"] = start_z
    features["end_z"] = end_z
    features["min_z"] = float(array.min())
    features["max_z"] = float(array.max())
    # Depth of the lowest point below the start, and how far it recovers after:
    # together these separate a true tone-3 dip-and-rise from a plain fall.
    low_index = int(np.argmin(array))
    features["dip_depth"] = start_z - float(array[low_index])
    features["rise_after_dip"] = (
        float(array[low_index:].max() - array[low_index])
        if low_index < len(array) - 1
        else 0.0
    )

    # Absolute pitch movement, in semitones. Every feature above is z-scored
    # within the utterance, which is right for *shape* but destroys *magnitude*:
    # a learner who barely moves their pitch has that small variation stretched
    # to unit variance and becomes indistinguishable from a speaker with full
    # tonal range. Insufficient excursion is the classic L2 tone error, so it
    # has to survive normalisation. Semitones are log ratios, so they stay
    # comparable across voices while preserving how much pitch actually moved.
    logs = detrended
    log_quarter = max(1, len(logs) // 4)
    log_start = float(np.mean(logs[:log_quarter]))
    log_end = float(np.mean(logs[-log_quarter:]))
    log_min_index = int(np.argmin(logs))
    features["st_range"] = float(logs.max() - logs.min()) * SEMITONES_PER_LOG
    features["st_slope"] = regression_slope(frame_times, logs) * SEMITONES_PER_LOG
    features["st_dip_depth"] = (log_start - float(logs[log_min_index])) * SEMITONES_PER_LOG
    features["st_rise_after_dip"] = (
        float(logs[log_min_index:].max() - logs[log_min_index]) * SEMITONES_PER_LOG
        if log_min_index < len(logs) - 1
        else 0.0
    )
    utterance_logs = _detrended_logs(
        [(float(t), float(f)) for t, f in pitch_contour if f > 0],
        declination,
        time_reference,
    )
    utterance_range = (
        float(utterance_logs.max() - utterance_logs.min()) * SEMITONES_PER_LOG
        if len(utterance_logs)
        else 0.0
    )
    features["st_utterance_range"] = utterance_range
    features["st_range_ratio"] = (
        features["st_range"] / utterance_range if utterance_range > 1e-6 else 0.0
    )

    duration = span.duration
    total_duration = max(
        float(pitch_contour[-1][0]) - float(pitch_contour[0][0]), 1e-6
    )
    features["duration"] = duration
    features["duration_ratio"] = duration / (total_duration / max(total, 1))
    features["frame_count"] = float(len(frames))
    features["voiced_density"] = len(frames) / max(duration, 1e-6)
    features["position_ratio"] = index / max(total - 1, 1)
    # Utterance-final syllables are systematically lengthened and lowered by
    # declination, so the model is told where it is rather than having to
    # infer it.
    features["is_final"] = 1.0 if index == total - 1 else 0.0

    features["prev_end_z"] = _edge_z(
        previous_span, pitch_contour, pitch_mean, pitch_std,
        declination, time_reference, last=True,
    )
    features["next_start_z"] = _edge_z(
        next_span, pitch_contour, pitch_mean, pitch_std,
        declination, time_reference, last=False,
    )

    features["intensity_mean_z"], features["intensity_slope"] = _intensity_features(
        span, intensity
    )

    for tone in (1, 2, 3, 4):
        features[f"expected_tone_{tone}"] = 1.0 if expected_tone == tone else 0.0
    return features


def _edge_z(
    span, pitch_contour, mean, deviation, declination=0.0, time_reference=0.0, *, last: bool
) -> float:
    """Neighbouring syllable's adjacent pitch, for coarticulation context.

    A syllable's realisation depends on what precedes it: a tone 2 after a high
    tone starts higher than the same tone 2 after a low one. Without this the
    model has to treat that variation as noise.
    """
    if span is None:
        return 0.0
    frames = [(t, f) for t, f in span.frames(pitch_contour) if f > 0]
    if not frames:
        return 0.0
    values = [
        (value - mean) / deviation
        for value in _detrended_logs(frames, declination, time_reference)
    ]
    if not values:
        return 0.0
    return values[-1] if last else values[0]


def _intensity_features(span, intensity) -> Tuple[float, float]:
    if not intensity:
        return 0.0, 0.0
    values = [
        float(value)
        for time, value in intensity
        if span.start <= float(time) <= span.end
    ]
    if len(values) < 2:
        return 0.0, 0.0
    array = np.asarray(values, dtype=float)
    overall = np.asarray([float(v) for _, v in intensity], dtype=float)
    deviation = float(overall.std()) or 1.0
    return (
        float((array.mean() - overall.mean()) / deviation),
        float((array[-1] - array[0]) / deviation),
    )


def features_to_vector(features: Dict[str, float]) -> List[float]:
    """Flatten to the fixed FEATURE_NAMES order.

    Order is pinned by FEATURE_NAMES so a stored model can never be fed columns
    in a different order than it was trained on -- a silent failure that would
    still produce plausible-looking scores.
    """
    return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]
