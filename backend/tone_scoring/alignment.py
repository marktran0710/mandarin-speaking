"""Split an utterance's pitch contour into per-syllable time spans.

Why this exists: the previous scorer divided time *uniformly* — words got a
span proportional to their character count, and syllables inside a word got an
equal share of the pitch frames. Real Mandarin syllable durations vary by 2-3x,
so those boundaries land in the wrong place and the tone template is then
compared against the wrong stretch of audio.

Both implementations are kept: ``ProportionalAligner`` preserves the legacy
behaviour, while ``EnergyAligner`` uses the available intensity contour to
place boundaries more faithfully. The active strategy is selected by config.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, Tuple

PitchContour = Sequence[Tuple[float, float]]
IntensityContour = Sequence[Tuple[float, float]]

# A voiced gap longer than this marks a likely stop/pause boundary. Matches the
# threshold the previous onset helper used, so the two agree on what a gap is.
VOICING_GAP_SECONDS = 0.06
# Mandarin syllables below this are implausible; used to stop the segmenter
# from carving a syllable out of a couple of frames.
MIN_SYLLABLE_SECONDS = 0.055
# How strongly to prefer plausible syllable durations over raw boundary
# strength. Set so a genuine voicing gap still outweighs the prior, while a
# cluster of shallow intensity ripples does not.
DURATION_WEIGHT = 1.0


@dataclass(frozen=True)
class SyllableSpan:
    """One syllable's time window, in seconds."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 0.0)

    def frames(self, contour: PitchContour) -> List[Tuple[float, float]]:
        """Pitch frames falling inside this span."""
        return [
            (float(time), float(freq))
            for time, freq in contour
            if self.start <= float(time) <= self.end
        ]


class SyllableAligner(Protocol):
    """Maps a contour plus a known syllable count onto that many spans.

    The syllable count is a hard constraint, not a hint: the transcript is
    known, so the number of syllables is known exactly. Using it turns an
    open-ended segmentation problem into a much easier constrained one.
    """

    name: str

    def align(
        self,
        pitch_contour: PitchContour,
        syllable_count: int,
        intensity: Optional[IntensityContour] = None,
    ) -> List[SyllableSpan]:
        ...


def _bounds(pitch_contour: PitchContour) -> Optional[Tuple[float, float]]:
    if len(pitch_contour) < 2:
        return None
    return float(pitch_contour[0][0]), float(pitch_contour[-1][0])


class ProportionalAligner:
    """Divides the voiced span into equal parts — the previous behaviour.

    Retained deliberately as the ablation control. Comparing against it is the
    only way to attribute a change in agreement to alignment rather than to
    something else changing at the same time.
    """

    name = "proportional"

    def align(
        self,
        pitch_contour: PitchContour,
        syllable_count: int,
        intensity: Optional[IntensityContour] = None,
    ) -> List[SyllableSpan]:
        edges = _bounds(pitch_contour)
        if edges is None or syllable_count < 1:
            return []
        start, end = edges
        step = (end - start) / syllable_count
        return [
            SyllableSpan(start + index * step, start + (index + 1) * step)
            for index in range(syllable_count)
        ]


def voicing_gap_candidates(
    pitch_contour: PitchContour, gap_seconds: float = VOICING_GAP_SECONDS
) -> List[Tuple[float, float]]:
    """Boundary candidates from breaks in voicing, as (time, strength).

    ``extract_pitch`` returns only voiced frames, so a time gap between
    consecutive frames is an unvoiced stretch — a stop consonant, a glottal
    break, or a pause. These are genuine acoustic landmarks rather than
    guesses, so they get the highest strength, scaled by how long the gap is.
    """
    candidates: List[Tuple[float, float]] = []
    for index in range(1, len(pitch_contour)):
        previous = float(pitch_contour[index - 1][0])
        current = float(pitch_contour[index][0])
        gap = current - previous
        if gap > gap_seconds:
            # Midpoint of the unvoiced stretch, weighted by its length.
            candidates.append(((previous + current) / 2.0, 1.0 + min(gap, 0.5)))
    return candidates


def intensity_dip_candidates(
    intensity: IntensityContour, start: float, end: float
) -> List[Tuple[float, float]]:
    """Boundary candidates from intensity minima, as (time, strength).

    Syllable nuclei are intensity peaks, so the valleys between them are where
    boundaries belong. This is what lets the aligner split two syllables that
    run together with no break in voicing — the common case in connected
    speech, and precisely where uniform division goes wrong.

    Strength is the dip's prominence: how far it falls below the surrounding
    peaks. A shallow ripple scores near zero and loses to a real valley.
    """
    points = [
        (float(time), float(value))
        for time, value in intensity
        if start <= float(time) <= end
    ]
    if len(points) < 3:
        return []

    candidates: List[Tuple[float, float]] = []
    for index in range(1, len(points) - 1):
        previous_value = points[index - 1][1]
        value = points[index][1]
        next_value = points[index + 1][1]
        if value > previous_value or value > next_value:
            continue
        # Prominence against the highest neighbouring peak on each side.
        left_peak = max(entry[1] for entry in points[: index + 1])
        right_peak = max(entry[1] for entry in points[index:])
        prominence = min(left_peak, right_peak) - value
        if prominence > 0:
            candidates.append((points[index][0], prominence))
    if not candidates:
        return []
    strongest = max(strength for _, strength in candidates)
    if strongest <= 0:
        return []
    # Normalised below the weakest voicing gap so a real break always wins.
    return [(time, strength / strongest) for time, strength in candidates]


