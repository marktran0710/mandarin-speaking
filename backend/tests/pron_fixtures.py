"""Synthetic utterances for pronunciation tests: no audio, fully deterministic."""

from __future__ import annotations

import math
from typing import Mapping, Optional, Sequence

from domain.pronunciation.types import (
    AlignmentResult,
    ExpectedSyllable,
    PauseFeature,
    UtteranceFeatures,
    build_syllable_features,
)

STEP_MS = 10
_HANZI = "友美妳這個週末要做什麼"
_TONE_OF = {"fall": 4, "rise": 2, "dip": 3, "flat": 1, "neutral": 5, "wide_dip": 3}


def shape_values(kind: str, n: int) -> list[float]:
    """Canonical tone shapes in semitones."""
    xs = [i / max(n - 1, 1) for i in range(n)]
    if kind == "fall":
        return [4.0 - 8.0 * x for x in xs]
    if kind == "rise":
        return [-3.0 + 6.0 * x for x in xs]
    if kind == "dip":
        return [-4.0 * math.sin(math.pi * x) for x in xs]
    if kind == "wide_dip":  # same direction as "dip", different shape (flat-bottomed)
        return [-4.0 * min(1.0, 3.0 * math.sin(math.pi * x)) for x in xs]
    if kind in ("flat", "neutral"):
        return [0.15 * math.sin(3.0 * i) for i in range(n)]
    raise ValueError(kind)


def make_utterance(
    shapes: Sequence[str],
    words: Optional[Sequence[int]] = None,
    *,
    syllable_ms: int = 300,
    durations: Optional[Sequence[int]] = None,
    offset_st: float = 0.0,
    scale: float = 1.0,
    pauses_after: Optional[Mapping[int, int]] = None,
    text: Optional[str] = None,
    alignment_confidence: float = 0.9,
) -> UtteranceFeatures:
    """One utterance whose syllables follow the named tone shapes."""
    pauses_after = dict(pauses_after or {})
    words = list(words) if words is not None else list(range(len(shapes)))
    hanzi = text if text is not None else _HANZI[: len(shapes)]
    syllables = []
    pauses = []
    clock = 0
    for index, kind in enumerate(shapes):
        length = durations[index] if durations else syllable_ms
        tone = _TONE_OF[kind]
        expected = ExpectedSyllable(
            index=index, hanzi=hanzi[index], pinyin=f"x{tone}", citation_tone=tone,
            expected_tone=tone, accepted_tones=(tone,), word_index=words[index],
        )
        count = length // STEP_MS
        values = [v * scale + offset_st for v in shape_values(kind, count)]
        points = [(clock + i * STEP_MS, value) for i, value in enumerate(values)]
        syllables.append(
            build_syllable_features(expected, clock, clock + length, points, intensity_mean=0.7)
        )
        clock += length
        if index in pauses_after:
            pauses.append(PauseFeature(start_ms=clock, end_ms=clock + pauses_after[index], after_syllable=index))
            clock += pauses_after[index]
    return UtteranceFeatures(
        expected_text=hanzi,
        duration_ms=clock + 200,
        syllables=tuple(syllables),
        pauses=tuple(pauses),
        articulation_ms=clock - sum(p.end_ms - p.start_ms for p in pauses),
        alignment=AlignmentResult(method="test", confidence=alignment_confidence, fallback_used=False),
        provenance={"pipeline_version": "test"},
    )
