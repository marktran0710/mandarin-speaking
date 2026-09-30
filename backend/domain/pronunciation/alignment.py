"""Place the known syllables on the audio, behind one replaceable interface.

The active strategy wraps the existing landmark aligner
(``domain.speech.acoustics.alignment.EnergyAligner``): the syllable count is
known from the script, so boundaries are chosen at voicing breaks and intensity
valleys. This is *not* forced alignment - there is no acoustic model - which is
why every result carries a confidence, and why a fallback to equal division is
reported rather than hidden. A real forced aligner can later implement
``SyllableAlignmentStrategy`` without anything downstream changing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

from domain.pronunciation.types import AlignmentResult
from domain.speech.acoustics.alignment import (
    EnergyAligner,
    intensity_dip_candidates,
    voicing_gap_candidates,
)

PitchContour = Sequence[tuple[float, float]]  # (seconds, hz), voiced frames only
IntensityContour = Sequence[tuple[float, float]]  # (seconds, dB)

#: A boundary within this many seconds of a voicing break counts as directly supported.
_BREAK_SUPPORT_WINDOW_S = 0.04
_FALLBACK_CONFIDENCE = 0.25
_SINGLE_SYLLABLE_CONFIDENCE = 0.9


@dataclass(frozen=True)
class AlignedSpans:
    #: One contiguous (start_ms, end_ms) per syllable, in script order.
    spans_ms: tuple[tuple[int, int], ...]
    result: AlignmentResult


class SyllableAlignmentStrategy(Protocol):
    def align(
        self,
        pitch_contour: PitchContour,
        syllable_count: int,
        intensity: Optional[IntensityContour] = None,
    ) -> AlignedSpans: ...


def _to_ms(seconds: float) -> int:
    return int(round(seconds * 1000.0))


class EnergyAlignmentStrategy:
    name = "energy_landmarks"

    def __init__(self) -> None:
        self._aligner = EnergyAligner()

    def align(
        self,
        pitch_contour: PitchContour,
        syllable_count: int,
        intensity: Optional[IntensityContour] = None,
    ) -> AlignedSpans:
        spans = self._aligner.align(list(pitch_contour), syllable_count, intensity)
        if not spans:
            return AlignedSpans((), AlignmentResult(self.name, 0.0, True))

        spans_ms = tuple((_to_ms(span.start), _to_ms(span.end)) for span in spans)
        if syllable_count == 1:
            return AlignedSpans(spans_ms, AlignmentResult(self.name, _SINGLE_SYLLABLE_CONFIDENCE, False))

        start, end = spans[0].start, spans[-1].end
        candidates = [time for time, _ in voicing_gap_candidates(pitch_contour)]
        breaks = list(candidates)
        if intensity:
            candidates += [time for time, _ in intensity_dip_candidates(intensity, start, end)]
        boundaries = [span.end for span in spans[:-1]]

        def near(boundary: float, times: Sequence[float]) -> bool:
            return any(abs(boundary - time) <= _BREAK_SUPPORT_WINDOW_S for time in times)

        widths = [span.duration for span in spans]
        equal_division = max(widths) - min(widths) < 1e-6
        usable = sum(1 for time in candidates if start <= time <= end)
        if equal_division and (
            usable < len(boundaries) or not any(near(b, candidates) for b in boundaries)
        ):
            # The aligner found too few landmarks and divided the voiced span
            # evenly; its boundaries are then guesses.
            return AlignedSpans(spans_ms, AlignmentResult(self.name, _FALLBACK_CONFIDENCE, True))

        supported = sum(1 for boundary in boundaries if near(boundary, breaks))
        # Every boundary sits on some landmark; one that coincides with a real
        # break in voicing is better evidenced than one inferred from intensity.
        confidence = 0.5 + 0.5 * supported / len(boundaries)
        return AlignedSpans(spans_ms, AlignmentResult(self.name, round(confidence, 3), False))
