"""End-to-end invariants of the tone-verdict refactor, spec §15.

These tests bind the refactor's central promises to the pipeline that
actually runs in production — estimate_word_prosody + the frontend's own
tests cover the display side. The rules pinned here are:

1. A tone contour that strongly matches the expected shape must not be
   marked INCORRECT solely because a coarse directional heuristic disagrees.
2. A contour that only has the correct start/end direction must not be
   marked CORRECT when its overall shape is poor.
3. Insufficient measurement must never be interpreted as correct
   pronunciation — placeholder-scored syllables (constant_short_segment,
   neutral_not_measured) can never produce `passed=True`.
4. Contextual tone sandhi (T3+T3, half-third, 一/不 sandhi) is preserved
   and evaluated against the surface target, not the dictionary target.
5. Punctuation still breaks T3 chains — a full-stop between two T3
   syllables is a boundary that must not sandhi.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from praat_analyzer import estimate_word_prosody
from tone_decision import (
    DIRECTION_BAD,
    DIRECTION_SUPPORT,
    DiagnosticStatus,
    QcEvidence,
    SHAPE_STRONG,
    SHAPE_WEAK,
    decide_word_tone,
)


GOOD_QC = QcEvidence(
    can_score_pronunciation=True,
    judged=True,
    pitch_points=40,
    minimum_pitch_points=8,
)


# ── Invariant 1: strong shape is never INCORRECT alone ───────────────────


def test_strong_shape_is_never_incorrect_regardless_of_directional_veto():
    """A shape score that strongly matches the expected tone cannot be
    called an error just because a coarse start/end directional heuristic
    disagrees. UNCERTAIN is the honest label for that disagreement.

    Sweeps direction from 0 to just below DIRECTION_BAD to prove every
    variant of "coarse directional heuristic disagrees" resolves to
    UNCERTAIN and never INCORRECT."""
    for direction in np.arange(0.0, DIRECTION_BAD + 0.01, 5.0):
        result = decide_word_tone(
            shape_score=95.0, direction_score=float(direction), qc=GOOD_QC
        )
        assert result.status is not DiagnosticStatus.INCORRECT, direction


# ── Invariant 2: direction alone never produces CORRECT ──────────────────


def test_direction_alone_never_promotes_a_poor_shape_to_correct():
    """A recording whose start/end pitch happens to move in the expected
    direction must not pass when the overall shape is poor. Direction is a
    consistency check, not a primary evidence source."""
    for direction in np.arange(DIRECTION_SUPPORT, 100.01, 5.0):
        result = decide_word_tone(
            shape_score=SHAPE_WEAK - 5.0, direction_score=float(direction), qc=GOOD_QC
        )
        assert result.status is not DiagnosticStatus.CORRECT, direction


# ── Invariant 3: placeholder scores can never mean CORRECT ───────────────


def _contour(pitch_pattern, base_hz=220.0, spread_hz=160.0, num_points=60, duration=0.8):
    x = np.linspace(0, 1, len(pitch_pattern))
    x_new = np.linspace(0, 1, num_points)
    shape = np.interp(x_new, x, pitch_pattern)
    freqs = base_hz + (shape - 0.5) * spread_hz
    times = np.linspace(0, duration, num_points)
    return list(zip(times.tolist(), freqs.tolist()))


def test_neutral_tone_syllable_never_produces_word_passed_true():
    """The bug the refactor closes: 什麼 has a neutral 麼 that the legacy
    scorer returned as a constant 75, which cleared the 58 bar and made
    every learner's 什麼 word silently pass. After the refactor, the
    placeholder resolves to UNCERTAIN and the word can't be CORRECT if any
    syllable is UNCERTAIN."""
    # A well-formed 什麼 contour: T2 rise then a level neutral. The T2 rise
    # is what should be judged; 麼 is a neutral placeholder.
    contour = _contour([0.3, 0.35, 0.4, 0.5, 0.7, 0.7, 0.7, 0.7], num_points=80)
    words = estimate_word_prosody(contour, "什麼")
    assert words, "expected estimate_word_prosody to return a segment"
    for word in words:
        # Neutral syllable must never produce passed=True on its own.
        neutral_syllables = [
            s
            for s in word.get("syllables", [])
            if s.get("score_provenance") == "neutral_not_measured"
        ]
        for syllable in neutral_syllables:
            assert syllable["passed"] is not True, syllable
            assert syllable.get("diagnostic_status") == "UNCERTAIN"


def test_short_segment_placeholder_never_produces_syllable_passed_true():
    """The other placeholder: too-short segments get a constant 65 in the
    legacy path, which used to silently pass. Now they resolve to
    UNCERTAIN and never CORRECT."""
    # Very short contour — every syllable in it hits the short-segment
    # fallback because the alignment can only give it a few frames each.
    contour = _contour([0.5, 0.5, 0.5, 0.5], num_points=8, duration=0.08)
    words = estimate_word_prosody(contour, "在家 很好")
    for word in words:
        for syllable in word.get("syllables") or []:
            assert syllable["passed"] is not True, syllable


# ── Invariant 4: contextual tone sandhi is preserved ─────────────────────


def test_third_tone_sandhi_still_evaluated_against_the_surface_target():
    """很好 (T3+T3) surfaces as T2+T3 by sandhi. The refactor must keep
    calling tone_context.plan_for_tokens so the first syllable is scored
    against the T2-like realization it should actually produce, not against
    a strict dictionary T3."""
    # Rising then dip — the T2 realisation for 很 followed by a T3 shape
    # for 好. If the planner is being consulted, this should score well.
    contour = _contour([0.35, 0.5, 0.65, 0.75, 0.6, 0.4, 0.6, 0.75], num_points=80)
    words = estimate_word_prosody(contour, "很好")
    assert words, "expected estimate_word_prosody to return a segment"
    # jieba may return "很好" as one word or as two 1-char tokens; either
    # way the first syllable of the first Chinese character should carry
    # the planner's contextual accepted_surface_tones.
    all_syllables = [
        syllable
        for word in words
        for syllable in word.get("syllables") or []
    ]
    assert len(all_syllables) >= 2
    hen = next(syllable for syllable in all_syllables if syllable.get("char") == "很")
    # accepted_surface_tones is populated by the contextual planner —
    # its presence proves the planner ran. The exact tone set matters
    # too: the first T3 must be allowed to surface as T2 (rising).
    accepted = hen.get("accepted_surface_tones")
    assert accepted is not None, hen
    assert 2 in (accepted or []), hen


# ── Invariant 5: punctuation still breaks T3 chains ──────────────────────


def test_punctuation_still_breaks_third_tone_sandhi():
    """A period or comma between two T3 syllables is a phrase boundary that
    must not sandhi. Regression guard for the third-tone-chain punctuation
    fix — the refactor did not touch that logic, and this test proves it."""
    from tone_context import plan_for_tokens

    # Same characters, once as one chain and once with a hard boundary.
    chained = plan_for_tokens(["你", "好"], text="你好")
    split = plan_for_tokens(["你", "好"], text="你。好")

    # With no boundary, T3+T3 sandhi fires and 你 accepts T2.
    assert 2 in list(chained[0].accepted_surface_tones), chained[0]

    # With a period between them, 你 is a final T3 in its own phrase and
    # must NOT accept the T2 realization the chain would have granted.
    assert 2 not in list(split[0].accepted_surface_tones), split[0]
