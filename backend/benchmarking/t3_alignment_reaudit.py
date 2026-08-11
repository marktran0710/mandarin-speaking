"""T3 alignment re-audit: does the T3-context conclusion survive proper
syllable-level alignment, replacing the earlier 50/50 frame-count split?

    python -m benchmarking.t3_alignment_reaudit

**Candidate E V1 remains frozen** — not imported, not touched. **No OMPAL,
no final_test.** Alignment uses `tone_scoring.alignment.EnergyAligner`, the
EXISTING deterministic aligner already used by production (`praat_analyzer.
_aligner()` defaults to it via `TONE_ALIGNER=energy`) — no new model is
added, per the task's explicit instruction.

Scope: exactly the four two-syllable T3-as-first-syllable contexts named in
the task (`plus_t1`..`plus_t4` for `base_tone == 3`), across the same 3
zh-TW voices the earlier audit used — 12 audio files, all already generated
by `t3_context_audit.py` (`benchmarking/external/t3_context_audio/`, not
regenerated here).
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

import chinese_tones
from praat_analyzer import _intensity_contour_from_sound, _load_sound, _pitch_contour_from_sound
from tone_scoring.alignment import EnergyAligner
from benchmarking.t3_context_audit import (
    VOICES,
    _linear_slope,
    _quarter_points,
    classify_shape,
)

AUDIO_DIR = Path("benchmarking/external/t3_context_audio")
CONTEXT_CSV = Path("benchmarking/results/t3_controlled_context.csv")  # from the earlier audit, read-only

ALIGNED_CONTEXT_CSV = Path("benchmarking/results/t3_aligned_context.csv")
BOUNDARY_COMPARISON_CSV = Path("benchmarking/results/t3_boundary_comparison.csv")
REAUDIT_MD = Path("benchmarking/results/t3_alignment_reaudit.md")

#: Exactly the four contexts the task names -- T3 as the FIRST syllable,
#: followed by each of the four tones.
TARGET_CONTEXTS = ("plus_t1", "plus_t2", "plus_t3", "plus_t4")
BASE_TONE = 3  # T3 is the syllable under investigation


@dataclass(frozen=True)
class AlignedMeasurement:
    voice: str
    context: str
    audio_path: str
    old_50pct_boundary_s: float
    aligned_boundary_s: float
    difference_ms: float
    first_syllable_duration_s: float
    second_syllable_duration_s: float
    n_raw_frames: int
    n_first_syllable_frames: int
    f0_start: float | None
    f0_quarter: float | None
    f0_mid: float | None
    f0_three_quarter: float | None
    f0_end: float | None
    first_half_slope: float | None
    second_half_slope: float | None
    full_slope: float | None
    min_location_frac: float | None
    max_location_frac: float | None
    range_: float | None
    duration_seconds: float | None
    voiced_fraction: float | None
    shape_category: str
    error: str


def _old_5050_boundary_seconds(raw_contour: list[tuple[float, float]]) -> float:
    """Reproduces exactly what `t3_context_audit.py`'s original heuristic
    did: a 50/50 split by FRAME COUNT (not time), so the "old boundary" here
    is the timestamp of the frame at `len(raw_contour) // 2`."""
    half = len(raw_contour) // 2
    if half >= len(raw_contour):
        half = len(raw_contour) - 1
    return float(raw_contour[half][0])


def measure_aligned(voice: str, context: str) -> AlignedMeasurement:
    audio_path = AUDIO_DIR / f"{voice}_{BASE_TONE}_{context}.wav"
    sound = _load_sound(str(audio_path))
    raw_contour = _pitch_contour_from_sound(sound)
    intensity = _intensity_contour_from_sound(sound)

    if len(raw_contour) < 4:
        return AlignedMeasurement(
            voice=voice, context=context, audio_path=str(audio_path),
            old_50pct_boundary_s=0.0, aligned_boundary_s=0.0, difference_ms=0.0,
            first_syllable_duration_s=0.0, second_syllable_duration_s=0.0,
            n_raw_frames=len(raw_contour), n_first_syllable_frames=0,
            f0_start=None, f0_quarter=None, f0_mid=None, f0_three_quarter=None, f0_end=None,
            first_half_slope=None, second_half_slope=None, full_slope=None,
            min_location_frac=None, max_location_frac=None, range_=None,
            duration_seconds=None, voiced_fraction=None,
            shape_category="unmeasured", error="too few raw pitch frames",
        )

    old_boundary = _old_5050_boundary_seconds(raw_contour)

    spans = EnergyAligner().align(raw_contour, syllable_count=2, intensity=intensity)
    if len(spans) != 2:
        return AlignedMeasurement(
            voice=voice, context=context, audio_path=str(audio_path),
            old_50pct_boundary_s=old_boundary, aligned_boundary_s=0.0, difference_ms=0.0,
            first_syllable_duration_s=0.0, second_syllable_duration_s=0.0,
            n_raw_frames=len(raw_contour), n_first_syllable_frames=0,
            f0_start=None, f0_quarter=None, f0_mid=None, f0_three_quarter=None, f0_end=None,
            first_half_slope=None, second_half_slope=None, full_slope=None,
            min_location_frac=None, max_location_frac=None, range_=None,
            duration_seconds=None, voiced_fraction=None,
            shape_category="unmeasured", error=f"EnergyAligner returned {len(spans)} spans, expected 2",
        )

    first_span, second_span = spans
    aligned_boundary = first_span.end
    difference_ms = (aligned_boundary - old_boundary) * 1000.0

    first_syllable_frames = first_span.frames(raw_contour)
    if len(first_syllable_frames) < 4:
        return AlignedMeasurement(
            voice=voice, context=context, audio_path=str(audio_path),
            old_50pct_boundary_s=old_boundary, aligned_boundary_s=aligned_boundary,
            difference_ms=difference_ms,
            first_syllable_duration_s=first_span.duration, second_syllable_duration_s=second_span.duration,
            n_raw_frames=len(raw_contour), n_first_syllable_frames=len(first_syllable_frames),
            f0_start=None, f0_quarter=None, f0_mid=None, f0_three_quarter=None, f0_end=None,
            first_half_slope=None, second_half_slope=None, full_slope=None,
            min_location_frac=None, max_location_frac=None, range_=None,
            duration_seconds=None, voiced_fraction=None,
            shape_category="unmeasured", error="too few frames in aligned first-syllable span",
        )

    normalized = chinese_tones.normalize_pitch_contour(first_syllable_frames)
    if len(normalized) < 4:
        return AlignedMeasurement(
            voice=voice, context=context, audio_path=str(audio_path),
            old_50pct_boundary_s=old_boundary, aligned_boundary_s=aligned_boundary,
            difference_ms=difference_ms,
            first_syllable_duration_s=first_span.duration, second_syllable_duration_s=second_span.duration,
            n_raw_frames=len(raw_contour), n_first_syllable_frames=len(first_syllable_frames),
            f0_start=None, f0_quarter=None, f0_mid=None, f0_three_quarter=None, f0_end=None,
            first_half_slope=None, second_half_slope=None, full_slope=None,
            min_location_frac=None, max_location_frac=None, range_=None,
            duration_seconds=None, voiced_fraction=None,
            shape_category="unmeasured", error="too few normalized frames",
        )
    smoothed = chinese_tones._smooth_for_directional_scoring(normalized)

    start, q1, mid, q3, end = _quarter_points(smoothed)
    half_n = len(smoothed) // 2
    first_half, second_half = smoothed[: half_n + 1], smoothed[half_n:]
    full_slope = _linear_slope(smoothed)
    first_slope = _linear_slope(first_half)
    second_slope = _linear_slope(second_half)
    min_idx = int(np.argmin(smoothed))
    max_idx = int(np.argmax(smoothed))
    shape = classify_shape(first_slope, second_slope)

    return AlignedMeasurement(
        voice=voice, context=context, audio_path=str(audio_path),
        old_50pct_boundary_s=round(old_boundary, 4),
        aligned_boundary_s=round(aligned_boundary, 4),
        difference_ms=round(difference_ms, 1),
        first_syllable_duration_s=round(first_span.duration, 4),
        second_syllable_duration_s=round(second_span.duration, 4),
        n_raw_frames=len(raw_contour),
        n_first_syllable_frames=len(first_syllable_frames),
        f0_start=round(start, 4), f0_quarter=round(q1, 4), f0_mid=round(mid, 4),
        f0_three_quarter=round(q3, 4), f0_end=round(end, 4),
        first_half_slope=round(first_slope, 4), second_half_slope=round(second_slope, 4),
        full_slope=round(full_slope, 4),
        min_location_frac=round(min_idx / max(1, len(smoothed) - 1), 3),
        max_location_frac=round(max_idx / max(1, len(smoothed) - 1), 3),
        range_=round(float(np.max(smoothed) - np.min(smoothed)), 4),
        duration_seconds=round(first_span.duration, 4),
        voiced_fraction=round(len(first_syllable_frames) / max(1, len(raw_contour)), 3),
        shape_category=shape, error="",
    )


def _old_shape_lookup() -> dict[tuple[str, str], str]:
    """Reads the earlier audit's own recorded 50/50-split shape
    classification straight from its CSV, so STEP 4's comparison is against
    what that audit ACTUALLY recorded, not a re-derivation of it."""
    lookup = {}
    with CONTEXT_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if int(row["base_tone"]) == BASE_TONE and row["context"] in TARGET_CONTEXTS:
                lookup[(row["voice"], row["context"])] = row["shape_category"]
    return lookup


def run() -> dict[str, Any]:
    measurements = [
        measure_aligned(voice, context) for voice in VOICES for context in TARGET_CONTEXTS
    ]
    old_shapes = _old_shape_lookup()

    rows = []
    for m in measurements:
        old_shape = old_shapes.get((m.voice, m.context), "unknown")
        rows.append({**asdict(m), "old_50pct_shape_category": old_shape, "shape_changed": old_shape != m.shape_category})

    _write_aligned_csv(rows)
    _write_boundary_csv(rows)

    return {"rows": rows}


_ALIGNED_FIELDS = [
    "voice", "context", "audio_path",
    "old_50pct_boundary_s", "aligned_boundary_s", "difference_ms",
    "first_syllable_duration_s", "second_syllable_duration_s",
    "n_raw_frames", "n_first_syllable_frames",
    "f0_start", "f0_quarter", "f0_mid", "f0_three_quarter", "f0_end",
    "first_half_slope", "second_half_slope", "full_slope",
    "min_location_frac", "max_location_frac", "range_", "duration_seconds",
    "voiced_fraction", "old_50pct_shape_category", "shape_category", "shape_changed", "error",
]


def _write_aligned_csv(rows: list[dict[str, Any]], path: Path = ALIGNED_CONTEXT_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_ALIGNED_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in _ALIGNED_FIELDS})


_BOUNDARY_FIELDS = [
    "voice", "context", "old_50pct_boundary_s", "aligned_boundary_s", "difference_ms",
    "first_syllable_duration_s", "second_syllable_duration_s",
]


def _write_boundary_csv(rows: list[dict[str, Any]], path: Path = BOUNDARY_COMPARISON_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_BOUNDARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in _BOUNDARY_FIELDS})


if __name__ == "__main__":
    from benchmarking import report_t3_alignment_reaudit

    result = run()
    report_t3_alignment_reaudit.write_reaudit_report(result, REAUDIT_MD)
    print(f"Aligned context CSV: {ALIGNED_CONTEXT_CSV}")
    print(f"Boundary comparison CSV: {BOUNDARY_COMPARISON_CSV}")
    print(f"Reaudit report: {REAUDIT_MD}")