def _duration_plausibility(duration: float, expected: float) -> float:
    """Penalty for a syllable duration far from the utterance's average.

    Mandarin syllable durations genuinely vary, but within roughly half to
    double the mean — not by an order of magnitude. Without this term the
    search happily clusters three boundaries onto adjacent intensity ripples
    and emits a 60 ms syllable beside a 640 ms one, which is not speech.

    A symmetric log-ratio is used so being half as long is penalised exactly
    as much as being twice as long; a plain difference would treat short
    syllables as nearly free.
    """
    if duration <= 0 or expected <= 0:
        return -10.0
    return -abs(math.log(duration / expected))


def _select_boundaries(
    candidates: Sequence[Tuple[float, float]],
    start: float,
    end: float,
    boundary_count: int,
    min_duration: float,
    duration_weight: float = 1.0,
) -> Optional[List[float]]:
    """Choose boundaries maximising acoustic evidence and duration plausibility.

    Dynamic programming over candidate positions, maximising total boundary
    strength plus a duration prior, subject to every resulting syllable being
    at least ``min_duration``. Greedy picking would take two strong candidates
    5 ms apart and produce an impossible syllable; both the hard floor and the
    duration prior have to be applied during the search, not patched up after.

    Returns None when no arrangement satisfies the constraint.
    """
    if boundary_count == 0:
        return []
    usable = sorted(
        (time, strength)
        for time, strength in candidates
        if start + min_duration <= time <= end - min_duration
    )
    if len(usable) < boundary_count:
        return None

    count = len(usable)
    expected = (end - start) / (boundary_count + 1)
    neg = float("-inf")
    # best[k][i]: best total score using k boundaries, the last at index i.
    best = [[neg] * count for _ in range(boundary_count + 1)]
    previous = [[-1] * count for _ in range(boundary_count + 1)]

    def prior(duration: float) -> float:
        return duration_weight * _duration_plausibility(duration, expected)

    for i, (time, strength) in enumerate(usable):
        if time - start >= min_duration:
            best[1][i] = strength + prior(time - start)

    for k in range(2, boundary_count + 1):
        for i, (time, strength) in enumerate(usable):
            for j in range(i):
                if best[k - 1][j] == neg:
                    continue
                span = time - usable[j][0]
                if span < min_duration:
                    continue
                candidate = best[k - 1][j] + strength + prior(span)
                if candidate > best[k][i]:
                    best[k][i] = candidate
                    previous[k][i] = j

    final, score = -1, neg
    for i, (time, _strength) in enumerate(usable):
        if best[boundary_count][i] == neg:
            continue
        tail = end - time
        if tail < min_duration:
            continue
        total = best[boundary_count][i] + prior(tail)
        if total > score:
            score, final = total, i
    if final < 0:
        return None

    chosen: List[float] = []
    index, level = final, boundary_count
    while index >= 0 and level > 0:
        chosen.append(usable[index][0])
        index = previous[level][index]
        level -= 1
    return sorted(chosen)


class EnergyAligner:
    """Places syllable boundaries at real acoustic landmarks.

    Voicing breaks are the strongest evidence; intensity valleys handle
    syllables that run together without one. Falls back to proportional
    division when the audio offers no usable landmark, so a difficult
    recording degrades to the old behaviour rather than to nonsense.
    """

    name = "energy"

    def __init__(
        self,
        gap_seconds: float = VOICING_GAP_SECONDS,
        min_syllable_seconds: float = MIN_SYLLABLE_SECONDS,
        duration_weight: float = DURATION_WEIGHT,
    ) -> None:
        self.gap_seconds = gap_seconds
        self.min_syllable_seconds = min_syllable_seconds
        self.duration_weight = duration_weight
        self._fallback = ProportionalAligner()

    def align(
        self,
        pitch_contour: PitchContour,
        syllable_count: int,
        intensity: Optional[IntensityContour] = None,
    ) -> List[SyllableSpan]:
        edges = _bounds(pitch_contour)
        if edges is None or syllable_count < 1:
            return []
        start, end = edges
        if syllable_count == 1:
            return [SyllableSpan(start, end)]

        total = end - start
        # Never demand a minimum that the recording cannot physically satisfy.
        min_duration = min(
            self.min_syllable_seconds, total / (syllable_count * 2.0)
        )

        candidates = voicing_gap_candidates(pitch_contour, self.gap_seconds)
        if intensity:
            candidates += intensity_dip_candidates(intensity, start, end)

        boundaries = _select_boundaries(
            candidates, start, end, syllable_count - 1, min_duration,
            duration_weight=self.duration_weight,
        )
        if boundaries is None:
            return self._fallback.align(pitch_contour, syllable_count, intensity)

        edges_all = [start, *boundaries, end]
        return [
            SyllableSpan(edges_all[index], edges_all[index + 1])
            for index in range(syllable_count)
        ]


ALIGNERS = {
    ProportionalAligner.name: ProportionalAligner,
    EnergyAligner.name: EnergyAligner,
}


def get_aligner(name: str) -> SyllableAligner:
    """Look up an aligner by name from the supported runtime strategies."""
    try:
        return ALIGNERS[name]()
    except KeyError:
        raise ValueError(
            f"Unknown aligner {name!r}; available: {sorted(ALIGNERS)}"
        ) from None
