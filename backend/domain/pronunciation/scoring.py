"""Measured comparison -> one deterministic /100 score and ranked issues.

Only this module turns evidence into a number, and only through the policy: the
same comparison and the same policy always give the same score. No LLM is ever
involved - a language model may *explain* this result but can neither recompute
nor alter it.

Dimensions the recordings cannot support (segmental accuracy, intelligibility:
Praat measures pitch, timing and a vowel formant readout, not phoneme
correctness) are reported ``unavailable`` and left out, and the total is
renormalised over what was measured, rather than inventing a number for them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from domain.pronunciation.compare import (
    EVIDENCE_MODERATE,
    EVIDENCE_STRONG,
    EVIDENCE_WEAK,
    FLAG_LONG,
    FLAG_SHORT,
    UtteranceComparison,
)
from domain.pronunciation.policy import PronunciationScoringPolicy

STATUS_SCORED = "scored"
STATUS_UNSCORABLE = "unscorable"
REASON_NO_TONES = "no_measurable_tones"
REASON_IMPLAUSIBLE_RATE = "speaking_rate_implausible"

BASIS_MEASURED = "measured"
BASIS_UNAVAILABLE = "unavailable"

_DIMENSION_ORDER = ("tone", "segmental", "fluency", "intelligibility")
_UNAVAILABLE_NOTES = {
    "segmental": "Praat measures pitch, timing and a vowel readout, not whether each sound was pronounced correctly.",
    "intelligibility": "No acoustic measure of intelligibility is available.",
}
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_EVIDENCE_RANK = {EVIDENCE_STRONG: 0, EVIDENCE_MODERATE: 1, EVIDENCE_WEAK: 2}


@dataclass(frozen=True)
class DimensionScore:
    key: str
    basis: str
    #: 0-1 quality of this dimension; None when unavailable.
    ratio: Optional[float]
    weight: float
    #: Points this dimension can earn after renormalisation; None when unavailable.
    max_points: Optional[int]
    points: Optional[int]
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "basis": self.basis,
            "ratio": self.ratio,
            "weight": self.weight,
            "max_points": self.max_points,
            "points": self.points,
            "note": self.note,
        }


@dataclass(frozen=True)
class Issue:
    syllable_index: int
    hanzi: str
    word: str
    pinyin: str
    expected_tone: int
    code: str
    severity: str
    evidence: str
    tone_similarity: Optional[float]
    duration_ratio: Optional[float]
    #: Measured pitch direction of the reference and of the student.
    reference_direction: str = ""
    student_direction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "syllable_index": self.syllable_index,
            "hanzi": self.hanzi,
            "word": self.word,
            "pinyin": self.pinyin,
            "expected_tone": self.expected_tone,
            "code": self.code,
            "severity": self.severity,
            "evidence": self.evidence,
            "tone_similarity": self.tone_similarity,
            "duration_ratio": self.duration_ratio,
            "reference_direction": self.reference_direction,
            "student_direction": self.student_direction,
        }


@dataclass(frozen=True)
class PronunciationScore:
    status: str
    reason: Optional[str]
    total: Optional[int]
    dimensions: tuple[DimensionScore, ...]
    issues: tuple[Issue, ...]
    policy_version: str
    #: True when the total was scaled over fewer dimensions than the policy has.
    renormalized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "total": self.total,
            "renormalized": self.renormalized,
            "policy_version": self.policy_version,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "issues": [i.to_dict() for i in self.issues],
        }


def apportion(weights: Sequence[float], total: int) -> list[int]:
    """Split ``total`` into integers proportional to ``weights`` that add up to it
    exactly (largest-remainder), so displayed sub-scores always sum to the total."""
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [0 for _ in weights]
    exact = [total * w / weight_sum for w in weights]
    shares = [int(value) for value in exact]
    by_remainder = sorted(range(len(weights)), key=lambda i: exact[i] - shares[i], reverse=True)
    for i in by_remainder[: total - sum(shares)]:
        shares[i] += 1
    return shares


def _fluency_ratio(comparison: UtteranceComparison, policy: PronunciationScoringPolicy) -> Optional[float]:
    rhythm = policy.rhythm
    parts = (
        (comparison.rhythm_similarity, rhythm.rhythm_weight),
        (comparison.pause_similarity, rhythm.pause_weight),
        (comparison.duration_similarity, rhythm.duration_weight),
    )
    available = [(value, weight) for value, weight in parts if value is not None and weight > 0]
    weight_sum = sum(weight for _, weight in available)
    if weight_sum <= 0:
        return None
    return sum(value * weight for value, weight in available) / weight_sum


def _severity(code: str, similarity: Optional[float], duration_ratio: Optional[float], policy: PronunciationScoringPolicy) -> str:
    flags = policy.flags
    if code in (FLAG_SHORT, FLAG_LONG):
        ratio = duration_ratio or 1.0
        extreme = ratio > flags.medium_duration_ratio or ratio < 1.0 / flags.medium_duration_ratio
        return "medium" if extreme else "low"
    if similarity is not None and similarity < flags.high_severity_similarity:
        return "high"
    return "medium"


def _issues(comparison: UtteranceComparison, policy: PronunciationScoringPolicy) -> tuple[Issue, ...]:
    word_text = {word.word_index: word.text for word in comparison.words}
    issues = [
        Issue(
            syllable_index=syllable.index,
            hanzi=syllable.hanzi,
            word=word_text.get(syllable.word_index, syllable.hanzi),
            pinyin=syllable.pinyin,
            expected_tone=syllable.expected_tone,
            code=code,
            severity=_severity(code, syllable.tone_similarity, syllable.duration_ratio, policy),
            evidence=syllable.evidence,
            tone_similarity=syllable.tone_similarity,
            duration_ratio=syllable.duration_ratio,
            reference_direction=syllable.reference_direction,
            student_direction=syllable.student_direction,
        )
        for syllable in comparison.syllables
        for code in syllable.flags
    ]
    issues.sort(key=lambda i: (_SEVERITY_RANK[i.severity], _EVIDENCE_RANK[i.evidence], i.syllable_index))
    return tuple(issues)


def unscorable_score(reason: str, policy: PronunciationScoringPolicy) -> PronunciationScore:
    """A result that says, with a stable reason, that no score could be given."""
    return PronunciationScore(
        status=STATUS_UNSCORABLE, reason=reason, total=None, dimensions=(), issues=(),
        policy_version=policy.version,
    )


def score_comparison(
    comparison: UtteranceComparison,
    policy: PronunciationScoringPolicy = PronunciationScoringPolicy(),
) -> PronunciationScore:
    low, high = policy.rhythm.plausible_rate
    if not (low <= comparison.student_articulation_rate <= high):
        return unscorable_score(REASON_IMPLAUSIBLE_RATE, policy)
    if comparison.tone_similarity is None:
        return unscorable_score(REASON_NO_TONES, policy)

    ratios = {
        "tone": comparison.tone_similarity,
        "segmental": None,
        "fluency": _fluency_ratio(comparison, policy),
        "intelligibility": None,
    }
    weights = policy.weights.as_dict()
    measured = [k for k in _DIMENSION_ORDER if ratios[k] is not None and weights[k] > 0]
    maxima = dict(zip(measured, apportion([weights[k] for k in measured], 100)))

    dimensions = []
    for key in _DIMENSION_ORDER:
        if key in maxima:
            points = round(ratios[key] * maxima[key])
            dimensions.append(
                DimensionScore(key, BASIS_MEASURED, round(ratios[key], 4), weights[key], maxima[key], points)
            )
        else:
            dimensions.append(
                DimensionScore(key, BASIS_UNAVAILABLE, None, weights[key], None, None, _UNAVAILABLE_NOTES.get(key, ""))
            )

    return PronunciationScore(
        status=STATUS_SCORED,
        reason=None,
        total=sum(d.points for d in dimensions if d.points is not None),
        dimensions=tuple(dimensions),
        issues=_issues(comparison, policy),
        policy_version=policy.version,
        renormalized=len(measured) < len(_DIMENSION_ORDER),
    )
