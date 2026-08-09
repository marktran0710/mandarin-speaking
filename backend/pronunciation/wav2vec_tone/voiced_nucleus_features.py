"""Train-only, acoustic voiced-nucleus *proxy* for tone research.

This module does **not** estimate vowel or phone boundaries.  OMPAL has no
phone-boundary gold labels, so calling a frame span a vowel would be false
precision.  Instead it derives a reproducible acoustic proxy from the token
audio alone:

1. find Praat voiced F0 frames;
2. retain frames at or above the token's 35th percentile voiced intensity;
3. choose the longest contiguous retained run; and
4. time-normalise its semitone F0 to twelve points.

If intensity is unavailable or the run is too short, the proxy falls back to
the full voiced span and records that fact.  It never reads pinyin, expected
tone, character, correctness, speaker identity, Dev, or Test rows.

The result is an acoustic representation for speaker-disjoint research.  It
is not phone alignment and requires phone-boundary gold data before any
boundary-accuracy claim.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from pronunciation.wav2vec_tone.phase_c6_f0_trajectory import (
    PITCH_CEILING,
    PITCH_FLOOR,
    PITCH_STEP,
    SAMPLE_RATE,
)

DATA_DIR = Path(__file__).resolve().parent / "data"
MANIFEST = DATA_DIR / "ompal_full_tone_benchmark_manifest_split.csv"
FEATURE_CACHE = DATA_DIR / "dev_features_train_dev.npz"
DEFAULT_CACHE = DATA_DIR / "voiced_nucleus_proxy_train.npz"

VOICED_NUCLEUS_PROXY_SCHEMA_VERSION = "voiced_nucleus_proxy.v1"
VOICED_NUCLEUS_PROXY_UNIT = "semitones_re_1hz"
POINTS = 12
INTENSITY_QUANTILE = 0.35
MIN_VOICED_FRAMES = 4


def _longest_contiguous_run(indices: np.ndarray) -> np.ndarray:
    """Return the longest sequence of adjacent frame indices."""
    if not len(indices):
        return np.asarray([], dtype=int)
    start = last = int(indices[0])
    runs: list[tuple[int, int]] = []
    for value in indices[1:]:
        value = int(value)
        if value == last + 1:
            last = value
        else:
            runs.append((start, last))
            start = last = value
    runs.append((start, last))
    begin, end = max(runs, key=lambda run: run[1] - run[0])
    return np.arange(begin, end + 1, dtype=int)


def voiced_nucleus_proxy_from_segment(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> tuple[np.ndarray, str]:
    """Return a 12-point energy-weighted voiced-nucleus proxy in semitones.

    The status distinguishes a successful energy-weighted proxy from the
    documented full-voiced fallbacks.  All failure paths keep missing values;
    an estimator must use fold-local imputation rather than inventing a
    contour.
    """
    import parselmouth

    values = np.asarray(audio, dtype=np.float64)
    if values.ndim == 2:
        values = values.mean(axis=1)
    if len(values) < 2:
        return np.full(POINTS, np.nan), "empty_audio"
    try:
        sound = parselmouth.Sound(values, sampling_frequency=sample_rate)
        pitch = sound.to_pitch(time_step=PITCH_STEP, pitch_floor=PITCH_FLOOR,
                               pitch_ceiling=PITCH_CEILING)
    except Exception:  # Praat rejects very short audio, among other cases.
        return np.full(POINTS, np.nan), "pitch_unavailable"

    frequencies = np.asarray(pitch.selected_array["frequency"], dtype=float)
    times = np.asarray(pitch.xs(), dtype=float)
    voiced = np.isfinite(frequencies) & (frequencies > 0)
    if int(voiced.sum()) < MIN_VOICED_FRAMES:
        return np.full(POINTS, np.nan), "insufficient_voiced_frames"

    try:
        intensity = sound.to_intensity(time_step=PITCH_STEP, minimum_pitch=PITCH_FLOOR)
        intensity_values = np.asarray(intensity.values[0], dtype=float)
        frame_intensity = np.interp(times, np.asarray(intensity.xs(), dtype=float),
                                    intensity_values, left=np.nan, right=np.nan)
        voiced_intensity = frame_intensity[voiced]
        if not np.isfinite(voiced_intensity).any():
            raise ValueError("no finite intensity at voiced frames")
        threshold = float(np.nanquantile(voiced_intensity, INTENSITY_QUANTILE))
        active = voiced & np.isfinite(frame_intensity) & (frame_intensity >= threshold)
        chosen = _longest_contiguous_run(np.flatnonzero(active))
        if len(chosen) >= MIN_VOICED_FRAMES:
            status = "energy_voiced_nucleus_proxy"
        else:
            chosen = np.flatnonzero(voiced)
            status = "energy_proxy_insufficient_full_voiced"
    except Exception:
        chosen = np.flatnonzero(voiced)
        status = "intensity_unavailable_full_voiced"

    semitones = 12.0 * np.log2(frequencies[chosen])
    grid = np.linspace(times[chosen[0]], times[chosen[-1]], POINTS)
    return np.interp(grid, times[chosen], semitones), status


def cache_metadata() -> dict:
    """Versioned provenance persisted alongside a Train-only matrix."""
    return {
        "schema_version": VOICED_NUCLEUS_PROXY_SCHEMA_VERSION,
        "unit": VOICED_NUCLEUS_PROXY_UNIT,
        "points": POINTS,
        "source_partition": "train_only",
        "selection": "longest contiguous voiced run at/above token voiced-intensity 35th percentile",
        "fallback": "full voiced span when intensity/run evidence is insufficient",
        "not_phone_alignment": True,
        "not_vowel_boundary_gold": True,
        "forbidden_inputs": [
            "expected_tone", "pinyin", "character", "word_script",
            "tone_correctness", "speaker_id", "utterance_id", "Dev", "Test",
        ],
        "pitch": {
            "floor_hz": PITCH_FLOOR,
            "ceiling_hz": PITCH_CEILING,
            "time_step_seconds": PITCH_STEP,
        },
    }


def build_train_cache(
    manifest_path: Path = MANIFEST,
    feature_cache_path: Path = FEATURE_CACHE,
    output_path: Path = DEFAULT_CACHE,
) -> dict:
    """Build a cache only for token IDs already marked ``train`` in the cache."""
    import soundfile as sf

    cache = np.load(feature_cache_path, allow_pickle=True)
    required = {"token_ids", "split"}
    missing = required - set(cache.files)
    if missing:
        raise ValueError(f"feature cache missing {sorted(missing)}")
    # A cache containing Test data is not safe for this research helper even
    # though its rows would be filtered later; fail closed instead.
    split = cache["split"].astype(str)
    if np.any(split == "test"):
        raise ValueError("TEST LOCK VIOLATION: feature cache contains test rows")
    train = split == "train"
    token_ids = cache["token_ids"].astype(str)[train]
    if not len(token_ids):
        raise ValueError("feature cache has no train rows")

    manifest_rows = {
        row["token_id"]: row
        for row in csv.DictReader(manifest_path.open(encoding="utf-8"))
        if row["split"] == "train"
    }
    if any(token_id not in manifest_rows for token_id in token_ids):
        raise ValueError("Train cache/manifest token IDs do not match")

    trajectories: list[np.ndarray] = []
    statuses: list[str] = []
    for token_id in token_ids:
        row = manifest_rows[token_id]
        try:
            audio, sample_rate = sf.read(str(DATA_DIR / row["extracted_token_path"]), dtype="float32")
            trajectory, status = voiced_nucleus_proxy_from_segment(audio, int(sample_rate))
        except Exception:
            trajectory, status = np.full(POINTS, np.nan), "unreadable_audio"
        trajectories.append(trajectory)
        statuses.append(status)

    metadata = cache_metadata()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        token_ids=token_ids,
        trajectories=np.asarray(trajectories, dtype=float),
        statuses=np.asarray(statuses, dtype=object),
        metadata_json=np.asarray(json.dumps(metadata, sort_keys=True)),
    )
    return {
        "path": str(output_path),
        "n_tokens": int(len(token_ids)),
        "finite_trajectory_rate": float(np.isfinite(trajectories).all(axis=1).mean()),
        "status_counts": dict(Counter(statuses)),
        "metadata": metadata,
    }


def load_train_cache(token_ids: np.ndarray, path: Path = DEFAULT_CACHE) -> tuple[np.ndarray, np.ndarray, dict]:
    """Load a requested ordered Train-only subset without guessing its rows."""
    stored = np.load(path, allow_pickle=True)
    required = {"token_ids", "trajectories", "statuses", "metadata_json"}
    missing = required - set(stored.files)
    if missing:
        raise ValueError(f"nucleus cache missing {sorted(missing)}")
    metadata = json.loads(str(stored["metadata_json"].item()))
    if metadata.get("schema_version") != VOICED_NUCLEUS_PROXY_SCHEMA_VERSION:
        raise ValueError("voiced-nucleus cache schema mismatch")
    if metadata.get("unit") != VOICED_NUCLEUS_PROXY_UNIT:
        raise ValueError("voiced-nucleus cache unit mismatch")
    if metadata.get("source_partition") != "train_only":
        raise ValueError("voiced-nucleus cache is not Train-only")
    stored_ids = stored["token_ids"].astype(str)
    requested_ids = np.asarray(token_ids, dtype=str)
    if len(set(stored_ids.tolist())) != len(stored_ids):
        raise ValueError("voiced-nucleus cache contains duplicate token IDs")
    positions = {token_id: index for index, token_id in enumerate(stored_ids.tolist())}
    if any(token_id not in positions for token_id in requested_ids):
        raise ValueError("requested token is absent from the Train-only nucleus cache")
    selection = np.asarray([positions[token_id] for token_id in requested_ids], dtype=int)
    trajectory = np.asarray(stored["trajectories"], dtype=float)
    if trajectory.shape != (len(stored_ids), POINTS):
        raise ValueError("voiced-nucleus cache trajectory shape mismatch")
    return trajectory[selection], stored["statuses"].astype(str)[selection], metadata


def main() -> None:
    report = build_train_cache()
    print(f"built Train-only voiced-nucleus proxy cache: {report['n_tokens']} tokens")
    print(f"finite trajectories: {report['finite_trajectory_rate']:.1%}")
    print(f"statuses: {report['status_counts']}")


if __name__ == "__main__":
    main()
