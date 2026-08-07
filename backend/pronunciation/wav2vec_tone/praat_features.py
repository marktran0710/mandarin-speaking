"""Interpretable F0 and duration features per syllable, via Praat/Parselmouth.

The counterpart to the wav2vec2 embeddings: 13 named measurements instead of
768 opaque dimensions. Nothing here is combined with the embeddings yet -- this
step only produces and validates the features.

Two deliberate choices about missing data:

Unvoiced or untrackable frames yield NaN, never 0. A 0 Hz F0 is not a low
pitch, it is the absence of a measurement, and a classifier given 0 would
treat it as an extreme value and learn from it.

Implausible values are flagged but left in place. The saved file holds raw
measurements, so any later cleaning decision can be made -- and reversed --
with the evidence still present.

    python -m pronunciation.wav2vec_tone.praat_features
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pronunciation.wav2vec_tone.embedding_smoke_test import (
    DEFAULT_METADATA,
    decode_to_16k_mono,
)
from pronunciation.wav2vec_tone.extract_embeddings import TARGET_SAMPLE_RATE
from pronunciation.wav2vec_tone.prepare_dataset import DATASET_ID, KEEP_TONES

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_OUT = DATA_DIR / "praat_tone_features.csv"

# Pitch search range. Wide enough to span adult female (~350 Hz peaks in
# excited speech) and adult male (~70 Hz in creak) without letting the tracker
# wander into octave errors, which a wider range invites.
PITCH_FLOOR_HZ = 60.0
PITCH_CEILING_HZ = 500.0
PITCH_TIME_STEP = 0.005      # 5 ms: a 0.12 s clip yields ~24 frames rather than ~12

# Plausibility bounds for flagging, not for filtering.
PLAUSIBLE_F0_LOW = 60.0
PLAUSIBLE_F0_HIGH = 500.0
# Within one syllable F0 rarely spans a full octave; 2.0x usually means the
# tracker halved or doubled somewhere.
MAX_WITHIN_SYLLABLE_RATIO = 2.0
# Between adjacent 5 ms frames, physiology cannot move F0 by half again.
MAX_ADJACENT_FRAME_RATIO = 1.5
MIN_VOICED_PROPORTION = 0.30
MIN_VOICED_FRAMES = 3

TRAJECTORY_POINTS = (("f0_start", 0.0), ("f0_25", 0.25), ("f0_50", 0.50),
                     ("f0_75", 0.75), ("f0_end", 1.0))

FEATURE_NAMES = (
    "duration_seconds", "mean_f0_hz", "median_f0_hz", "min_f0_hz", "max_f0_hz",
    "f0_range_hz",
    "f0_start", "f0_25", "f0_50", "f0_75", "f0_end",
    "slope_start_to_mid", "slope_mid_to_end", "voiced_proportion",
)
# Extra columns kept alongside the required set.
EXTRA_NAMES = (
    "slope_start_to_mid_hz_per_s", "slope_mid_to_end_hz_per_s",
    "f0_sd_hz", "voiced_frames", "total_frames", "flags",
)
IDENTITY_NAMES = (
    "dataset_index", "utt_id", "speaker_id", "pinyin", "syllable_base", "tone",
    "speaker_variety", "pinyin_variety", "pinyin_source",
)


def semitones(high: float, low: float) -> float:
    """Interval in semitones -- a log ratio, so it is comparable across voices.

    A 20 Hz rise means something very different at 100 Hz than at 300 Hz. Slope
    in Hz/s is therefore partly a statement about the speaker; slope in
    semitones/s is much closer to a statement about the tone.
    """
    if not (np.isfinite(high) and np.isfinite(low)) or high <= 0 or low <= 0:
        return float("nan")
    return 12.0 * np.log2(high / low)


def robust_f0_at(times: np.ndarray, values: np.ndarray, position: float) -> float:
    """Median voiced F0 near a relative position in the voiced span.

    A single frame at exactly 25% may be unvoiced, or may be the one frame the
    tracker got wrong. Taking a median over a window around the target position
    is far more stable, and widening the window when it comes up empty keeps
    the feature defined for clips with a voicing gap in the middle.
    """
    if not len(values):
        return float("nan")
    start, end = float(times[0]), float(times[-1])
    span = end - start
    if span <= 0:
        return float(np.median(values))

    centre = start + position * span
    for fraction in (0.10, 0.20, 0.35):
        # At least 15 ms of window: on a 0.12 s clip, 10% of the span is barely
        # one frame, which would defeat the point of taking a median.
        half = max(fraction * span, 0.015)
        selected = values[(times >= centre - half) & (times <= centre + half)]
        if len(selected):
            return float(np.median(selected))
    # Last resort: the nearest voiced frame. Still a real measurement.
    return float(values[int(np.argmin(np.abs(times - centre)))])


def extract_one(audio: np.ndarray) -> dict:
    """All F0/duration features for one clip, plus any plausibility flags."""
    import parselmouth

    duration = len(audio) / TARGET_SAMPLE_RATE
    features = {name: float("nan") for name in FEATURE_NAMES + EXTRA_NAMES[:-1]}
    features["duration_seconds"] = duration
    flags = []

    sound = parselmouth.Sound(audio.astype(np.float64), TARGET_SAMPLE_RATE)
    try:
        pitch = sound.to_pitch(
            time_step=PITCH_TIME_STEP,
            pitch_floor=PITCH_FLOOR_HZ,
            pitch_ceiling=PITCH_CEILING_HZ,
        )
    except Exception:  # noqa: BLE001 - parselmouth raises PraatError
        # Praat needs at least three pitch periods, i.e. 3/floor seconds (~40 ms
        # at a 60 Hz floor). Shorter clips get no F0 at all rather than an F0
        # measured with a raised floor, which would silently mean something
        # different from every other row.
        flags.append("too_short_for_pitch")
        features["flags"] = "|".join(flags)
        return features
    frequencies = pitch.selected_array["frequency"]
    times = np.asarray(pitch.xs(), dtype=float)
    voiced = np.isfinite(frequencies) & (frequencies > 0)

    features["total_frames"] = float(len(frequencies))
    features["voiced_frames"] = float(int(voiced.sum()))
    features["voiced_proportion"] = (
        float(voiced.sum()) / len(frequencies) if len(frequencies) else float("nan")
    )

    if int(voiced.sum()) < MIN_VOICED_FRAMES:
        # Left as NaN rather than filled: there is genuinely no pitch here.
        flags.append("too_few_voiced")
        features["flags"] = "|".join(flags)
        return features

    voiced_times = times[voiced]
    voiced_f0 = frequencies[voiced]

    features["mean_f0_hz"] = float(np.mean(voiced_f0))
    # The reference for per-syllable semitone normalisation. Median rather
    # than mean because a single octave-error frame moves the mean and
    # would shift every relative feature derived from it.
    features["median_f0_hz"] = float(np.median(voiced_f0))
    features["min_f0_hz"] = float(np.min(voiced_f0))
    features["max_f0_hz"] = float(np.max(voiced_f0))
    features["f0_range_hz"] = features["max_f0_hz"] - features["min_f0_hz"]
    features["f0_sd_hz"] = float(np.std(voiced_f0, ddof=1)) if len(voiced_f0) > 1 else 0.0

    for name, position in TRAJECTORY_POINTS:
        features[name] = robust_f0_at(voiced_times, voiced_f0, position)

    half_span = max((float(voiced_times[-1]) - float(voiced_times[0])) / 2.0, 1e-6)
    features["slope_start_to_mid"] = (
        semitones(features["f0_50"], features["f0_start"]) / half_span
    )
    features["slope_mid_to_end"] = (
        semitones(features["f0_end"], features["f0_50"]) / half_span
    )
    features["slope_start_to_mid_hz_per_s"] = (
        features["f0_50"] - features["f0_start"]
    ) / half_span
    features["slope_mid_to_end_hz_per_s"] = (
        features["f0_end"] - features["f0_50"]
    ) / half_span

    if features["min_f0_hz"] < PLAUSIBLE_F0_LOW:
        flags.append("f0_below_floor")
    if features["max_f0_hz"] > PLAUSIBLE_F0_HIGH:
        flags.append("f0_above_ceiling")
    if features["min_f0_hz"] > 0 and \
            features["max_f0_hz"] / features["min_f0_hz"] >= MAX_WITHIN_SYLLABLE_RATIO:
        flags.append("octave_span")
    if len(voiced_f0) > 1:
        ratios = voiced_f0[1:] / np.maximum(voiced_f0[:-1], 1e-9)
        adjacent = np.maximum(ratios, 1.0 / np.maximum(ratios, 1e-9))
        # Only count jumps between frames that are actually adjacent in time;
        # a gap across an unvoiced stretch is not a tracking error.
        contiguous = np.diff(voiced_times) <= PITCH_TIME_STEP * 1.5
        if np.any(adjacent[contiguous] > MAX_ADJACENT_FRAME_RATIO):
            flags.append("frame_jump")
    if features["voiced_proportion"] < MIN_VOICED_PROPORTION:
        flags.append("low_voicing")

    features["flags"] = "|".join(flags)
    return features


def extract_all(metadata_path: Path, limit: int | None = None) -> tuple[list[dict], list[str]]:
    from datasets import Audio, load_dataset

    rows = list(csv.DictReader(metadata_path.open(encoding="utf-8")))
    if limit:
        rows = rows[:limit]
    print(f"[1] {len(rows)} records from {metadata_path.name}")

    print("[2] opening source parquet…")
    dataset = load_dataset(DATASET_ID, split="train").cast_column(
        "audio", Audio(decode=False)
    )
    subset = dataset.select([int(row["dataset_index"]) for row in rows])
    mismatches = [
        row["utt_id"] for row, actual in zip(rows, subset["utt_id"])
        if row["utt_id"] != actual
    ]
    if mismatches:
        raise RuntimeError(f"{len(mismatches)} stale dataset_index values.")
    print(f"    utt_id verified for all {len(rows)} records")

    print("[3] extracting Praat features…")
    extracted, failures = [], []
    for position, (row, audio_field) in enumerate(zip(rows, subset["audio"]), start=1):
        try:
            audio, _ = decode_to_16k_mono(audio_field["bytes"])
            record = {name: row.get(name, "") for name in IDENTITY_NAMES}
            record.update(extract_one(audio))
            extracted.append(record)
        except Exception as error:  # noqa: BLE001 - collected and reported
            failures.append(f"{row['utt_id']}: {error}")
        if position % 100 == 0:
            print(f"    {position}/{len(rows)}", end="\r")

    print(f"    extracted {len(extracted)}/{len(rows)}        ")
    for failure in failures[:10]:
        print(f"    FAILED {failure}")
    return extracted, failures


def column(records: list[dict], name: str) -> np.ndarray:
    return np.asarray([record.get(name, float("nan")) for record in records], dtype=float)


def describe(values: np.ndarray) -> str:
    finite = values[np.isfinite(values)]
    if not len(finite):
        return "        (no finite values)"
    return (f"{len(finite):>6}{np.min(finite):>10.2f}{np.percentile(finite, 25):>10.2f}"
            f"{np.median(finite):>10.2f}{np.mean(finite):>10.2f}"
            f"{np.percentile(finite, 75):>10.2f}{np.max(finite):>10.2f}"
            f"{np.std(finite, ddof=1) if len(finite) > 1 else 0.0:>10.2f}")


def report(records: list[dict], failures: list[str], path: Path, requested: int) -> str:
    tones = np.asarray([int(r["tone"]) for r in records])
    speakers = [str(r["speaker_id"]) for r in records]

    missing = {name: int((~np.isfinite(column(records, name))).sum())
               for name in FEATURE_NAMES}
    flag_counts = Counter(
        flag for record in records
        for flag in str(record.get("flags", "")).split("|") if flag
    )
    flagged = sum(1 for record in records if record.get("flags"))

    lines = [
        "",
        "=" * 78,
        f"Samples: {requested}",
        f"Successful extraction: {len(records)}",
        f"Failures: {len(failures)}",
        "",
        "Missing F0 counts (NaN, never zero-filled):",
    ]
    for name in FEATURE_NAMES:
        count = missing[name]
        lines.append(f"  {name:<28} {count:>4}"
                     + (f"  ({count / max(len(records), 1) * 100:.1f}%)" if count else ""))

    lines += ["", f"Implausible/outlier count: {flagged} samples carry at least one flag"]
    for flag, count in flag_counts.most_common():
        lines.append(f"  {flag:<28} {count:>4}"
                     f"  ({count / max(len(records), 1) * 100:.1f}%)")

    header = (f"  {'feature':<28}{'n':>6}{'min':>10}{'p25':>10}{'median':>10}"
              f"{'mean':>10}{'p75':>10}{'max':>10}{'sd':>10}")
    lines += ["", "Feature distributions, overall:", header]
    for name in FEATURE_NAMES:
        lines.append(f"  {name:<28}" + describe(column(records, name)))

    lines += ["", "Key features by tone:", ""]
    for name in ("duration_seconds", "mean_f0_hz", "f0_range_hz",
                 "slope_start_to_mid", "slope_mid_to_end", "voiced_proportion"):
        lines.append(f"  {name}")
        lines.append(f"  {'  tone':<28}{'n':>6}{'min':>10}{'p25':>10}{'median':>10}"
                     f"{'mean':>10}{'p75':>10}{'max':>10}{'sd':>10}")
        for tone in KEEP_TONES:
            values = column(records, name)[tones == tone]
            lines.append(f"    T{tone:<25}" + describe(values))
        lines.append("")

    lines += ["F0 by speaker (for a later normalisation decision):",
              f"  {'speaker':<12}{'n':>6}{'mean':>10}{'median':>10}{'sd':>10}"
              f"{'p10':>10}{'p90':>10}{'range':>10}"]
    by_speaker = defaultdict(list)
    for record, speaker in zip(records, speakers):
        value = record.get("mean_f0_hz", float("nan"))
        if np.isfinite(value):
            by_speaker[speaker].append(value)
    speaker_means = []
    for speaker in sorted(by_speaker):
        values = np.asarray(by_speaker[speaker])
        speaker_means.append(float(values.mean()))
        lines.append(
            f"  {speaker:<12}{len(values):>6}{values.mean():>10.1f}"
            f"{np.median(values):>10.1f}{values.std(ddof=1):>10.1f}"
            f"{np.percentile(values, 10):>10.1f}{np.percentile(values, 90):>10.1f}"
            f"{values.max() - values.min():>10.1f}"
        )
    if speaker_means:
        spread = max(speaker_means) - min(speaker_means)
        lines += [
            f"  speaker mean F0 spans {min(speaker_means):.0f}-{max(speaker_means):.0f} Hz "
            f"({spread:.0f} Hz, {semitones(max(speaker_means), min(speaker_means)):.1f} st)",
        ]

    lines += [
        "",
        f"Feature names: {', '.join(FEATURE_NAMES)}",
        f"Also saved: {', '.join(EXTRA_NAMES)}",
        "",
        f"Saved path: {path}",
        "=" * 78,
    ]
    return "\n".join(lines)


def save(records: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(IDENTITY_NAMES) + list(FEATURE_NAMES) + list(EXTRA_NAMES)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            row = dict(record)
            for name in FEATURE_NAMES + EXTRA_NAMES[:-1]:
                value = row.get(name, float("nan"))
                # Empty cell for a missing measurement. Not 0 -- 0 Hz would read
                # as a real, very low pitch to anything consuming this file.
                row[name] = "" if not np.isfinite(value) else f"{value:.6g}"
            writer.writerow(row)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    rows = sum(1 for _ in csv.DictReader(Path(args.metadata).open(encoding="utf-8")))
    records, failures = extract_all(Path(args.metadata), args.limit)
    path = save(records, Path(args.out))
    print(report(records, failures, path, args.limit or rows))
    print("\nFeatures extracted and validated. No model trained; not combined "
          "with wav2vec2.")


if __name__ == "__main__":
    main()
