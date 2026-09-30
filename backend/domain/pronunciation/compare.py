"""Student-vs-reference comparison: measured evidence, no score.

Everything here is what the recordings *show*. Turning it into a number is the
scoring policy's job (``scoring.py``), and explaining it to a student is the
feedback layer's job - keeping the three apart is what lets a stored evaluation
answer "why 84 and not 90" from measurements alone.

The reference is a teacher recording, not ground truth for every feature: issues
are only as strong as the reference and the alignment behind them, which is what
each syllable's ``evidence`` records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from domain.pronunciation.contour import ContourSimilarity, compare_word_contours
from domain.pronunciation.policy import PronunciationScoringPolicy
from domain.pronunciation.types import SyllableFeatures, UtteranceFeatures

FLAG_TOO_FLAT = "tone_contour_too_flat"
FLAG_NOT_LEVEL = "tone_contour_not_level"
FLAG_DIRECTION = "tone_direction_mismatch"
FLAG_NARROW = "tone_range_too_narrow"
FLAG_SHORT = "syllable_too_short"
FLAG_LONG = "syllable_too_long"

EVIDENCE_STRONG = "strong"
EVIDENCE_MODERATE = "moderate"
EVIDENCE_WEAK = "weak"
_EVIDENCE_LEVELS = (EVIDENCE_STRONG, EVIDENCE_MODERATE, EVIDENCE_WEAK)

#: Which pitch directions each tone is realised with. Tone 3 is commonly a low
#: fall or low level ("half third") outside phrase-final position.
_TONE_DIRECTIONS = {1: {"flat"}, 2: {"rise"}, 3: {"dip", "fall", "flat"}, 4: {"fall"}}


class ReferenceMismatchError(ValueError):
    """The reference recording is not of the same script as the student's."""


@dataclass(frozen=True)
class SyllableComparison:
    index: int
    hanzi: str
    pinyin: str
    expected_tone: int
    word_index: int
    judged: bool
    tone_similarity: Optional[float]
    reference_direction: str
    student_direction: str
    #: Student share of utterance time over the reference's (speed-normalised).
    duration_ratio: Optional[float]
    evidence: str
    flags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "hanzi": self.hanzi,
            "pinyin": self.pinyin,
            "expected_tone": self.expected_tone,
            "word_index": self.word_index,
            "judged": self.judged,
            "tone_similarity": self.tone_similarity,
            "reference_direction": self.reference_direction,
            "student_direction": self.student_direction,
            "duration_ratio": self.duration_ratio,
            "evidence": self.evidence,
            "flags": list(self.flags),
        }


@dataclass(frozen=True)
class WordComparison:
    word_index: int
    text: str
    syllable_indices: tuple[int, ...]
    judged: bool
    tone_similarity: Optional[float]
    shape: Optional[float]
    range: Optional[float]
    flat_reference: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "word_index": self.word_index,
            "text": self.text,
            "syllable_indices": list(self.syllable_indices),
            "judged": self.judged,
            "tone_similarity": self.tone_similarity,
            "shape": self.shape,
            "range": self.range,
            "flat_reference": self.flat_reference,
        }


@dataclass(frozen=True)
class UtteranceComparison:
    words: tuple[WordComparison, ...]
    syllables: tuple[SyllableComparison, ...]
    tone_similarity: Optional[float]
    judged_words: int
    total_words: int
    rhythm_similarity: Optional[float]
    duration_similarity: Optional[float]
    pause_similarity: Optional[float]
    #: Student syllables per second over the reference's.
    speaking_rate_ratio: Optional[float]
    student_articulation_rate: float
    alignment_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tone_similarity": self.tone_similarity,
            "rhythm_similarity": self.rhythm_similarity,
            "duration_similarity": self.duration_similarity,
            "pause_similarity": self.pause_similarity,
            "speaking_rate_ratio": self.speaking_rate_ratio,
            "student_articulation_rate": self.student_articulation_rate,
            "alignment_confidence": self.alignment_confidence,
            "judged_words": self.judged_words,
            "total_words": self.total_words,
            "words": [w.to_dict() for w in self.words],
            "syllables": [s.to_dict() for s in self.syllables],
        }


def _require_same_script(student: UtteranceFeatures, reference: UtteranceFeatures) -> None:
    student_text = [s.expected.hanzi for s in student.syllables]
    reference_text = [s.expected.hanzi for s in reference.syllables]
    if student_text != reference_text:
        raise ReferenceMismatchError(
            "Reference and student recordings are not of the same syllable sequence."
        )


def _points(syllables: list[SyllableFeatures]) -> list[tuple[float, float]]:
    return [(float(t), v) for syllable in syllables for t, v in syllable.f0_points]


