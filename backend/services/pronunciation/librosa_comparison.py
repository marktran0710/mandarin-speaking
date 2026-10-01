"""Reference-relative teacher/student audio comparison with librosa.

This module is deliberately an evidence adapter, not a pronunciation model.
It aligns MFCC sequences with DTW, compares speaker-normalized pYIN contours,
and reports coarse duration/pause similarity. The raw contours are retained
for admin/debug visualization; the feedback model receives only scalar values.

The dependency is optional because the production image does not install the
local ASR extras. A missing package or an unusable recording returns a stable
unavailable result instead of changing the Praat/Wav2Vec2 evaluation path.
"""

from __future__ import annotations

import math
import os
from typing import Any

import numpy as np


SAMPLE_RATE = 16_000
HOP_LENGTH = 160
N_FFT = 1_024
N_MFCC = 20
N_MELS = 40
FMIN_HZ = 65.0
FMAX_HZ = 500.0
VOICED_PROBABILITY_MINIMUM = 0.35
SILENCE_TOP_DB = 35
MFCC_DISTANCE_SCALE = 5.0
PITCH_DISTANCE_SCALE_SEMITONES = 4.0
MAX_DURATION_SECONDS = 60
MAX_DTW_FRAMES = 2_000


def _enabled() -> bool:
    value = os.environ.get("PRONUNCIATION_LIBROSA_COMPARISON_ENABLED", "true")
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _float_setting(name: str, default: float, *, minimum: float = 0.0, maximum: float = math.inf) -> float:
    """Read a tunable evidence parameter without allowing invalid values."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) and minimum <= value <= maximum else default


def _int_setting(name: str, default: int, *, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _parameters() -> dict[str, float | int | str]:
    """Persist the effective extraction settings and similarity transforms.

    The exponential transforms are configurable engineering conveniences,
    not calibrated probabilities or pronunciation grades.
    """
    return {
        "version": "librosa-reference-comparison-v1",
        "sample_rate": SAMPLE_RATE, "hop_length": HOP_LENGTH,
        "n_fft": N_FFT, "n_mfcc": N_MFCC, "n_mels": N_MELS,
        "fmin_hz": _float_setting("PRONUNCIATION_LIBROSA_FMIN_HZ", FMIN_HZ, minimum=1.0, maximum=SAMPLE_RATE / 2 - 1),
        "fmax_hz": _float_setting("PRONUNCIATION_LIBROSA_FMAX_HZ", FMAX_HZ, minimum=1.0, maximum=SAMPLE_RATE / 2 - 1),
        "silence_top_db": _int_setting("PRONUNCIATION_LIBROSA_SILENCE_TOP_DB", SILENCE_TOP_DB),
        "voiced_probability_minimum": _float_setting(
            "PRONUNCIATION_LIBROSA_VOICED_PROBABILITY_MINIMUM", VOICED_PROBABILITY_MINIMUM, maximum=1.0,
        ),
        "mfcc_distance_scale": _float_setting(
            "PRONUNCIATION_LIBROSA_MFCC_DISTANCE_SCALE", MFCC_DISTANCE_SCALE, minimum=1e-6,
        ),
        "pitch_distance_scale_semitones": _float_setting(
            "PRONUNCIATION_LIBROSA_PITCH_DISTANCE_SCALE_SEMITONES", PITCH_DISTANCE_SCALE_SEMITONES, minimum=1e-6,
        ),
        "max_duration_seconds": _int_setting(
            "PRONUNCIATION_LIBROSA_MAX_DURATION_SECONDS", MAX_DURATION_SECONDS, minimum=1,
        ),
        "max_dtw_frames": _int_setting(
            "PRONUNCIATION_LIBROSA_MAX_DTW_FRAMES", MAX_DTW_FRAMES, minimum=2,
        ),
        "similarity_validation_status": "uncalibrated_engineering_transform",
    }


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "backend": "librosa",
        "reason": reason,
        "measurements": {},
        "debug": {},
    }


def _zscore(features: np.ndarray) -> np.ndarray:
    mean = np.mean(features, axis=1, keepdims=True)
    scale = np.std(features, axis=1, keepdims=True)
    return (features - mean) / np.where(scale > 1e-6, scale, 1.0)


def _relative_f0(f0: np.ndarray, valid: np.ndarray) -> np.ndarray:
    values = f0[valid]
    if values.size == 0:
        return np.full(f0.shape, np.nan, dtype=float)
    median = float(np.median(values))
    result = np.full(f0.shape, np.nan, dtype=float)
    result[valid] = 12.0 * np.log2(f0[valid] / median)
    return result


def _active_intervals(librosa, audio: np.ndarray, parameters: dict) -> np.ndarray:
    intervals = librosa.effects.split(
        audio,
        top_db=parameters["silence_top_db"],
        frame_length=N_FFT,
        hop_length=HOP_LENGTH,
    )
    return np.asarray(intervals, dtype=int).reshape((-1, 2))


def _timing_measurements(librosa, reference: np.ndarray, student: np.ndarray, parameters: dict) -> dict[str, float | int]:
    def one(audio: np.ndarray) -> tuple[float, float, int, float]:
        intervals = _active_intervals(librosa, audio, parameters)
        total = max(len(audio) / SAMPLE_RATE, 1e-6)
        if not len(intervals):
            raise ValueError("no_active_audio")
        first, last = int(intervals[0, 0]), int(intervals[-1, 1])
        active_span = max((last - first) / SAMPLE_RATE, 1e-6)
        internal_pause = sum(
            max(0, int(start) - int(end)) / SAMPLE_RATE
            for (_, end), (start, _) in zip(intervals, intervals[1:])
        )
        return total, active_span, max(0, len(intervals) - 1), internal_pause / active_span

    reference_total, reference_span, reference_pause_count, reference_pause_ratio = one(reference)
    student_total, student_span, student_pause_count, student_pause_ratio = one(student)
    duration_ratio = student_span / reference_span
    duration_similarity = math.exp(-abs(math.log(duration_ratio)))
    pause_delta = abs(student_pause_ratio - reference_pause_ratio)
    return {
        "reference_duration_seconds": reference_total,
        "student_duration_seconds": student_total,
        "reference_active_span_seconds": reference_span,
        "student_active_span_seconds": student_span,
        "reference_pause_count": reference_pause_count,
        "student_pause_count": student_pause_count,
        "reference_pause_ratio": reference_pause_ratio,
        "student_pause_ratio": student_pause_ratio,
        "duration_ratio": duration_ratio,
        "duration_similarity": duration_similarity,
        "pause_ratio_absolute_difference": pause_delta,
        "timing_similarity": math.exp(-pause_delta) * duration_similarity,
    }


def _f0_measurements(librosa, reference: np.ndarray, student: np.ndarray, parameters: dict) -> tuple[dict[str, float | int | None], dict[str, Any]]:
    def one(audio: np.ndarray):
        f0, voiced_flag, voiced_probability = librosa.pyin(
            audio,
            sr=SAMPLE_RATE,
            fmin=parameters["fmin_hz"],
            fmax=parameters["fmax_hz"],
            frame_length=N_FFT,
            hop_length=HOP_LENGTH,
            fill_na=np.nan,
        )
        valid = (
            np.isfinite(f0)
            & np.asarray(voiced_flag, dtype=bool)
            & (np.asarray(voiced_probability) >= parameters["voiced_probability_minimum"])
        )
        return f0, valid, _relative_f0(f0, valid)

    reference_f0, reference_valid, reference_relative = one(reference)
    student_f0, student_valid, student_relative = one(student)
    reference_mfcc = _zscore(librosa.feature.mfcc(
        y=reference, sr=SAMPLE_RATE, n_mfcc=N_MFCC, n_mels=N_MELS,
        n_fft=N_FFT, hop_length=HOP_LENGTH,
    ))
    student_mfcc = _zscore(librosa.feature.mfcc(
        y=student, sr=SAMPLE_RATE, n_mfcc=N_MFCC, n_mels=N_MELS,
        n_fft=N_FFT, hop_length=HOP_LENGTH,
    ))
    # Bound the quadratic DTW matrix for long recordings. The same stride is
    # used for both sequences; path indices are restored to the F0 frame grid.
    stride = max(1, math.ceil(max(student_mfcc.shape[1], reference_mfcc.shape[1]) / parameters["max_dtw_frames"]))
    distance, path = librosa.sequence.dtw(
        X=student_mfcc[:, ::stride], Y=reference_mfcc[:, ::stride], metric="euclidean", backtrack=True,
    )
    path = np.asarray(path[::-1], dtype=int) * stride
    path_cost = float(distance[-1, -1] / max(len(path), 1))

    paired = []
    for student_index, reference_index in path:
        if student_index < len(student_relative) and reference_index < len(reference_relative):
            student_value = student_relative[student_index]
            reference_value = reference_relative[reference_index]
            if np.isfinite(student_value) and np.isfinite(reference_value):
                paired.append((float(student_value), float(reference_value)))
    student_values = np.asarray([item[0] for item in paired], dtype=float)
    reference_values = np.asarray([item[1] for item in paired], dtype=float)
    pitch_error = float(np.mean(np.abs(student_values - reference_values))) if paired else None
    if len(paired) >= 3 and np.std(student_values) > 1e-6 and np.std(reference_values) > 1e-6:
        correlation = float(np.corrcoef(student_values, reference_values)[0, 1])
    else:
        correlation = None
    measurements: dict[str, float | int | None] = {
        "mfcc_dtw_distance": path_cost,
        "mfcc_similarity": math.exp(-path_cost / parameters["mfcc_distance_scale"]),
        "reference_voiced_coverage": float(np.mean(reference_valid)),
        "student_voiced_coverage": float(np.mean(student_valid)),
        "aligned_pitch_pair_coverage": len(paired) / max(len(path), 1),
        "pitch_mae_semitones": pitch_error,
        "pitch_similarity": math.exp(-pitch_error / parameters["pitch_distance_scale_semitones"]) if pitch_error is not None else None,
        "pitch_correlation": correlation,
    }
    reference_times = librosa.times_like(reference_f0, sr=SAMPLE_RATE, hop_length=HOP_LENGTH)
    student_times = librosa.times_like(student_f0, sr=SAMPLE_RATE, hop_length=HOP_LENGTH)
    debug = {
        "reference_pitch_contour": [
            [float(time), float(value) if np.isfinite(value) else None]
            for time, value in zip(reference_times, reference_relative)
        ],
        "student_pitch_contour": [
            [float(time), float(value) if np.isfinite(value) else None]
            for time, value in zip(student_times, student_relative)
        ],
        "dtw_path_length": int(len(path)),
        "dtw_frame_stride": stride,
        "dtw_path": path.tolist(),
    }
    return measurements, debug


def compare_recordings(reference_audio_path: str, student_audio_path: str) -> dict[str, Any]:
    """Compare two recordings and return scalar evidence plus debug contours.

    This function never raises for an optional-dependency or signal-quality
    problem. The caller can continue using Praat and report the stable reason.
    """
    if not _enabled():
        return _unavailable("feature_flag_disabled")
    try:
        import librosa
    except Exception:
        return _unavailable("librosa_not_installed")
    parameters = _parameters()
    if parameters["fmin_hz"] >= parameters["fmax_hz"]:
        return _unavailable("invalid_pitch_range") | {"parameters": parameters}
    try:
        max_duration = parameters["max_duration_seconds"]
        reference, _ = librosa.load(reference_audio_path, sr=SAMPLE_RATE, mono=True, duration=max_duration + 1)
        student, _ = librosa.load(student_audio_path, sr=SAMPLE_RATE, mono=True, duration=max_duration + 1)
        if max(len(reference), len(student)) > max_duration * SAMPLE_RATE:
            return _unavailable("comparison_duration_limit_exceeded") | {"parameters": parameters}
        if not np.isfinite(reference).all() or not np.isfinite(student).all():
            return _unavailable("nonfinite_audio_samples")
        if not reference.any() or not student.any():
            return _unavailable("no_active_audio")
        if len(reference) < N_FFT or len(student) < N_FFT:
            return _unavailable("audio_too_short")
        silence_top_db = parameters["silence_top_db"]
        reference, _ = librosa.effects.trim(reference, top_db=silence_top_db)
        student, _ = librosa.effects.trim(student, top_db=silence_top_db)
        if len(reference) < N_FFT or len(student) < N_FFT:
            return _unavailable("voiced_audio_too_short")
        timing = _timing_measurements(librosa, reference, student, parameters)
        pitch, debug = _f0_measurements(librosa, reference, student, parameters)
        measurements = {**pitch, **timing}
        return {
            "status": "scored",
            "backend": "librosa",
            "librosa_version": librosa.__version__,
            "evidence_quality": "full" if pitch["pitch_similarity"] is not None else "degraded",
            "reason": None if pitch["pitch_similarity"] is not None else "insufficient_aligned_pitch",
            "parameters": parameters,
            "measurements": measurements,
            "debug": debug,
        }
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        return _unavailable(f"comparison_failed_{type(exc).__name__}") | {"parameters": parameters}
