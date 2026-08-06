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


def _resample(values: Sequence[float], points: int) -> List[float]:
    """Resample a contour to a fixed number of points by linear interpolation."""
    if len(values) == 1:
        return [float(values[0])] * points
    source = np.linspace(0.0, 1.0, num=len(values))
    target = np.linspace(0.0, 1.0, num=points)
    return [float(v) for v in np.interp(target, source, values)]


def utterance_pitch_stats(pitch_contour: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    """Mean and standard deviation of log-F0 across the whole utterance.

    The normalisation reference is the utterance rather than a global constant,
    so the features describe movement within this speaker's range on this
    recording.
    """
    values = [math.log(float(freq)) for _, freq in pitch_contour if float(freq) > 0]
    if not values:
        return 0.0, 1.0
    mean = float(np.mean(values))
    deviation = float(np.std(values))
    # A flat utterance would otherwise divide by zero and produce infinities.
    return mean, deviation if deviation > 1e-6 else 1.0


def _z(values: Sequence[float], mean: float, deviation: float) -> List[float]:
    return [(math.log(v) - mean) / deviation for v in values if v > 0]


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
) -> Optional[Dict[str, float]]:
    """Features for one syllable, or None when it cannot be featurized.

    Returning None rather than zeros keeps "no evidence" distinct from
    "measured as zero" -- conflating the two is what made the previous scorer
    count 19% of syllables as failures it had never actually judged.
    """
    frames = [(t, f) for t, f in span.frames(pitch_contour) if f > 0]
    if len(frames) < MIN_FRAMES:
        return None

    z_values = _z([f for _, f in frames], pitch_mean, pitch_std)
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
    features["slope"] = end_z - start_z
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

    features["prev_end_z"] = _edge_z(previous_span, pitch_contour, pitch_mean, pitch_std, last=True)
    features["next_start_z"] = _edge_z(next_span, pitch_contour, pitch_mean, pitch_std, last=False)

    features["intensity_mean_z"], features["intensity_slope"] = _intensity_features(
        span, intensity
    )

    for tone in (1, 2, 3, 4):
        features[f"expected_tone_{tone}"] = 1.0 if expected_tone == tone else 0.0
    return features


def _edge_z(span, pitch_contour, mean, deviation, *, last: bool) -> float:
    """Neighbouring syllable's adjacent pitch, for coarticulation context.

    A syllable's realisation depends on what precedes it: a tone 2 after a high
    tone starts higher than the same tone 2 after a low one. Without this the
    model has to treat that variation as noise.
    """
    if span is None:
        return 0.0
    frames = [f for _, f in span.frames(pitch_contour) if f > 0]
    if not frames:
        return 0.0
    values = _z(frames, mean, deviation)
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