def _span(syllables: list[SyllableFeatures]) -> tuple[float, float]:
    return float(syllables[0].start_ms), float(syllables[-1].end_ms)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _group_by_word(syllables: tuple[SyllableFeatures, ...]) -> dict[int, list[SyllableFeatures]]:
    groups: dict[int, list[SyllableFeatures]] = {}
    for syllable in syllables:
        groups.setdefault(syllable.expected.word_index, []).append(syllable)
    return groups


def _reference_direction_is_plausible(reference: SyllableFeatures) -> bool:
    accepted = [t for t in reference.expected.accepted_tones if t != 5]
    if not accepted:
        return False
    return any(reference.direction in _TONE_DIRECTIONS.get(tone, set()) for tone in accepted)


def _evidence(
    student: SyllableFeatures,
    reference: SyllableFeatures,
    word_size: int,
    alignment_confidence: float,
    policy: PronunciationScoringPolicy,
) -> str:
    """How much a flag on this syllable can be trusted.

    Short words are the most reliable to compare (per-word agreement with
    raters falls as words get longer); an odd-looking reference or a shaky
    alignment weakens any claim regardless.
    """
    flags = policy.flags
    if alignment_confidence < flags.low_alignment_confidence:
        return EVIDENCE_WEAK
    if not _reference_direction_is_plausible(reference):
        return EVIDENCE_WEAK
    level = 0 if word_size == 1 else 1 if word_size == 2 else 2
    if min(student.voiced_ratio, reference.voiced_ratio) < flags.min_voiced_ratio:
        level += 1
    return _EVIDENCE_LEVELS[min(level, len(_EVIDENCE_LEVELS) - 1)]


def _contour_flags(
    student: SyllableFeatures,
    reference: SyllableFeatures,
    similarity: ContourSimilarity,
    policy: PronunciationScoringPolicy,
) -> list[str]:
    if similarity.score >= policy.flags.similarity_max:
        return []
    ref_dir, stu_dir = reference.direction, student.direction
    if ref_dir == "flat":
        return [FLAG_NOT_LEVEL] if stu_dir not in ("flat", "unvoiced") else []
    if ref_dir in ("unvoiced", "other"):
        return []
    if stu_dir == "flat":
        return [FLAG_TOO_FLAT]
    if stu_dir == ref_dir:
        return [FLAG_NARROW] if similarity.range < policy.flags.narrow_range_factor else []
    if stu_dir != "unvoiced":
        return [FLAG_DIRECTION]
    return []


def _compare_syllable(
    student: SyllableFeatures,
    reference: SyllableFeatures,
    word_size: int,
    duration_ratio: Optional[float],
    alignment_confidence: float,
    policy: PronunciationScoringPolicy,
) -> SyllableComparison:
    expected = reference.expected
    similarity: Optional[ContourSimilarity] = None
    if expected.measurable_by_contour:
        similarity = compare_word_contours(
            [(float(t), v) for t, v in student.f0_points],
            (float(student.start_ms), float(student.end_ms)),
            [(float(t), v) for t, v in reference.f0_points],
            (float(reference.start_ms), float(reference.end_ms)),
            policy.similarity,
        )

    flags: list[str] = []
    if similarity is not None:
        flags.extend(_contour_flags(student, reference, similarity, policy))
    if duration_ratio is not None:
        if duration_ratio < policy.flags.short_ratio:
            flags.append(FLAG_SHORT)
        elif duration_ratio > policy.flags.long_ratio:
            flags.append(FLAG_LONG)

    judged = similarity is not None
    return SyllableComparison(
        index=expected.index,
        hanzi=expected.hanzi,
        pinyin=expected.pinyin,
        expected_tone=expected.expected_tone,
        word_index=expected.word_index,
        judged=judged,
        tone_similarity=None if similarity is None else round(similarity.score, 4),
        reference_direction=reference.direction,
        student_direction=student.direction,
        duration_ratio=None if duration_ratio is None else round(duration_ratio, 4),
        evidence=(
            _evidence(student, reference, word_size, alignment_confidence, policy)
            if judged or flags
            else EVIDENCE_WEAK
        ),
        flags=tuple(flags),
    )


def _compare_words(
    student: UtteranceFeatures,
    reference: UtteranceFeatures,
    policy: PronunciationScoringPolicy,
) -> list[WordComparison]:
    student_words = _group_by_word(student.syllables)
    reference_words = _group_by_word(reference.syllables)
    words: list[WordComparison] = []
    for word_index in sorted(reference_words):
        ref_syllables = reference_words[word_index]
        stu_syllables = student_words[word_index]
        indices = tuple(s.expected.index for s in ref_syllables)
        text = "".join(s.expected.hanzi for s in ref_syllables)
        similarity = None
        if any(s.expected.measurable_by_contour for s in ref_syllables):
            similarity = compare_word_contours(
                _points(stu_syllables), _span(stu_syllables),
                _points(ref_syllables), _span(ref_syllables),
                policy.similarity,
            )
        words.append(
            WordComparison(
                word_index=word_index,
                text=text,
                syllable_indices=indices,
                judged=similarity is not None,
                tone_similarity=None if similarity is None else round(similarity.score, 4),
                shape=None if similarity is None else round(similarity.shape, 4),
                range=None if similarity is None else round(similarity.range, 4),
                flat_reference=bool(similarity and similarity.flat_reference),
            )
        )
    return words


