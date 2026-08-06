"""Unit tests for syllable alignment.

Alignment is the foundation of every downstream tone feature: if a boundary
lands in the wrong place, the tone template is compared against the wrong
audio. These tests use synthetic contours with known boundaries so a
regression is caught here rather than surfacing as an unexplained drop in
benchmark agreement.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tone_scoring.alignment import (
    EnergyAligner,
    ProportionalAligner,
    SyllableSpan,
    get_aligner,
    intensity_dip_candidates,
    voicing_gap_candidates,
)


def contour(start=0.0, end=1.0, step=0.01, gaps=()):
    """Voiced frames from start to end, omitting frames inside `gaps`."""
    points = []
    time = start
    while time <= end + 1e-9:
        if not any(low <= time <= high for low, high in gaps):
            points.append((round(time, 5), 200.0))
        time += step
    return points


class TestProportionalAligner:
    def test_divides_the_voiced_span_equally(self):
        spans = ProportionalAligner().align(contour(0.0, 1.0), 4)
        assert len(spans) == 4
        assert spans[0].start == pytest.approx(0.0)
        assert spans[-1].end == pytest.approx(1.0)
        for span in spans:
            assert span.duration == pytest.approx(0.25)

    def test_returns_nothing_for_an_unusable_contour(self):
        assert ProportionalAligner().align([(0.0, 200.0)], 3) == []
        assert ProportionalAligner().align(contour(), 0) == []


class TestVoicingGapCandidates:
    def test_finds_a_gap_and_weights_it_by_length(self):
        points = contour(0.0, 1.0, gaps=[(0.40, 0.50)])
        found = voicing_gap_candidates(points)
        assert len(found) == 1
        time, strength = found[0]
        assert 0.38 <= time <= 0.52
        assert strength > 1.0

    def test_ignores_gaps_shorter_than_the_threshold(self):
        points = contour(0.0, 1.0, gaps=[(0.40, 0.41)])
        assert voicing_gap_candidates(points) == []


class TestIntensityDipCandidates:
    def test_finds_the_valley_between_two_nuclei(self):
        intensity = [
            (0.0, 60.0), (0.1, 75.0), (0.2, 70.0),
            (0.3, 50.0),                      # the valley
            (0.4, 72.0), (0.5, 76.0), (0.6, 62.0),
        ]
        found = intensity_dip_candidates(intensity, 0.0, 0.6)
        assert found, "expected a dip candidate"
        assert min(found, key=lambda c: abs(c[0] - 0.3))[0] == pytest.approx(0.3)

    def test_a_deeper_valley_outranks_a_shallow_ripple(self):
        intensity = [
            (0.0, 70.0), (0.1, 68.0), (0.2, 72.0),   # shallow ripple at 0.1
            (0.3, 40.0),                              # deep valley
            (0.4, 74.0), (0.5, 70.0),
        ]
        found = dict(intensity_dip_candidates(intensity, 0.0, 0.5))
        assert found[0.3] > found.get(0.1, 0.0)

    def test_returns_nothing_when_there_is_no_intensity_data(self):
        assert intensity_dip_candidates([], 0.0, 1.0) == []


class TestEnergyAligner:
    def test_places_a_boundary_at_a_real_voicing_gap(self):
        """The whole point: a boundary should land on acoustic evidence, not
        at the midpoint a uniform split would have chosen."""
        points = contour(0.0, 1.0, gaps=[(0.28, 0.36)])
        spans = EnergyAligner().align(points, 2)
        assert len(spans) == 2
        assert spans[0].end == pytest.approx(0.32, abs=0.05)
        # A proportional split would have put it at 0.5.
        assert abs(spans[0].end - 0.5) > 0.1

    def test_uses_intensity_valleys_when_voicing_never_breaks(self):
        """Connected speech often has no gap between syllables — this is the
        case uniform division gets most wrong."""
        points = contour(0.0, 0.6)
        intensity = [
            (0.0, 60.0), (0.05, 74.0), (0.10, 76.0), (0.15, 70.0),
            (0.20, 45.0),                                   # valley
            (0.25, 70.0), (0.30, 78.0), (0.35, 74.0), (0.40, 66.0),
            (0.50, 64.0), (0.60, 60.0),
        ]
        spans = EnergyAligner().align(points, 2, intensity=intensity)
        assert spans[0].end == pytest.approx(0.20, abs=0.05)

    def test_never_creates_an_implausibly_short_syllable(self):
        """Two strong candidates milliseconds apart must not both be taken."""
        points = contour(0.0, 1.0, gaps=[(0.50, 0.57), (0.58, 0.65)])
        spans = EnergyAligner().align(points, 3)
        assert len(spans) == 3
        for span in spans:
            assert span.duration > 0.02

    def test_falls_back_to_proportional_when_there_is_no_landmark(self):
        """A featureless contour must degrade to the old behaviour rather than
        to nonsense: no evidence is not the same as bad evidence."""
        points = contour(0.0, 1.0)
        spans = EnergyAligner().align(points, 4)
        assert len(spans) == 4
        assert spans[0].duration == pytest.approx(0.25, abs=0.01)

    def test_spans_tile_the_utterance_without_gaps_or_overlap(self):
        points = contour(0.0, 1.2, gaps=[(0.3, 0.37), (0.7, 0.78)])
        spans = EnergyAligner().align(points, 3)
        assert spans[0].start == pytest.approx(0.0)
        assert spans[-1].end == pytest.approx(1.2, abs=0.01)
        for earlier, later in zip(spans, spans[1:]):
            assert earlier.end == pytest.approx(later.start)

    def test_a_single_syllable_is_the_whole_span(self):
        spans = EnergyAligner().align(contour(0.0, 0.5), 1)
        assert spans == [SyllableSpan(0.0, 0.5)]

    def test_produces_exactly_the_requested_syllable_count(self):
        """The transcript is known, so the count is a hard constraint."""
        points = contour(0.0, 2.0, gaps=[(0.4, 0.47), (0.9, 0.97), (1.4, 1.47)])
        for count in (2, 3, 4, 5):
            assert len(EnergyAligner().align(points, count)) == count


class TestSyllableSpan:
    def test_frames_selects_only_pitch_inside_the_span(self):
        points = [(0.0, 100.0), (0.1, 110.0), (0.2, 120.0), (0.3, 130.0)]
        assert SyllableSpan(0.1, 0.2).frames(points) == [(0.1, 110.0), (0.2, 120.0)]


class TestRegistry:
    def test_looks_up_each_aligner_by_name(self):
        assert get_aligner("proportional").name == "proportional"
        assert get_aligner("energy").name == "energy"

    def test_rejects_an_unknown_name_instead_of_silently_defaulting(self):
        """A typo in config must fail loudly, not quietly score everything with
        the wrong aligner and invalidate a benchmark run."""
        with pytest.raises(ValueError, match="Unknown aligner"):
            get_aligner("nope")
