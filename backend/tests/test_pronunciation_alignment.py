"""Syllable alignment behind the align_utterance interface."""

import pytest

from domain.pronunciation.alignment import EnergyAlignmentStrategy


def _voiced(start, end, hz=200.0, step=0.01):
    count = int(round((end - start) / step))
    return [(round(start + i * step, 4), hz) for i in range(count)]


def test_a_break_in_voicing_places_the_syllable_boundary_there():
    contour = _voiced(0.0, 0.3) + _voiced(0.5, 0.8)
    aligned = EnergyAlignmentStrategy().align(contour, 2)
    assert len(aligned.spans_ms) == 2
    boundary = aligned.spans_ms[0][1]
    assert 300 <= boundary <= 500
    assert aligned.spans_ms[0][1] == aligned.spans_ms[1][0]
    assert aligned.result.fallback_used is False
    assert aligned.result.confidence >= 0.7


def test_spans_cover_the_voiced_region_contiguously():
    contour = _voiced(0.1, 0.4) + _voiced(0.5, 0.8) + _voiced(0.95, 1.3)
    spans = EnergyAlignmentStrategy().align(contour, 3).spans_ms
    assert spans[0][0] == 100
    assert spans[-1][1] == pytest.approx(1290, abs=10)
    assert all(a[1] == b[0] for a, b in zip(spans, spans[1:]))


def test_a_recording_with_no_landmarks_falls_back_and_says_so():
    contour = _voiced(0.0, 1.2)  # one unbroken voiced run, no intensity
    aligned = EnergyAlignmentStrategy().align(contour, 4)
    widths = [end - start for start, end in aligned.spans_ms]
    assert max(widths) - min(widths) <= 2  # equal division
    assert aligned.result.fallback_used is True
    assert aligned.result.confidence < 0.5


def test_a_single_syllable_needs_no_boundaries():
    aligned = EnergyAlignmentStrategy().align(_voiced(0.0, 0.4), 1)
    assert len(aligned.spans_ms) == 1
    assert aligned.result.fallback_used is False


def test_nothing_to_align_returns_no_spans():
    aligned = EnergyAlignmentStrategy().align([], 3)
    assert aligned.spans_ms == ()
    assert aligned.result.confidence == 0.0
