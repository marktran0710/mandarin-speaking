"""CANDIDATE E — an interpretable, corrected contour scorer.

    python -m benchmarking.candidates.contour_scorer_v2

**BASELINE_A_FROZEN**: the production scorer this candidate is compared
against is `chinese_tones.directional_tone_scores` (and everything it
calls), used here strictly read-only, imported and never modified. It
remains the only scorer that drives the progression gate and threshold 58.
This module is a wholly separate implementation; nothing here is wired into
production, and nothing in production imports this module.

Scope, per the task that authorized this candidate: fix the two formula
problems the diagnosis (`directional_tone_formula_audit.md`) identified --

  - T1's flatness rule (`variance < 0.12`) is severely over-permissive and
    was not shape-specific (a shallow-range T3 dip could pass as T1).
  - T3's dip formula (`avg(start,end) - mid_min`) is not shape-specific
    either -- a monotonic rise or fall can satisfy it without ever falling
    then rising.

T2 and T4's formulas are UNCHANGED from `chinese_tones.py`: the diagnosis
found their idealized canonical behaviour directionally correct (diagonal
highest in each column of the 4x4 matrix); the controlled-audio failure
there traced to the onset-skip windowing interacting badly with short
isolated syllables, which this module addresses separately (STEP 4) rather
than by changing the T2/T4 formulas themselves.

Every constant below is justified from canonical contours and/or the
existing controlled synthetic audio set (`benchmarking/external/
controlled_tone_test/audio/`) -- **never from OMPAL labels**. See
`benchmarking/results/candidate_e_formula.md` for the full rationale
alongside each constant, and `directional_tone_diagnosis.py` /
`report_directional_tone_diagnosis.py` for the diagnosis that motivated
this module.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# STEP 2 -- T1 (flat): shape-specific, not variance-only
# ---------------------------------------------------------------------------

#: Canonical T1 has slope=0; canonical T2/T4 have |slope| >= 0.72 (see
#: `candidate_e_formula.md` §T1 for the exact computed values). 0.3 sits
#: comfortably below both, with more than 2x headroom on either side, so a
#: genuinely flat contour is never penalized by ordinary measurement noise
#: while a genuinely moving one is.
T1_SLOPE_REF = 0.3
#: Canonical T1 has range=0; canonical T3 (the shape T1's OLD variance-only
#: rule was fooled by) has range=0.45 despite its near-zero net slope
#: (0.04) -- slope alone cannot separate T1 from T3, which is exactly the
#: old formula's failure mode. 0.2 sits below T3's 0.45 with margin, while
#: still well above the range a genuinely flat contour should show.
T1_RANGE_REF = 0.2


def _linear_slope(seg: np.ndarray) -> float:
    """Total predicted rise across the segment from a least-squares line
    fit (index vs value), not just `last - first` -- robust to a single
    noisy endpoint frame the way a plain endpoint difference is not."""
    n = len(seg)
    if n < 2:
        return 0.0
    x = np.arange(n)
    slope_per_step = float(np.polyfit(x, seg, 1)[0])
    return slope_per_step * (n - 1)


def _score_t1(seg: np.ndarray) -> float:
    slope = abs(_linear_slope(seg))
    value_range = float(np.max(seg) - np.min(seg))
    slope_factor = max(0.0, 1.0 - slope / T1_SLOPE_REF)
    range_factor = max(0.0, 1.0 - value_range / T1_RANGE_REF)
    return slope_factor * range_factor * 100.0


# ---------------------------------------------------------------------------
# STEP 3 -- T3 (dip): shape validity (fall THEN rise) gates dip depth
# ---------------------------------------------------------------------------

#: How much of the segment counts as "first half" / "second half" for the
#: shape-validity check -- a plain midpoint split, symmetric with the
#: existing `s_mean`/`e_mean` quarter-region convention this file inherits
#: from `chinese_tones._score_segment`.
def _half_split(seg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mid = len(seg) // 2
    first = seg[: mid + 1]
    second = seg[mid:]
    return first, second


#: Canonical T3's own first/second-half slopes are -0.4 / +0.45 (see
#: `candidate_e_formula.md` §T3). 0.05 only requires the SIGN to be
#: unambiguous (comfortably above measurement-noise-level slopes near
#: zero), not that the magnitude approach canonical's -- shape validity is
#: a yes/no gate; magnitude is `dip_depth`'s job, separately.
T3_SHAPE_SLOPE_EPS = 0.05
#: Same dip-depth definition `chinese_tones._score_segment` already used
#: (avg of start/end regions minus the middle's minimum) -- STEP 3 only
#: asked to add a shape-validity gate in front of it, not to redefine depth
#: itself. Calibrated so canonical T3's own dip_depth (0.425, see the
#: formula doc) maps to 100.
T3_DEPTH_OFFSET = 0.25
T3_DEPTH_SCALE = 0.55
#: Ceiling applied when the shape-validity gate fails (a monotonic rise or
#: fall, not a genuine dip). Chosen well below threshold territory and well
#: below any valid dip's likely score, so a monotonic contour cannot pass
#: as T3 regardless of how large its raw dip_depth number happens to be --
#: this is precisely the failure STEP 3 was written to close (canonical T2
#: scored 90.9 and canonical T4 scored 81.8 against a T3 target under the
#: OLD formula).
T3_INVALID_SHAPE_CEILING = 20.0


def _score_t3(seg: np.ndarray) -> float:
    q = max(1, len(seg) // 4)
    s_mean = float(np.mean(seg[:q]))
    e_mean = float(np.mean(seg[-q:]))
    mid_seg = seg[q: len(seg) - q]
    mid_min = float(np.min(mid_seg)) if len(mid_seg) else float(np.min(seg))
    dip_depth = (s_mean + e_mean) / 2.0 - mid_min

    first_half, second_half = _half_split(seg)
    first_slope = _linear_slope(first_half)
    second_slope = _linear_slope(second_half)
    shape_valid = first_slope <= -T3_SHAPE_SLOPE_EPS and second_slope >= T3_SHAPE_SLOPE_EPS

    if shape_valid:
        return max(0.0, min(1.0, (dip_depth + T3_DEPTH_OFFSET) / T3_DEPTH_SCALE)) * 100.0
    # Not a genuine dip: cap well below what a real one could score,
    # regardless of how large dip_depth alone would otherwise suggest.
    depth_component = max(0.0, dip_depth) * 40.0
    return min(T3_INVALID_SHAPE_CEILING, depth_component)


# ---------------------------------------------------------------------------
# T2 / T4 -- UNCHANGED from chinese_tones._score_segment (see module
# docstring for why: the diagnosis found these directionally correct).
# ---------------------------------------------------------------------------


def _score_t2(seg: np.ndarray) -> float:
    q = max(1, len(seg) // 4)
    s_mean = float(np.mean(seg[:q]))
    e_mean = float(np.mean(seg[-q:]))
    rise = e_mean - s_mean
    return max(0.0, min(1.0, (rise + 0.5) / 1.0)) * 100.0


def _score_t4(seg: np.ndarray) -> float:
    q = max(1, len(seg) // 4)
    s_mean = float(np.mean(seg[:q]))
    e_mean = float(np.mean(seg[-q:]))
    fall = s_mean - e_mean
    return max(0.0, min(1.0, (fall + 0.5) / 1.0)) * 100.0


def score_segment_v2(seg: np.ndarray, tone: int) -> tuple[float, str]:
    """Candidate E's per-syllable score, mirroring
    `chinese_tones._score_segment`'s signature and short-segment fallback
    exactly so the two are drop-in comparable."""
    seg = np.asarray(seg, dtype=float)
    if len(seg) < 4:
        return 65.0, "constant_short_segment"
    if tone == 1:
        return _score_t1(seg), "measured"
    if tone == 2:
        return _score_t2(seg), "measured"
    if tone == 3:
        return _score_t3(seg), "measured"
    if tone == 4:
        return _score_t4(seg), "measured"
    return 75.0, "neutral_not_measured"


# ---------------------------------------------------------------------------
# STEP 4 -- preprocessing: onset skip, chosen from the ablation, not reused
# from praat_analyzer.py's alignment-dependent windowing.
#
# Candidate E deliberately does NOT reuse `estimate_word_prosody`'s
# alignment-based word-span + 12%-onset-skip windowing: the diagnosis found
# that pipeline actively harmful for short, isolated syllables (a genuinely
# rising T2 recording measured `rise = -0.1976`, backwards, after that
# windowing -- see `directional_tone_formula_audit.md`'s onset-skip
# finding). Candidate E instead works from the syllable's OWN full
# extracted pitch contour (`praat_analyzer.extract_pitch`), trimming a
# configurable leading fraction chosen by the STEP 4 ablation
# (`candidate_e_onset_ablation.csv`) -- simpler, self-contained, and not
# dependent on alignment machinery this candidate isn't trying to fix.
# ---------------------------------------------------------------------------

#: Selected by the STEP 4 ablation over {0, 3, 5, 8, 12}% -- see
#: `candidate_e_formula.md` §Onset ablation for the full evidence and why
#: this value was chosen over the others.
ONSET_SKIP_FRACTION = 0.0


def apply_onset_skip(pitch_contour: list[tuple[float, float]], fraction: float = ONSET_SKIP_FRACTION) -> list[tuple[float, float]]:
    if not pitch_contour or fraction <= 0:
        return list(pitch_contour)
    start_time = pitch_contour[0][0]
    end_time = pitch_contour[-1][0]
    skip_until = start_time + (end_time - start_time) * fraction
    trimmed = [point for point in pitch_contour if point[0] >= skip_until]
    return trimmed if len(trimmed) >= 4 else list(pitch_contour)


def directional_tone_scores_v2(
    pitch_contour: list[tuple[float, float]],
    tones: list[int],
    syllable_windows: list[tuple[int, int]] | None = None,
) -> tuple[list[float], list[str]]:
    """Candidate E's top-level entry point -- mirrors
    `directional_tone_scores_with_provenance`'s signature and return shape
    exactly, so the two can be run side by side on the same inputs."""
    import chinese_tones

    trimmed = apply_onset_skip(pitch_contour, ONSET_SKIP_FRACTION)
    user_pitch = chinese_tones.normalize_pitch_contour(trimmed)
    if len(user_pitch) == 0 or not tones:
        return [], []
    user_pitch = chinese_tones._smooth_for_directional_scoring(user_pitch)

    tones_s = chinese_tones.apply_tone_sandhi(tones)
    n = len(tones_s)
    syl_len = max(1, len(user_pitch) // n)
    windows = syllable_windows if syllable_windows and len(syllable_windows) == n else None

    scores: list[float] = []
    provenance: list[str] = []
    for i, tone in enumerate(tones_s):
        start, end = chinese_tones._window_for(i, n, syl_len, len(user_pitch), windows)
        seg = user_pitch[start:end]
        score, source = score_segment_v2(seg, tone)
        scores.append(score)
        provenance.append(source)
    return scores, provenance


if __name__ == "__main__":
    from benchmarking.candidates import contour_scorer_v2_pipeline

    contour_scorer_v2_pipeline.run()
