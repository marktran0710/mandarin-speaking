"""The feature schema shared by reference and student recordings.

One schema for both is deliberate: a reference utterance and a student
utterance are extracted by the same pipeline, so comparing them never has to
translate between two shapes. Everything is plain data and JSON round-trippable
so a reference can be cached in the database and reused for every student.

Pitch is always stored as semitones against the speaker's own median (after
octave-error folding), never as Hz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from domain.pronunciation.contour import classify_direction
from domain.pronunciation.policy import DirectionParams

#: Praat pitch frame step used by the acoustic pipeline (10 ms).
FRAME_MS = 10


@dataclass(frozen=True)
class ExpectedSyllable:
    """One syllable of the known script.

    ``accepted_tones`` holds every surface tone that counts as correct here
    (third-tone sandhi, optional neutral tone, 一/不 changes), so a learner
    matching any of them has made no tone error.
    """

    index: int
    hanzi: str
    pinyin: str
    citation_tone: int
    expected_tone: int
    accepted_tones: tuple[int, ...]
    word_index: int
    realization: str = "canonical"

    @property
    def measurable_by_contour(self) -> bool:
        """Neutral tone has no fixed contour to compare against."""
        return 5 not in self.accepted_tones or len(self.accepted_tones) > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "hanzi": self.hanzi,
            "pinyin": self.pinyin,
            "citation_tone": self.citation_tone,
            "expected_tone": self.expected_tone,
            "accepted_tones": list(self.accepted_tones),
            "word_index": self.word_index,
            "realization": self.realization,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExpectedSyllable":
        return cls(
            index=int(data["index"]),
            hanzi=str(data["hanzi"]),
            pinyin=str(data["pinyin"]),
            citation_tone=int(data["citation_tone"]),
            expected_tone=int(data["expected_tone"]),
            accepted_tones=tuple(int(t) for t in data["accepted_tones"]),
            word_index=int(data["word_index"]),
            realization=str(data.get("realization", "canonical")),
        )


@dataclass(frozen=True)
class SyllableFeatures:
    expected: ExpectedSyllable
    start_ms: int
    end_ms: int
    #: (ms from the start of the audio, semitones against the speaker's median).
    f0_points: tuple[tuple[int, float], ...]
    voiced_ratio: float
    #: rise | fall | dip | flat | other | unvoiced
    direction: str
    f0_start: Optional[float]
    f0_mid: Optional[float]
    f0_end: Optional[float]
    #: 0-1 within this utterance; stored for inspection, not used in scoring.
    intensity_mean: Optional[float]

    @property
    def duration_ms(self) -> int:
        return max(self.end_ms - self.start_ms, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected.to_dict(),
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
            "f0_points": [[t, v] for t, v in self.f0_points],
            "voiced_ratio": self.voiced_ratio,
            "direction": self.direction,
            "f0_start": self.f0_start,
            "f0_mid": self.f0_mid,
            "f0_end": self.f0_end,
            "intensity_mean": self.intensity_mean,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SyllableFeatures":
        return cls(
            expected=ExpectedSyllable.from_dict(data["expected"]),
            start_ms=int(data["start_ms"]),
            end_ms=int(data["end_ms"]),
            f0_points=tuple((int(t), float(v)) for t, v in data["f0_points"]),
            voiced_ratio=float(data["voiced_ratio"]),
            direction=str(data["direction"]),
            f0_start=data.get("f0_start"),
            f0_mid=data.get("f0_mid"),
            f0_end=data.get("f0_end"),
            intensity_mean=data.get("intensity_mean"),
        )


@dataclass(frozen=True)
class PauseFeature:
    start_ms: int
    end_ms: int
    #: The pause falls between this syllable and the next.
    after_syllable: int

    @property
    def duration_ms(self) -> int:
        return max(self.end_ms - self.start_ms, 0)


@dataclass(frozen=True)
class AlignmentResult:
    """How the known syllables were placed on the audio."""

    method: str
    #: 0-1. Low when the aligner had to fall back to equal division.
    confidence: float
    fallback_used: bool


@dataclass(frozen=True)
class UtteranceFeatures:
    expected_text: str
    duration_ms: int
    syllables: tuple[SyllableFeatures, ...]
    pauses: tuple[PauseFeature, ...]
    #: Aligned speech time with pauses removed.
    articulation_ms: int
    alignment: AlignmentResult
    #: pipeline_version, praat_version, pitch_tracker, aligner ... for provenance.
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_text": self.expected_text,
            "duration_ms": self.duration_ms,
            "syllables": [s.to_dict() for s in self.syllables],
            "pauses": [
                {"start_ms": p.start_ms, "end_ms": p.end_ms, "after_syllable": p.after_syllable}
                for p in self.pauses
            ],
            "articulation_ms": self.articulation_ms,
            "alignment": {
                "method": self.alignment.method,
                "confidence": self.alignment.confidence,
                "fallback_used": self.alignment.fallback_used,
            },
            "provenance": dict(self.provenance),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UtteranceFeatures":
        alignment = data["alignment"]
        return cls(
            expected_text=str(data["expected_text"]),
            duration_ms=int(data["duration_ms"]),
            syllables=tuple(SyllableFeatures.from_dict(s) for s in data["syllables"]),
            pauses=tuple(
                PauseFeature(int(p["start_ms"]), int(p["end_ms"]), int(p["after_syllable"]))
                for p in data["pauses"]
            ),
            articulation_ms=int(data["articulation_ms"]),
            alignment=AlignmentResult(
                method=str(alignment["method"]),
                confidence=float(alignment["confidence"]),
                fallback_used=bool(alignment["fallback_used"]),
            ),
            provenance=dict(data.get("provenance") or {}),
        )


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def build_syllable_features(
    expected: ExpectedSyllable,
    start_ms: int,
    end_ms: int,
    points: Sequence[tuple[float, float]],
    *,
    intensity_mean: Optional[float],
    direction_params: DirectionParams = DirectionParams(),
) -> SyllableFeatures:
    """Summarise one syllable's voiced pitch points into the stored features."""
    stored = tuple((int(round(t)), round(float(v), 2)) for t, v in points)
    values = [v for _, v in stored]
    duration = max(end_ms - start_ms, 1)
    voiced_ratio = min(1.0, len(stored) / max(1, round(duration / FRAME_MS)))
    direction = classify_direction(values, direction_params)
    if direction == "unvoiced":
        f0_start = f0_mid = f0_end = None
    else:
        count = len(values)
        edge = max(1, count // 5)
        f0_start = round(_mean(values[:edge]), 2)
        f0_end = round(_mean(values[-edge:]), 2)
        f0_mid = round(_mean(values[count // 3 : max(count // 3 + 1, 2 * count // 3)]), 2)
    return SyllableFeatures(
        expected=expected,
        start_ms=int(start_ms),
        end_ms=int(end_ms),
        f0_points=stored,
        voiced_ratio=round(voiced_ratio, 3),
        direction=direction,
        f0_start=f0_start,
        f0_mid=f0_mid,
        f0_end=f0_end,
        intensity_mean=None if intensity_mean is None else round(float(intensity_mean), 3),
    )
