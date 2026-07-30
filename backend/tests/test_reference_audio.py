"""Tests for the model-voice reference-audio slicing helpers in
praat_analyzer.py: approximating where a vocabulary word sits inside a
TTS-synthesized sentence recording, and caching its normalized pitch shape.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from praat_analyzer import reference_curve_for_span, slice_reference_word_span


def _flat_contour(start, end, hz=200.0, num_points=60):
    step = (end - start) / (num_points - 1)
    return [(round(start + step * i, 4), hz) for i in range(num_points)]


class TestSliceReferenceWordSpan:
    def test_word_not_in_sentence_returns_none(self):
        contour = _flat_contour(0.0, 1.0)
        assert slice_reference_word_span("我想喝水", "咖啡", contour) is None

    def test_no_pitch_contour_returns_none(self):
        assert slice_reference_word_span("我想喝水", "喝水", []) is None

    def test_word_at_start_gets_an_early_span(self):
        sentence = "我想喝水"
        contour = _flat_contour(0.0, 1.0)
        result = slice_reference_word_span(sentence, "我", contour)
        assert result is not None
        start, end, next_from = result
        assert 0.0 <= start < end <= 1.0
        assert start < 0.4  # first char of 4 should sit in the first quarter
        assert next_from == 1

    def test_word_at_end_gets_a_later_span_than_word_at_start(self):
        sentence = "我想喝水"
        contour = _flat_contour(0.0, 1.0)
        first = slice_reference_word_span(sentence, "我", contour)
        last = slice_reference_word_span(sentence, "水", contour)
        assert first is not None and last is not None
        assert last[0] > first[0]

    def test_search_from_finds_the_second_occurrence(self):
        sentence = "我喜歡咖啡，你也喜歡咖啡。"
        contour = _flat_contour(0.0, 2.0, num_points=120)
        first = slice_reference_word_span(sentence, "咖啡", contour)
        assert first is not None
        second = slice_reference_word_span(sentence, "咖啡", contour, search_from=first[2])
        assert second is not None
        assert second[0] > first[0]

    def test_span_never_exceeds_the_contour_duration(self):
        sentence = "水"
        contour = _flat_contour(0.0, 0.5)
        result = slice_reference_word_span(sentence, "水", contour)
        assert result is not None
        start, end, _ = result
        assert start >= 0.0
        assert end <= 0.5


class TestReferenceCurveForSpan:
    def test_too_few_points_returns_empty(self):
        contour = [(0.0, 200.0)]
        assert reference_curve_for_span(contour, 0.0, 1.0) == []

    def test_returns_a_hundred_point_normalized_curve(self):
        # Rising pitch across the span
        contour = [(t / 10, 150.0 + t * 5) for t in range(11)]
        curve = reference_curve_for_span(contour, 0.0, 1.0)
        assert len(curve) == 100
        assert all(0.0 <= v <= 1.0 for v in curve)
        # Rising contour -> curve should trend upward end vs start
        assert curve[-1] > curve[0]

    def test_only_points_inside_the_span_are_used(self):
        # Flat inside [0, 1], sharp spike just outside — must not leak in.
        inside = [(t / 10, 200.0) for t in range(11)]
        outside_spike = [(1.5, 500.0)]
        curve = reference_curve_for_span(inside + outside_spike, 0.0, 1.0)
        assert len(curve) == 100
        # Flat inside span -> normalize_pitch_contour falls back to 0.5 midline
        assert max(curve) - min(curve) < 0.05
