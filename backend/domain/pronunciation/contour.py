"""Pitch-contour maths shared by reference and student features.

Everything here works in semitones relative to the speaker's own median, never
in Hz, so a low voice and a high voice producing the same tone compare as equal.
``compare_word_contours`` is a Python port of the frontend's v2 model
similarity (frontend/src/entities/speech/modelSimilarity.ts): Pearson shape
inside each word times a one-sided range factor, best over small window shifts.
One deliberate extension: a level reference word is scored on how level the
student stayed, where the frontend skips it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

from domain.pronunciation.policy import ContourSimilarityParams, DirectionParams

Point = tuple[float, float]  # (time in ms, semitones)

_OCTAVE = 12.0
#: Price of starting or ending an octave-shifted block (see frontend pitchCleaning.ts).
OCTAVE_SWITCH_PENALTY = 8.0
_OFFSETS = (0.0, -_OCTAVE, _OCTAVE)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def hz_to_relative_semitones(hz: Sequence[float]) -> list[float]:
    """Semitones against the median of the same speaker's own voiced pitch."""
    if not hz:
        return []
    median_hz = _median(hz)
    return [12.0 * math.log2(value / median_hz) for value in hz]


def fold_octave_blocks(values: Sequence[float]) -> list[float]:
    """Remove half/double-frequency tracker errors of any length.

    Each point may move by 0 or +-12 semitones; a Viterbi pass keeps the total
    frame-to-frame jump plus a switch penalty minimal, so a held octave error is
    folded back while a real 7-9 semitone syllable reset is left alone.
    """
    count = len(values)
    if count < 3:
        return list(values)

    cost = [[0.0] * 3 for _ in range(count)]
    came_from = [[0] * 3 for _ in range(count)]
    for k, offset in enumerate(_OFFSETS):
        cost[0][k] = 0.0 if offset == 0 else OCTAVE_SWITCH_PENALTY
    for i in range(1, count):
        for k in range(3):
            best, best_from = math.inf, 0
            for j in range(3):  # "no shift" first, so ties keep the original value
                jump = abs(values[i] + _OFFSETS[k] - (values[i - 1] + _OFFSETS[j]))
                total = cost[i - 1][j] + jump + (0.0 if j == k else OCTAVE_SWITCH_PENALTY)
                if total < best - 1e-9:
                    best, best_from = total, j
            cost[i][k] = best
            came_from[i][k] = best_from

    state = 0
    for k in (1, 2):
        if cost[count - 1][k] < cost[count - 1][state] - 1e-9:
            state = k
    folded = [0.0] * count
    for i in range(count - 1, -1, -1):
        folded[i] = values[i] + _OFFSETS[state]
        state = came_from[i][state]
    return folded


def _percentile(ordered: Sequence[float], fraction: float) -> float:
    position = fraction * (len(ordered) - 1)
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def robust_span(values: Sequence[float]) -> float:
    """10th-90th percentile spread: one stray sample cannot inflate it."""
    if len(values) < 2:
        return 0.0
    ordered = sorted(values)
    return _percentile(ordered, 0.9) - _percentile(ordered, 0.1)


def classify_direction(
    values: Sequence[float], params: DirectionParams = DirectionParams()
) -> str:
    """rise | fall | dip | flat | other, or ``unvoiced`` when there is too little pitch."""
    count = len(values)
    if count < params.min_points:
        return "unvoiced"
    span = robust_span(values)
    if span < params.flat_range:
        return "flat"
    edge = max(1, count // 5)
    start = _mean(values[:edge])
    end = _mean(values[-edge:])
    middle = values[count // 3 : max(count // 3 + 1, 2 * count // 3)]
    dip = (start + end) / 2.0 - _mean(middle)
    if dip >= max(params.dip_min, params.dip_fraction * span):
        return "dip"
    slope_bar = max(params.slope_min, params.slope_fraction * span)
    if end - start >= slope_bar:
        return "rise"
    if start - end >= slope_bar:
        return "fall"
    return "other"


def _interpolate(points: Sequence[Point], time: float, max_gap: float) -> Optional[float]:
    for i in range(1, len(points)):
        t0, v0 = points[i - 1]
        t1, v1 = points[i]
        if t0 <= time <= t1:
            if t1 - t0 > max_gap:
                return None
            return v0 if t1 == t0 else v0 + (time - t0) / (t1 - t0) * (v1 - v0)
    return None


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    mean_x, mean_y = _mean(xs), _mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    # A level contour has no shape to correlate: treat it as no similarity.
    if var_x < 1e-9 or var_y < 1e-9:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


@dataclass(frozen=True)
class ContourSimilarity:
    r: float
    shape: float
    range: float
    score: float
    flat_reference: bool = False


def compare_word_contours(
    student: Sequence[Point],
    student_span: tuple[float, float],
    reference: Sequence[Point],
    reference_span: tuple[float, float],
    params: ContourSimilarityParams = ContourSimilarityParams(),
) -> Optional[ContourSimilarity]:
    """Shape x size similarity of one word, 0..1, or None when it cannot be judged.

    Each contour is read on its own span scaled to 0..1, so neither speaking
    speed nor absolute pitch matters.
    """
    ref_start, ref_end = reference_span
    st_start, st_end = student_span
    ref_len, st_len = ref_end - ref_start, st_end - st_start
    if ref_len <= 0 or st_len <= 0:
        return None

    samples = params.samples_per_word

    def paired_samples(shift: float) -> tuple[list[float], list[float]]:
        student_values: list[float] = []
        reference_values: list[float] = []
        for i in range(samples):
            fraction = (i + 0.5) / samples
            s = _interpolate(student, st_start + (fraction + shift) * st_len, params.max_voiced_gap_ms)
            r = _interpolate(reference, ref_start + fraction * ref_len, params.max_voiced_gap_ms)
            if s is not None and r is not None:
                student_values.append(s)
                reference_values.append(r)
        return student_values, reference_values

    unshifted_student, unshifted_reference = paired_samples(0.0)
    if (
        len(unshifted_student) >= samples / 2
        and max(unshifted_reference) - min(unshifted_reference) < params.flat_reference_range
    ):
        # Judged on the unshifted window only: picking the best shift would let
        # a narrower window hide real movement.
        return _level_reference_similarity(unshifted_student, params)

    best: Optional[ContourSimilarity] = None
    for shift in params.window_shifts:
        student_values, reference_values = paired_samples(shift)
        if len(student_values) < samples / 2:
            continue

        r = _pearson(student_values, reference_values)
        shape = _clamp01((r - params.r_floor) / (params.r_full - params.r_floor))
        reference_size = max(robust_span(reference_values), params.min_reference_span)
        ratio = robust_span(student_values) / reference_size
        size = _clamp01((ratio - params.rho_zero) / (params.rho_full - params.rho_zero))
        candidate = ContourSimilarity(r=r, shape=shape, range=size, score=shape * size)
        if best is None or candidate.score > best.score:
            best = candidate
    return best


def _level_reference_similarity(
    student_values: Sequence[float], params: ContourSimilarityParams
) -> ContourSimilarity:
    span = robust_span(student_values)
    credit = _clamp01(
        (params.flat_zero_credit_range - span)
        / (params.flat_zero_credit_range - params.flat_full_credit_range)
    )
    return ContourSimilarity(r=0.0, shape=credit, range=1.0, score=credit, flat_reference=True)
