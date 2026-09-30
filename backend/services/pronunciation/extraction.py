"""Praat acoustic extraction for one recording against a known script.

Reference and student recordings both go through this one function, so the two
feature sets are comparable by construction. It reuses the project's validated
Praat helpers (``domain.speech.acoustics.audio_features``: the speaker-adaptive
two-pass pitch tracker, intensity contour and pause segmentation) and the
landmark aligner, and adds nothing acoustic of its own beyond expressing pitch
relative to the speaker's median after folding octave-tracker errors.

What it measures: pitch contour per syllable, syllable timing, pauses and
relative intensity. What it does not: whether each consonant or vowel was
pronounced correctly.
"""

from __future__ import annotations

from typing import Optional, Sequence

from domain.pronunciation.alignment import EnergyAlignmentStrategy, SyllableAlignmentStrategy
from domain.pronunciation.contour import fold_octave_blocks, hz_to_relative_semitones
from domain.pronunciation.policy import DirectionParams
from domain.pronunciation.types import (
    ExpectedSyllable,
    PauseFeature,
    UtteranceFeatures,
    build_syllable_features,
)
from domain.speech.acoustics import audio_features
from services.pronunciation.script import build_expected_syllables

PIPELINE_VERSION = "pronunciation-features-v1"
PITCH_TRACKER = "two_pass_adaptive"
PITCH_STEP_MS = 10

#: Fewer voiced frames than this cannot support any contour.
MIN_VOICED_FRAMES = 10


class FeatureExtractionError(Exception):
    """A recording could not be turned into features; ``code`` is a stable reason."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0


def _relative_semitones(pitch_contour: Sequence[tuple[float, float]]) -> list[float]:
    """Octave-folded semitones re-centred on the speaker's own median."""
    folded = fold_octave_blocks(hz_to_relative_semitones([hz for _, hz in pitch_contour]))
    centre = _median(folded)
    return [value - centre for value in folded]


def _normalised_intensity(
    intensity: Sequence[tuple[float, float]], start_s: float, end_s: float
) -> Optional[float]:
    inside = [db for t, db in intensity if start_s <= t <= end_s]
    if not intensity or not inside:
        return None
    low = min(db for _, db in intensity)
    high = max(db for _, db in intensity)
    if high - low < 1e-6:
        return None
    return min(1.0, max(0.0, (sum(inside) / len(inside) - low) / (high - low)))


def _pauses(raw: Sequence[dict], spans_ms: Sequence[tuple[int, int]]) -> tuple[PauseFeature, ...]:
    """Pauses between syllables, each attached to the nearest syllable boundary."""
    if len(spans_ms) < 2:
        return ()
    boundaries = [end for _, end in spans_ms[:-1]]
    first_start, last_end = spans_ms[0][0], spans_ms[-1][1]
    pauses = []
    for pause in raw:
        start, end = int(round(pause["start"] * 1000)), int(round(pause["end"] * 1000))
        if start < first_start or end > last_end:
            continue  # leading/trailing silence is not a pause inside the sentence
        middle = (start + end) / 2.0
        gap = min(range(len(boundaries)), key=lambda i: abs(boundaries[i] - middle))
        pauses.append(PauseFeature(start_ms=start, end_ms=end, after_syllable=gap))
    return tuple(pauses)


def extract_utterance_features(
    audio_path: str,
    expected_text: str,
    *,
    expected: Optional[Sequence[ExpectedSyllable]] = None,
    aligner: Optional[SyllableAlignmentStrategy] = None,
    direction_params: DirectionParams = DirectionParams(),
) -> UtteranceFeatures:
    syllables = tuple(expected) if expected is not None else build_expected_syllables(expected_text)
    if not syllables:
        raise FeatureExtractionError("no_syllables", "The script has no Chinese syllables to align.")

    aligner = aligner or EnergyAlignmentStrategy()
    try:
        sound = audio_features._load_sound(audio_path)
        duration_ms = int(round(sound.get_total_duration() * 1000))
        pitch_contour = audio_features.extract_pitch_two_pass(audio_path)
        intensity = audio_features._intensity_contour_from_sound(sound)
        raw_pauses = audio_features.analyze_pauses_and_utterances(
            audio_path, _preloaded_sound=sound
        )["pauses"]
    except (RuntimeError, OSError) as exc:
        raise FeatureExtractionError("audio_unreadable", str(exc)) from exc

    if len(pitch_contour) < MIN_VOICED_FRAMES:
        raise FeatureExtractionError("no_voiced_speech", "There is not enough voiced speech to measure.")

    semitones = _relative_semitones(pitch_contour)
    aligned = aligner.align(pitch_contour, len(syllables), intensity)
    if len(aligned.spans_ms) != len(syllables):
        raise FeatureExtractionError("alignment_failed", "The syllables could not be placed on the audio.")

    frames_ms = [(int(round(t * 1000)), value) for (t, _), value in zip(pitch_contour, semitones)]
    built = []
    last = len(syllables) - 1
    for index, (expected_syllable, (start_ms, end_ms)) in enumerate(zip(syllables, aligned.spans_ms)):
        points = [
            (t, value) for t, value in frames_ms
            if start_ms <= t < end_ms or (index == last and t == end_ms)
        ]
        built.append(
            build_syllable_features(
                expected_syllable, start_ms, end_ms, points,
                intensity_mean=_normalised_intensity(intensity, start_ms / 1000.0, end_ms / 1000.0),
                direction_params=direction_params,
            )
        )

    pauses = _pauses(raw_pauses, aligned.spans_ms)
    spoken_ms = aligned.spans_ms[-1][1] - aligned.spans_ms[0][0]
    articulation_ms = max(1, spoken_ms - sum(p.duration_ms for p in pauses))

    parselmouth = audio_features.parselmouth
    return UtteranceFeatures(
        expected_text=expected_text,
        duration_ms=duration_ms,
        syllables=tuple(built),
        pauses=pauses,
        articulation_ms=articulation_ms,
        alignment=aligned.result,
        provenance={
            "pipeline_version": PIPELINE_VERSION,
            "praat_version": str(getattr(parselmouth, "PRAAT_VERSION", "") or getattr(parselmouth, "__version__", "unknown")),
            "pitch_tracker": PITCH_TRACKER,
            "pitch_step_ms": PITCH_STEP_MS,
            "octave_fold": "viterbi-v1",
            "aligner": aligned.result.method,
        },
    )
