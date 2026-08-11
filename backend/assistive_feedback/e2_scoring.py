"""Per-syllable Candidate E2 diagnostic score for live inference.

Reuses `context_aware_contour_scorer.score_segment_e2` exactly as validated
throughout every Candidate E2 OMPAL development/validation evaluation in
this project -- same per-syllable frame extraction, normalization, and
smoothing convention (`chinese_tones.normalize_pitch_contour` +
`_smooth_for_directional_scoring`, the same pair every prior E2 evaluation
used). No E2 formula is touched here.
"""

from __future__ import annotations

from typing import Sequence

import chinese_tones
from benchmarking.candidates.context_aware_contour_scorer import score_segment_e2
from tone_context import ExpectedTone


def score_syllable_e2(
    pitch_contour: Sequence[tuple[float, float]], start: float, end: float, expected: ExpectedTone,
) -> tuple[float, str, int]:
    frames = [(float(t), float(f)) for t, f in pitch_contour if start <= float(t) <= end]
    normalized = chinese_tones.normalize_pitch_contour(frames)
    smoothed = chinese_tones._smooth_for_directional_scoring(normalized)
    return score_segment_e2(smoothed, expected)
