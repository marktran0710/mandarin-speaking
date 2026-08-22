"""Word-level shape+direction verdict, refactor per the tone-verdict spec.

The legacy path collapsed a 50/50 shape+direction blend into a single number
and passed anything >= 58. That let a good pitch shape be vetoed by a coarse
directional heuristic, let a strong start-end direction rescue a broken
overall shape, and let placeholder constants (short-segment=65, neutral=75)
silently pass. This suite pins the new word-level decision rules:

* shape similarity is the primary evidence
* direction is a consistency check, not 50% of the decision
* measurement quality (audio + syllable measurability) gates verdicts before
  scores speak
* CORRECT requires strong shape AND supporting direction
* disagreement (one strong, one weak) resolves to UNCERTAIN, never CORRECT or
  INCORRECT
* INCORRECT requires BOTH shape and direction to be poor
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


# ── Threshold sanity ──────────────────────────────────────────────────────


def test_thresholds_are_ordered_and_finite():
    """Regression guard: collapsing these on each other restores the old
    binary rule, and DIRECTION_BAD must sit below DIRECTION_SUPPORT for the
    disagreement rules to have anywhere to live."""
    assert 0 < SHAPE_WEAK < SHAPE_STRONG <= 100
    assert 0 < DIRECTION_BAD < DIRECTION_SUPPORT <= 100


# ── Case A: shape high, direction high → CORRECT ─────────────────────────


def test_case_a_shape_high_direction_high_is_correct():
    result = decide_word_tone(shape_score=91.0, direction_score=84.0, qc=GOOD_QC)
    assert result.status is DiagnosticStatus.CORRECT
    assert result.reason == "strong_shape_supported"


# ── Case B: shape high, direction low → CORRECT, never INCORRECT ─────────


def test_case_b_shape_high_direction_low_is_correct():
    """Shape is the primary evidence; direction is a consistency check, not
    veto power. A contour that visibly matches the expected tone must not be
    marked INCORRECT — or held to UNCERTAIN — just because a coarse
    directional heuristic disagrees. A genuine tone error would also show up
    as a poor shape match, so strong shape wins."""
    result = decide_word_tone(shape_score=89.0, direction_score=42.0, qc=GOOD_QC)
    assert result.status is DiagnosticStatus.CORRECT
    assert result.status is not DiagnosticStatus.INCORRECT
    assert result.reason == "strong_shape_direction_overridden"


# ── Case C: shape low, direction high → UNCERTAIN (not CORRECT) ──────────


def test_case_c_shape_low_direction_high_is_uncertain():
    """The other direction of the same invariant: a contour whose overall
    shape is poor must not PASS just because its start and end happen to sit
    in the expected direction. UNCERTAIN."""
    result = decide_word_tone(shape_score=45.0, direction_score=90.0, qc=GOOD_QC)
    assert result.status is DiagnosticStatus.UNCERTAIN
    assert result.status is not DiagnosticStatus.CORRECT


# ── Case D: both low → INCORRECT ─────────────────────────────────────────


def test_case_d_both_low_is_incorrect():
    """The only situation where INCORRECT is honest: neither the shape nor
    the direction supports the expected tone."""
    result = decide_word_tone(shape_score=42.0, direction_score=30.0, qc=GOOD_QC)
    assert result.status is DiagnosticStatus.INCORRECT
    assert result.reason == "strong_negative_evidence"


# ── Case E: measurement quality overrides acoustic score ─────────────────


def test_case_e_insufficient_frames_overrides_high_scores():
    """Even a near-perfect calculated score cannot produce CORRECT if the
    underlying measurement was thin. QC is a gate, never a score."""
    thin = QcEvidence(judged=True, pitch_points=3, minimum_pitch_points=8)
    result = decide_word_tone(shape_score=92.0, direction_score=90.0, qc=thin)
    assert result.status is DiagnosticStatus.UNCERTAIN
    assert result.reason == "insufficient_pitch_frames"


def test_unusable_recording_is_invalid_audio_even_with_high_scores():
    unusable = QcEvidence(can_score_pronunciation=False)
    result = decide_word_tone(shape_score=95.0, direction_score=95.0, qc=unusable)
    assert result.status is DiagnosticStatus.INVALID_AUDIO
    assert result.reason == "invalid_audio"


def test_recording_quality_reason_codes_gate_the_word_verdict():
    qc = QcEvidence(reason_codes=("audio_clipping",))
    result = decide_word_tone(shape_score=95.0, direction_score=95.0, qc=qc)
    assert result.status is DiagnosticStatus.INVALID_AUDIO


# ── Display score ────────────────────────────────────────────────────────


def test_display_score_is_shape_weighted_seventy_thirty():
    """display_score = 0.70 * shape + 0.30 * direction. Shape is primary."""
    result = decide_word_tone(shape_score=90.0, direction_score=50.0, qc=GOOD_QC)
    assert result.display_score == pytest.approx(0.70 * 90.0 + 0.30 * 50.0)


def test_display_score_survives_none_inputs_without_crashing():
    """When a component wasn't measured the display should still be
    computable — treat missing as 0 for the display number but let the
    verdict flow through the measurement-quality path."""
    result = decide_word_tone(shape_score=None, direction_score=None, qc=GOOD_QC)
    assert result.display_score == 0.0


# ── Boundary values around SHAPE_STRONG / SHAPE_WEAK / DIRECTION_* ───────


def test_shape_exactly_at_strong_with_supporting_direction_is_correct():
    """Boundary: shape == SHAPE_STRONG (80) with direction at DIRECTION_SUPPORT
    (60) must be inclusive — otherwise a two-decimal round-down flips CORRECT
    into UNCERTAIN."""
    result = decide_word_tone(
        shape_score=SHAPE_STRONG, direction_score=DIRECTION_SUPPORT, qc=GOOD_QC
    )
    assert result.status is DiagnosticStatus.CORRECT


def test_shape_just_below_strong_is_never_correct_alone():
    """Even a very high direction score cannot promote a below-strong shape
    to CORRECT — direction is not the primary evidence."""
    result = decide_word_tone(
        shape_score=SHAPE_STRONG - 0.1, direction_score=99.0, qc=GOOD_QC
    )
    assert result.status is not DiagnosticStatus.CORRECT


def test_shape_below_weak_and_direction_at_bad_bar_is_incorrect():
    """Boundary: direction at exactly DIRECTION_BAD (45) is the edge of the
    'moved wrong way' band; combined with sub-weak shape the verdict must be
    INCORRECT (inclusive). One tick above and it must reset to UNCERTAIN."""
    incorrect = decide_word_tone(
        shape_score=SHAPE_WEAK - 0.1, direction_score=DIRECTION_BAD, qc=GOOD_QC
    )
    assert incorrect.status is DiagnosticStatus.INCORRECT

    uncertain = decide_word_tone(
        shape_score=SHAPE_WEAK - 0.1, direction_score=DIRECTION_BAD + 0.1, qc=GOOD_QC
    )
    assert uncertain.status is DiagnosticStatus.UNCERTAIN


def test_shape_in_middle_band_is_always_uncertain():
    """SHAPE_WEAK <= shape < SHAPE_STRONG — the shape evidence is neither
    strong enough to confirm nor weak enough to condemn. Generated relative
    to the two threshold constants so this stays correct across calibration
    passes rather than pinning to values from the original 60-80 band."""
    midpoint = (SHAPE_WEAK + SHAPE_STRONG) / 2
    for shape in (SHAPE_WEAK, midpoint, SHAPE_STRONG - 0.1):
        for direction in (0.0, 30.0, 60.0, 90.0):
            result = decide_word_tone(
                shape_score=shape, direction_score=direction, qc=GOOD_QC
            )
            assert result.status is DiagnosticStatus.UNCERTAIN, (shape, direction)


# ── Invariants stated in the spec (§15) ──────────────────────────────────


def test_strong_shape_is_never_incorrect_regardless_of_direction():
    """A tone contour that strongly matches the expected shape should not be
    marked INCORRECT solely because a coarse directional heuristic disagrees."""
    for direction in (0.0, 10.0, 30.0, 44.0):
        result = decide_word_tone(shape_score=95.0, direction_score=direction, qc=GOOD_QC)
        assert result.status is not DiagnosticStatus.INCORRECT, direction


def test_direction_alone_never_produces_correct_when_shape_is_poor():
    """A contour that only has the correct start/end direction should not be
    marked CORRECT when its overall shape is poor."""
    for direction in (60.0, 70.0, 90.0, 100.0):
        result = decide_word_tone(shape_score=40.0, direction_score=direction, qc=GOOD_QC)
        assert result.status is not DiagnosticStatus.CORRECT, direction


def test_insufficient_measurement_never_produces_correct():
    """Insufficient measurement must never be interpreted as correct
    pronunciation."""
    thin = QcEvidence(judged=True, pitch_points=2, minimum_pitch_points=8)
    unjudged = QcEvidence(judged=False, pitch_points=40, minimum_pitch_points=8)
    for qc in (thin, unjudged):
        result = decide_word_tone(shape_score=99.0, direction_score=99.0, qc=qc)
        assert result.status is not DiagnosticStatus.CORRECT


# ── Payload shape ────────────────────────────────────────────────────────


def test_verdict_payload_exposes_shape_direction_display_and_reason():
    """The refactor's promise to consumers: shape and direction are surfaced
    separately, alongside the display composite and a reason code."""
    result = decide_word_tone(shape_score=89.0, direction_score=42.0, qc=GOOD_QC)
    payload = result.as_dict()
    assert payload["shape_score"] == 89.0
    assert payload["direction_score"] == 42.0
    assert payload["display_score"] == pytest.approx(0.70 * 89.0 + 0.30 * 42.0)
    assert payload["verdict"] == "CORRECT"
    assert payload["reason"] == "strong_shape_direction_overridden"
    # Reason codes must never claim these engineering thresholds are validated.
    assert payload["threshold_validated"] is False
