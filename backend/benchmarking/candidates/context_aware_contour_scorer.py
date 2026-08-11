"""CANDIDATE E2 — context-aware interpretable Mandarin tone scorer.

    python -m benchmarking.candidates.context_aware_contour_scorer_pipeline

**Candidate E V1 remains frozen** (`contour_scorer_v2.py` — imported
read-only here for its T1/T2/T3-full/T4 formulas, never edited). **No
OMPAL, no final_test. `tone_context.py` is imported read-only and never
edited.**

## The one architectural change from Candidate E V1

E V1 scores a segment against a bare `tone: int`. Every prior audit in this
research program (`t3_context_audit.md`, `tone_context_planner_audit.md`)
converged on the same finding: `tone_context.plan_expected_tones` already
computes the right linguistic context (previous/following tone, phrase
boundaries, sandhi rules) — it is simply discarded before reaching the
scorer. This module's only structural change is to accept a
`tone_context.ExpectedTone` object instead of a bare tone integer, and to
try every tone in `expected.accepted_surface_tones` rather than assuming
there is exactly one correct answer. This is also a documented, deliberate
gap in `tone_context.py` itself:

    "`half_third` is represented but not yet scored differently: the
    contour scorer still uses one T3 template for both realizations."
    (tone_context.py, "KNOWN GAPS", line ~381)

Nothing here duplicates `tone_context`'s linguistic rules — this module
never decides what tone is acceptable in a given context; it only decides
how to SCORE an already-decided acceptable tone.
"""

from __future__ import annotations

import numpy as np

from benchmarking.candidates.contour_scorer_v2 import (
    _half_split,
    _linear_slope,
    _score_t1,
    _score_t2,
    _score_t3,
    _score_t4,
)
from tone_context import CANONICAL, FULL_THIRD, HALF_THIRD, NEUTRAL, THIRD_CHAIN, THIRD_SANDHI, ExpectedTone

# ---------------------------------------------------------------------------
# STEP 4 -- half-third scorer (T3 before a non-T3 tone, not phrase-final)
# ---------------------------------------------------------------------------

#: The base "predominantly low/falling" component reuses `_score_t4`'s exact
#: primitive (`fall = s_mean - e_mean`, quarter-region means) but with a
#: more lenient offset: half-third explicitly accepts BOTH falling AND flat
#: (task: "predominantly low / falling realization ... no requirement for
#: late rise"), whereas T4's own 0.5 offset is calibrated to require a
#: clear fall. Calibrated from `t3_aligned_context.csv`'s
#: `plus_t1`/`plus_t2`/`plus_t4` rows (the EnergyAligner-aligned, properly
#: segmented controlled evidence -- no OMPAL): every one of those 9
#: (voice, context) cells shows `fall = s_mean - e_mean >= 0`  (falling or
#: flat, never a genuine rise) except tiny end-of-scale noise. An offset of
#: 0.7 (vs. T4's 0.5) means a perfectly flat contour (`fall = 0`) scores 70
#: -- comfortably in accepted territory, since flat is a legitimate
#: half-third realization, not a deficient one -- while a clearly falling
#: contour (`fall >= 0.3`, well within the aligned data's observed range)
#: reaches 100.
HALF_THIRD_FALL_OFFSET = 0.7
HALF_THIRD_FALL_SCALE = 1.0

#: Reject gate: a half-third context does not permit a clear T2-like rise.
#: The aligned controlled evidence draws a clean line here -- every
#: half-third (`plus_t1`/`plus_t2`/`plus_t4`) second-half slope measured at
#: most +0.057 (noise), while every T3+T3 sandhi (`plus_t3`, which routes
#: through the T2 branch entirely and never reaches this function) second-
#: half slope measured at least +0.467. 0.15 sits with >2x margin above the
#: half-third noise ceiling and >3x margin below the sandhi group's floor.
HALF_THIRD_RISE_REJECT_SLOPE = 0.15
#: Ceiling applied when the reject gate fires -- same value and same
#: rationale as Candidate E V1's `T3_INVALID_SHAPE_CEILING`: well below
#: threshold territory and well below any genuine half-third's likely
#: score, so a clear rise cannot pass as a reduced T3 regardless of how
#: the base fall/flat component alone would have scored it.
HALF_THIRD_RISE_CEILING = 20.0