def _duration_ratios(
    student: UtteranceFeatures, reference: UtteranceFeatures
) -> list[Optional[float]]:
    """Per-syllable duration share of the student over the reference's.

    Dividing each syllable by its own utterance's mean cancels overall speed, so
    only the *pattern* of long and short syllables is compared.
    """
    count = len(student.syllables)
    student_mean = sum(s.duration_ms for s in student.syllables) / count
    reference_mean = sum(s.duration_ms for s in reference.syllables) / count
    ratios: list[Optional[float]] = []
    for stu, ref in zip(student.syllables, reference.syllables):
        if student_mean <= 0 or reference_mean <= 0 or ref.duration_ms <= 0 or stu.duration_ms <= 0:
            ratios.append(None)
            continue
        ratios.append((stu.duration_ms / student_mean) / (ref.duration_ms / reference_mean))
    return ratios


def _rhythm_similarity(ratios: list[Optional[float]], policy: PronunciationScoringPolicy) -> Optional[float]:
    usable = [r for r in ratios if r is not None]
    if not usable:
        return None
    limit = math.log(policy.rhythm.zero_ratio_factor)
    return sum(_clamp01(1.0 - abs(math.log(r)) / limit) for r in usable) / len(usable)


def _rate(utterance: UtteranceFeatures) -> float:
    seconds = utterance.articulation_ms / 1000.0
    return len(utterance.syllables) / seconds if seconds > 0 else 0.0


def _duration_similarity(rate_ratio: Optional[float], policy: PronunciationScoringPolicy) -> Optional[float]:
    if rate_ratio is None or rate_ratio <= 0:
        return None
    low, high = policy.rhythm.rate_band
    if rate_ratio < low:
        deviation = math.log(low / rate_ratio)
    elif rate_ratio > high:
        deviation = math.log(rate_ratio / high)
    else:
        return 1.0
    return _clamp01(1.0 - deviation / math.log(policy.rhythm.rate_zero_factor))


def _pause_similarity(
    student: UtteranceFeatures, reference: UtteranceFeatures, policy: PronunciationScoringPolicy
) -> float:
    tolerance = policy.rhythm.pause_match_gaps
    student_gaps = [p.after_syllable for p in student.pauses]
    reference_gaps = [p.after_syllable for p in reference.pauses]
    extra = sum(1 for g in student_gaps if all(abs(g - r) > tolerance for r in reference_gaps))
    missing = sum(1 for r in reference_gaps if all(abs(g - r) > tolerance for g in student_gaps))
    return _clamp01(
        1.0 - extra * policy.rhythm.extra_pause_penalty - missing * policy.rhythm.missing_pause_penalty
    )


def compare_utterances(
    student: UtteranceFeatures,
    reference: UtteranceFeatures,
    policy: PronunciationScoringPolicy = PronunciationScoringPolicy(),
) -> UtteranceComparison:
    _require_same_script(student, reference)
    if not student.syllables:
        raise ReferenceMismatchError("There are no syllables to compare.")

    alignment_confidence = min(student.alignment.confidence, reference.alignment.confidence)
    ratios = _duration_ratios(student, reference)
    word_sizes = {w: len(g) for w, g in _group_by_word(reference.syllables).items()}

    syllables = tuple(
        _compare_syllable(
            stu, ref, word_sizes[ref.expected.word_index], ratio, alignment_confidence, policy
        )
        for stu, ref, ratio in zip(student.syllables, reference.syllables, ratios)
    )
    words = _compare_words(student, reference, policy)
    judged = [w for w in words if w.judged]

    student_rate, reference_rate = _rate(student), _rate(reference)
    rate_ratio = student_rate / reference_rate if student_rate > 0 and reference_rate > 0 else None

    return UtteranceComparison(
        words=tuple(words),
        syllables=syllables,
        tone_similarity=(
            round(sum(w.tone_similarity for w in judged) / len(judged), 4) if judged else None
        ),
        judged_words=len(judged),
        total_words=len(words),
        rhythm_similarity=_round(_rhythm_similarity(ratios, policy)),
        duration_similarity=_round(_duration_similarity(rate_ratio, policy)),
        pause_similarity=_round(_pause_similarity(student, reference, policy)),
        speaking_rate_ratio=_round(rate_ratio),
        student_articulation_rate=round(student_rate, 3),
        alignment_confidence=round(alignment_confidence, 3),
    )


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 4)
