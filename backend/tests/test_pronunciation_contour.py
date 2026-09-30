"""Pitch-contour maths: speaker-relative semitones, octave folding, direction
and the shape x size word similarity (Python port of the frontend's v2)."""

import math

import pytest

from domain.pronunciation.contour import (
    classify_direction,
    compare_word_contours,
    fold_octave_blocks,
    hz_to_relative_semitones,
    robust_span,
)
from domain.pronunciation.policy import ContourSimilarityParams


def _shape(kind: str, n: int = 30) -> list[float]:
    """Canonical tone shapes in semitones, deterministic."""
    xs = [i / (n - 1) for i in range(n)]
    if kind == "fall":
        return [4.0 - 8.0 * x for x in xs]
    if kind == "rise":
        return [-3.0 + 6.0 * x for x in xs]
    if kind == "dip":
        return [-4.0 * math.sin(math.pi * x) for x in xs]
    if kind == "flat":
        return [0.0 for _ in xs]
    raise ValueError(kind)


def _points(values: list[float], start_ms: float = 0.0, step_ms: float = 10.0):
    return [(start_ms + i * step_ms, v) for i, v in enumerate(values)]


def _span(values: list[float], step_ms: float = 10.0) -> tuple[float, float]:
    return (0.0, (len(values) - 1) * step_ms)


def _similarity(student: list[float], reference: list[float], params=None):
    return compare_word_contours(
        _points(student), _span(student), _points(reference), _span(reference),
        params or ContourSimilarityParams(),
    )


# ── semitones ─────────────────────────────────────────────────────────────

def test_relative_semitones_are_centred_on_the_speakers_median():
    st = hz_to_relative_semitones([100.0, 200.0, 400.0])
    assert st == pytest.approx([-12.0, 0.0, 12.0])


def test_different_voice_ranges_give_identical_relative_contours():
    low_voice = [110.0, 100.0, 90.0, 100.0, 120.0]
    high_voice = [f * 2.3 for f in low_voice]
    assert hz_to_relative_semitones(low_voice) == pytest.approx(
        hz_to_relative_semitones(high_voice)
    )


def test_relative_semitones_of_nothing_is_empty():
    assert hz_to_relative_semitones([]) == []


# ── octave folding ────────────────────────────────────────────────────────

def test_a_held_octave_error_block_is_folded_back():
    clean = [0.0, 0.3, 0.6, 0.9, 1.2, 1.5, 1.8, 2.1, 2.4, 2.7]
    broken = clean[:4] + [v + 12 for v in clean[4:7]] + clean[7:]
    folded = fold_octave_blocks(broken)
    # Only the shape matters: compare after removing any constant offset.
    offset = folded[0] - clean[0]
    assert [v - offset for v in folded] == pytest.approx(clean, abs=1e-6)


def test_a_genuine_syllable_reset_smaller_than_an_octave_is_kept():
    values = [4.0, 2.0, 0.0, -2.0, -4.0, 3.0, 1.0, -1.0, -3.0, -5.0]  # two falls
    assert fold_octave_blocks(values) == pytest.approx(values)


# ── direction ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["fall", "rise", "dip", "flat"])
def test_canonical_shapes_are_classified_as_themselves(kind):
    assert classify_direction(_shape(kind)) == kind


def test_too_few_voiced_points_is_unvoiced_not_a_guess():
    assert classify_direction([1.0, 2.0]) == "unvoiced"


# ── similarity ────────────────────────────────────────────────────────────

def test_a_contour_matches_itself_almost_perfectly():
    result = _similarity(_shape("fall"), _shape("fall"))
    assert result.score > 0.97


def test_flat_attempt_at_a_falling_tone_scores_far_below_a_correct_one():
    flat_attempt = [0.05 * math.sin(i) for i in range(30)]
    result = _similarity(flat_attempt, _shape("fall"))
    assert result.score < 0.2


def test_wrong_direction_scores_below_flat_and_correct():
    correct = _similarity(_shape("fall"), _shape("fall")).score
    wrong = _similarity(_shape("rise"), _shape("fall")).score
    assert correct > 0.9
    assert wrong < 0.1


def test_a_half_size_attempt_loses_credit_but_keeps_some():
    half = [v * 0.5 for v in _shape("fall")]
    full = _similarity(_shape("fall"), _shape("fall")).score
    partial = _similarity(half, _shape("fall")).score
    assert 0.3 < partial < full


def test_moving_more_than_the_model_is_not_penalised():
    wide = [v * 1.6 for v in _shape("fall")]
    assert _similarity(wide, _shape("fall")).score > 0.97


def test_a_constant_pitch_offset_does_not_change_the_score():
    shifted = [v + 7.0 for v in _shape("dip")]
    base = _similarity(_shape("dip"), _shape("dip")).score
    assert _similarity(shifted, _shape("dip")).score == pytest.approx(base)


def test_score_does_not_depend_on_syllable_speed():
    quick = _shape("fall", n=15)
    slow = _shape("fall", n=45)
    result = compare_word_contours(
        _points(quick), _span(quick), _points(slow), _span(slow), ContourSimilarityParams()
    )
    assert result.score > 0.95


def test_level_reference_is_scored_on_how_level_the_student_stayed():
    level = _similarity([0.2 * math.sin(i) for i in range(30)], _shape("flat"))
    moving = _similarity(_shape("rise"), _shape("flat"))
    assert level.flat_reference and level.score > 0.95
    assert moving.flat_reference and moving.score < 0.1


def test_too_little_voiced_data_is_not_scored():
    sparse = [(0.0, 0.0), (10.0, 0.5), (400.0, 1.0)]  # long unvoiced gap
    result = compare_word_contours(
        sparse, (0.0, 400.0), _points(_shape("fall")), _span(_shape("fall")),
        ContourSimilarityParams(),
    )
    assert result is None


def test_robust_span_ignores_one_stray_sample():
    values = [0.0] * 20 + [50.0] + [1.0] * 20
    assert robust_span(values) < 3.0