def _score_half_third(seg: np.ndarray) -> float:
    q = max(1, len(seg) // 4)
    s_mean = float(np.mean(seg[:q]))
    e_mean = float(np.mean(seg[-q:]))
    fall = s_mean - e_mean
    base_score = max(0.0, min(1.0, (fall + HALF_THIRD_FALL_OFFSET) / HALF_THIRD_FALL_SCALE)) * 100.0

    _first_half, second_half = _half_split(seg)
    second_half_slope = _linear_slope(second_half)
    if second_half_slope > HALF_THIRD_RISE_REJECT_SLOPE:
        return min(base_score, HALF_THIRD_RISE_CEILING)
    return base_score


# ---------------------------------------------------------------------------
# STEP 2/3/5 -- per-surface-tone routing + max-over-accepted-alternatives
# ---------------------------------------------------------------------------


def _score_for_surface_tone(seg: np.ndarray, surface_tone: int, realization: str) -> tuple[float, str]:
    """One candidate score for one tone in `accepted_surface_tones`.

    T1/T2/T4 always route to Candidate E V1's own unchanged formulas
    (STEP 2: "normal T1/T2/T4 realization"). T3 branches on `realization`:
    `FULL_THIRD` -> E V1's full-dip formula (STEP 2.A); `HALF_THIRD` -> the
    new reduced-shape formula above (STEP 2.B). A surface tone of 3 with
    any other realization label should not occur in practice (the planner
    always assigns FULL_THIRD or HALF_THIRD to a syllable whose accepted
    tone includes 3 -- see `plan_expected_tones` Pass 3), but falls back to
    the full-dip formula rather than silently guessing, since that is
    E V1's own (frozen, already-evaluated) default behaviour.
    """
    if len(seg) < 4:
        return 65.0, "constant_short_segment"
    if surface_tone == 1:
        return _score_t1(seg), "measured"
    if surface_tone == 2:
        return _score_t2(seg), "measured"
    if surface_tone == 4:
        return _score_t4(seg), "measured"
    if surface_tone == 3:
        if realization == HALF_THIRD:
            return _score_half_third(seg), "measured_half_third"
        return _score_t3(seg), "measured_full_third"
    if surface_tone == 5:
        return 75.0, "neutral_not_measured"
    return 0.0, f"unrecognized_surface_tone_{surface_tone}"


def score_segment_e2(seg: np.ndarray, expected: ExpectedTone) -> tuple[float, str, int]:
    """Candidate E2's per-syllable score.

    STEP 3's rule, applied exactly as specified: when
    `expected.accepted_surface_tones` names more than one acceptable
    realization (e.g. `(2, 3)` for an ambiguous T3 chain, or a future case
    with more than one accepted tone), score the observed contour against
    EACH accepted tone and take the MAX -- a learner who genuinely produced
    any accepted realization must not be penalized for not also matching
    the others. This is semantically consistent with `ExpectedTone`'s own
    design: `accepted_surface_tones` is already a tuple specifically
    because "more than one realization can be accepted"
    (tone_context.py:95-98) -- Candidate E2 does not invent that idea, it
    is the first scorer to actually act on it.

    Returns (score, provenance, matched_surface_tone) -- the third element
    records WHICH accepted tone produced the winning score, for
    auditability (STEP 8's routing tests read this directly).
    """
    seg = np.asarray(seg, dtype=float)
    if expected.realization == NEUTRAL:
        return 75.0, "neutral_not_measured", expected.underlying_tone
    if not expected.accepted_surface_tones:
        return 0.0, "no_accepted_surface_tones", expected.underlying_tone

    candidates = [
        (*_score_for_surface_tone(seg, tone, expected.realization), tone)
        for tone in expected.accepted_surface_tones
    ]
    best_score, best_provenance, best_tone = max(candidates, key=lambda c: c[0])
    return best_score, best_provenance, best_tone


# ---------------------------------------------------------------------------
# Top-level entry point -- mirrors Candidate E V1's shape, but consumes a
# list of ExpectedTone (from tone_context.plan_expected_tones) instead of a
# bare tone-integer list.
# ---------------------------------------------------------------------------


def directional_tone_scores_e2(
    pitch_contour: list[tuple[float, float]],
    expected_tones: list[ExpectedTone],
    syllable_windows: list[tuple[int, int]] | None = None,
    onset_skip_fraction: float = 0.0,
) -> tuple[list[float], list[str], list[int]]:
    """Candidate E2's top-level scorer. `onset_skip_fraction` defaults to
    Candidate E V1's own selected value (0%, i.e. no skip) unless a caller
    overrides it -- this module does not re-run STEP 4's ablation; it
    reuses E V1's already-evidenced answer to that question."""
    import chinese_tones

    from benchmarking.candidates.contour_scorer_v2 import apply_onset_skip

    trimmed = apply_onset_skip(pitch_contour, onset_skip_fraction)
    user_pitch = chinese_tones.normalize_pitch_contour(trimmed)
    if len(user_pitch) == 0 or not expected_tones:
        return [], [], []
    user_pitch = chinese_tones._smooth_for_directional_scoring(user_pitch)

    n = len(expected_tones)
    syl_len = max(1, len(user_pitch) // n)
    windows = syllable_windows if syllable_windows and len(syllable_windows) == n else None

    scores: list[float] = []
    provenance: list[str] = []
    matched_tones: list[int] = []
    for i, expected in enumerate(expected_tones):
        start, end = chinese_tones._window_for(i, n, syl_len, len(user_pitch), windows)
        seg = user_pitch[start:end]
        score, source, matched = score_segment_e2(seg, expected)
        scores.append(score)
        provenance.append(source)
        matched_tones.append(matched)
    return scores, provenance, matched_tones


if __name__ == "__main__":
    from benchmarking.candidates import context_aware_contour_scorer_pipeline

    context_aware_contour_scorer_pipeline.run()
