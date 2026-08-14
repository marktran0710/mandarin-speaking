"""The one place that decides what a tone measurement means.

Background, because the naming here matters more than the code.

The production scorer (`chinese_tones.directional_tone_scores`) is **not** a
tone classifier. It is handed the tone the syllable is supposed to carry and
returns a 0-100 heuristic describing how well the measured pitch matched that
tone's expected direction. There is no probability distribution over T1-T4 and
nothing here may be called a probability, a confidence, or a likelihood.

The bug this module fixes: a middling contour match was being turned straight
into "the learner said it wrong". A weak match has at least three causes —

    the learner really did produce the wrong pitch movement,
    the pitch tracker had too little to work with,
    the syllable has no contour target at all (neutral tone),

— and only the first is a pronunciation error. Collapsing all three into ✗
tells students they are wrong when the system simply could not tell.

So the output is four states rather than a boolean:

    CORRECT        clear match against an accepted realization
    UNCERTAIN      measurement usable but not decisive, or not measurable
    INCORRECT      clear mismatch, with usable measurement behind it
    INVALID_AUDIO  the recording or segment cannot support any judgement

QC is a **gate, not a term**. It answers "can this measurement be trusted?",
never "how good was the pronunciation?", so it is never mixed into the score.

None of these states drive lesson progression. Progression still runs on the
legacy `score >= SYLLABLE_PASS_THRESHOLD` path, unchanged, so this patch
cannot move anyone's unlock state. See `praat_analyzer.SYLLABLE_PASS_THRESHOLD`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple


class DiagnosticStatus(str, Enum):
    """Diagnostic verdict for one syllable. Not a progression decision."""

    CORRECT = "CORRECT"
    UNCERTAIN = "UNCERTAIN"
    INCORRECT = "INCORRECT"
    INVALID_AUDIO = "INVALID_AUDIO"


# ── Where a contour score came from ───────────────────────────────────────
# The legacy scorer returns two hard-coded constants that are not
# measurements: 65.0 when a segment is too short to judge, and 75.0 for
# neutral tone, which has no contour target. Both sit above the legacy pass
# bar of 58, so today "could not measure" silently becomes ✓. Those constants
# stay in the legacy path — removing them would change progression — but they
# must never reach the diagnostic path dressed up as evidence.
PROVENANCE_MEASURED = "measured"
PROVENANCE_SHORT_SEGMENT_CONSTANT = "constant_short_segment"
PROVENANCE_NEUTRAL_CONSTANT = "neutral_not_measured"
PROVENANCE_NONE = "not_scored"

_CONSTANT_PROVENANCE = frozenset(
    {PROVENANCE_SHORT_SEGMENT_CONSTANT, PROVENANCE_NEUTRAL_CONSTANT}
)


# ── Thresholds ────────────────────────────────────────────────────────────
# ENGINEERING DEFAULTS. Neither number is validated against human raters, and
# neither may be described as such. They exist to be calibrated later against
# teacher judgements collected in the validation study; until then they are
# starting points chosen for the reasons below, not findings.
#
# CONFIRM: set to the legacy pass bar so that everything the diagnostic path
# calls CORRECT is also a legacy pass. That keeps the new display from ever
# being more generous than the gate students are actually measured by.
#
# ERROR: set below the score a *completely flat* contour earns, which is 50
# for T2/T4 (rise/fall of zero) and 45 for T3 (no dip) under the formulas in
# chinese_tones.directional_tone_scores. Below this line the pitch did not
# merely fail to move enough — it moved against the target. That is the
# weakest claim the current scorer can support for "this is an error", and it
# deliberately leaves a wide UNCERTAIN band rather than guessing.
TONE_CONFIRM_THRESHOLD = float(os.getenv("TONE_CONFIRM_THRESHOLD", "58.0"))
TONE_ERROR_THRESHOLD = float(os.getenv("TONE_ERROR_THRESHOLD", "45.0"))

# ── Word-level shape/direction verdict thresholds ────────────────────────
# ENGINEERING DEFAULTS, not calibrated cutoffs. The refactor makes shape the
# primary evidence and direction a consistency check; these constants control
# where "strong enough" and "poor enough" begin. Keep them named so a future
# reader can grep for them and a calibration pass can move them from one place.
#
# Read as: shape >= SHAPE_STRONG is enough to confirm the tone when direction
# is at least DIRECTION_SUPPORT. Shape below SHAPE_WEAK combined with direction
# at or below DIRECTION_BAD is the only combination that produces INCORRECT —
# either component alone must resolve to UNCERTAIN, never a verdict.
SHAPE_STRONG = float(os.getenv("TONE_SHAPE_STRONG", "80.0"))
SHAPE_WEAK = float(os.getenv("TONE_SHAPE_WEAK", "60.0"))
DIRECTION_SUPPORT = float(os.getenv("TONE_DIRECTION_SUPPORT", "60.0"))
DIRECTION_BAD = float(os.getenv("TONE_DIRECTION_BAD", "45.0"))

# Weight for the display composite score. Not a verdict input — kept only so
# a single number can be shown to learners for progress history. Shape leads
# because it is the primary evidence in the decision hierarchy.
DISPLAY_SHAPE_WEIGHT = 0.70
DISPLAY_DIRECTION_WEIGHT = 0.30

#: Recording-level QC reasons that make any tone judgement meaningless.
#: Sourced from main._assess_recording_quality; kept as a set here so the
#: mapping from reason code to "unusable" is stated once.
UNUSABLE_RECORDING_REASONS = frozenset(
    {
        "recording_too_short",
        "signal_too_quiet",
        "insufficient_speech",
        "audio_clipping",
        "audio_format_unverified",
    }
)


@dataclass(frozen=True)
class QcEvidence:
    """Everything known about whether a measurement can be trusted.

    Fields mirror signals the pipeline already produces — nothing here is
    invented. `can_score_pronunciation` and `reason_codes` come from
    main._assess_recording_quality; `judged`, `pitch_points` and
    `minimum_pitch_points` come from praat_analyzer.estimate_word_prosody.
    """

    can_score_pronunciation: bool = True
    judged: bool = True
    pitch_points: int = 0
    minimum_pitch_points: int = 0
    voiced_ratio: Optional[float] = None
    reason_codes: Tuple[str, ...] = ()

    @property
    def unusable_recording(self) -> bool:
        if not self.can_score_pronunciation:
            return True
        return bool(UNUSABLE_RECORDING_REASONS.intersection(self.reason_codes))

    @property
    def thin_evidence(self) -> bool:
        """Usable recording, but not enough pitch to decide this syllable."""
        if not self.judged:
            return True
        if self.minimum_pitch_points > 0:
            return self.pitch_points < self.minimum_pitch_points
        return False


@dataclass(frozen=True)
class ToneDiagnosis:
    """Result of one syllable's decision, with the reasoning attached."""

    status: DiagnosticStatus
    reason: str
    #: The score the decision was actually taken on, or None when no usable
    #: measurement existed. Never call this a probability or a confidence.
    contour_match_score: Optional[float] = None
    #: Which accepted realization the score was measured against.
    matched_surface_tone: Optional[int] = None
    score_provenance: str = PROVENANCE_NONE
    confirm_threshold: float = TONE_CONFIRM_THRESHOLD
    error_threshold: float = TONE_ERROR_THRESHOLD

    def as_dict(self) -> dict:
        return {
            "diagnostic_status": self.status.value,
            "diagnostic_reason": self.reason,
            "contour_match_score": self.contour_match_score,
            "matched_surface_tone": self.matched_surface_tone,
            "score_provenance": self.score_provenance,
            "confirm_threshold": self.confirm_threshold,
            "error_threshold": self.error_threshold,
            # Guard against a future reader — human or script — mistaking
            # these for validated cutoffs. INCORRECT here means "strong
            # heuristic evidence of a contour mismatch", not "an established
            # pronunciation error". Flip this only when the thresholds have
            # actually been calibrated against human raters.
            "threshold_validated": False,
        }


def decide_tone(
    contour_match_score: Optional[float],
    score_provenance: str,
    qc: QcEvidence,
    *,
    matched_surface_tone: Optional[int] = None,
    measurable_by_contour: bool = True,
    confirm_threshold: float = None,
    error_threshold: float = None,
) -> ToneDiagnosis:
    """Decide what one syllable's contour measurement means.

    Order matters and follows "can we trust it?" before "what does it say?":

    1. Recording or segment unusable        → INVALID_AUDIO
    2. Nothing was actually measured        → UNCERTAIN
    3. Evidence too thin to decide          → UNCERTAIN
    4. Score above the confirm bar          → CORRECT
    5. Score below the error bar            → INCORRECT
    6. Anything between the two bars        → UNCERTAIN

    QC never adjusts the score. A poor measurement removes the system's right
    to an opinion; it does not lower the learner's result.
    """
    confirm = TONE_CONFIRM_THRESHOLD if confirm_threshold is None else confirm_threshold
    error = TONE_ERROR_THRESHOLD if error_threshold is None else error_threshold

    def build(status: DiagnosticStatus, reason: str, score: Optional[float]) -> ToneDiagnosis:
        return ToneDiagnosis(
            status=status,
            reason=reason,
            contour_match_score=score,
            matched_surface_tone=matched_surface_tone,
            score_provenance=score_provenance,
            confirm_threshold=confirm,
            error_threshold=error,
        )

    # 1. The recording itself cannot support a judgement. Asking the learner
    #    to record again is the honest response; calling it wrong is not.
    if qc.unusable_recording:
        return build(DiagnosticStatus.INVALID_AUDIO, "recording_quality_unusable", None)

    # 2. No measurement at all, or one of the legacy placeholder constants.
    #    A constant is not evidence, so it can never produce CORRECT or
    #    INCORRECT no matter which side of a threshold it happens to land on.
    if score_provenance == PROVENANCE_NEUTRAL_CONSTANT or not measurable_by_contour:
        return build(
            DiagnosticStatus.UNCERTAIN, "neutral_tone_has_no_contour_target", None
        )
    if score_provenance == PROVENANCE_SHORT_SEGMENT_CONSTANT:
        return build(
            DiagnosticStatus.UNCERTAIN, "segment_too_short_to_measure", None
        )
    if contour_match_score is None or score_provenance == PROVENANCE_NONE:
        return build(DiagnosticStatus.UNCERTAIN, "no_contour_measurement", None)

    # 3. Measured, but on too little pitch to stand behind either verdict.
    if qc.thin_evidence:
        return build(
            DiagnosticStatus.UNCERTAIN, "insufficient_pitch_evidence", contour_match_score
        )

    # 4-6. Now, and only now, the score is allowed to speak.
    score = float(contour_match_score)
    if score >= confirm:
        return build(DiagnosticStatus.CORRECT, "contour_matches_expected_tone", score)
    if score <= error:
        return build(
            DiagnosticStatus.INCORRECT, "contour_contradicts_expected_tone", score
        )
    return build(DiagnosticStatus.UNCERTAIN, "contour_match_inconclusive", score)


@dataclass(frozen=True)
class WordToneDiagnosis:
    """Word-level verdict from separate shape and direction evidence.

    Kept structurally close to :class:`ToneDiagnosis` so the two can share
    downstream code, but the fields differ: shape and direction are surfaced
    as their own numbers, and ``display_score`` is a shape-weighted composite
    for progress history only — it is **not** the input to the verdict.
    """

    status: DiagnosticStatus
    reason: str
    shape_score: Optional[float]
    direction_score: Optional[float]
    display_score: float
    shape_strong_threshold: float = SHAPE_STRONG
    shape_weak_threshold: float = SHAPE_WEAK
    direction_support_threshold: float = DIRECTION_SUPPORT
    direction_bad_threshold: float = DIRECTION_BAD

    def as_dict(self) -> dict:
        return {
            "verdict": self.status.value,
            "reason": self.reason,
            "shape_score": self.shape_score,
            "direction_score": self.direction_score,
            "display_score": self.display_score,
            "shape_strong_threshold": self.shape_strong_threshold,
            "shape_weak_threshold": self.shape_weak_threshold,
            "direction_support_threshold": self.direction_support_threshold,
            "direction_bad_threshold": self.direction_bad_threshold,
            # Same guard as ToneDiagnosis: these are engineering starting
            # points, never calibrated cutoffs. Flip only after human-rater
            # calibration.
            "threshold_validated": False,
        }


def _display_composite(shape_score: Optional[float], direction_score: Optional[float]) -> float:
    """The shape-weighted display composite. Never the verdict input.

    Missing components are treated as 0 for the display number so a payload
    always carries one; the verdict path handles missing evidence via QC.
    """
    shape = float(shape_score) if shape_score is not None else 0.0
    direction = float(direction_score) if direction_score is not None else 0.0
    return round(DISPLAY_SHAPE_WEIGHT * shape + DISPLAY_DIRECTION_WEIGHT * direction, 2)


def decide_word_tone(
    shape_score: Optional[float],
    direction_score: Optional[float],
    qc: QcEvidence,
) -> WordToneDiagnosis:
    """Word-level verdict from shape + direction evidence.

    Decision hierarchy (order matters — "can we trust it?" before "what does
    it say?"):

    1. Unusable recording                              → INVALID_AUDIO
    2. Thin pitch evidence / measurement not judged    → UNCERTAIN
    3. Strong shape AND supporting direction           → CORRECT
    4. Strong shape XOR weak direction                 → UNCERTAIN
       (shape/direction disagreement — the contour visibly matches the
        target but the coarse directional heuristic doesn't agree; the
        learner is told the pitch movement was not clear enough, never
        that the tone was wrong)
    5. Weak shape (SHAPE_WEAK ≤ shape < SHAPE_STRONG)  → UNCERTAIN
       (direction never rescues a middling shape)
    6. Shape < SHAPE_WEAK AND direction ≤ DIRECTION_BAD → INCORRECT
       (both signals point away from the expected tone — the only combination
        this scorer can honestly call an error)
    7. Anything else                                   → UNCERTAIN

    ``display_score`` is a 70/30 shape-weighted composite kept for progress
    history and never used as a verdict input. QC never adjusts the score;
    poor measurement removes the system's right to an opinion, it does not
    lower the learner's numbers.
    """
    display = _display_composite(shape_score, direction_score)

    def build(status: DiagnosticStatus, reason: str) -> WordToneDiagnosis:
        return WordToneDiagnosis(
            status=status,
            reason=reason,
            shape_score=shape_score,
            direction_score=direction_score,
            display_score=display,
        )

    # 1. Recording itself unusable — never call the learner wrong for that.
    if qc.unusable_recording:
        return build(DiagnosticStatus.INVALID_AUDIO, "invalid_audio")

    # 2. Measurement too thin (short segment, low voiced-pitch density, or
    #    unjudged for another reason). No verdict is honest here.
    if qc.thin_evidence:
        return build(DiagnosticStatus.UNCERTAIN, "insufficient_pitch_frames")

    # Both components must be present to reach the acoustic branches.
    if shape_score is None or direction_score is None:
        return build(DiagnosticStatus.UNCERTAIN, "no_contour_measurement")

    shape = float(shape_score)
    direction = float(direction_score)

    # 3-4. Strong shape branch: shape is the primary evidence.
    if shape >= SHAPE_STRONG:
        if direction >= DIRECTION_SUPPORT:
            return build(DiagnosticStatus.CORRECT, "strong_shape_supported")
        return build(DiagnosticStatus.UNCERTAIN, "shape_direction_disagreement")

    # 5. Middle band — shape is neither strong nor clearly poor. Direction
    #    alone cannot rescue this, by design; a weak shape stays UNCERTAIN
    #    regardless of how well the pitch moved in the right direction.
    if shape >= SHAPE_WEAK:
        return build(DiagnosticStatus.UNCERTAIN, "weak_shape")

    # 6. Poor shape: only combined with a matching directional failure does
    #    the scorer commit to INCORRECT. The <= for DIRECTION_BAD mirrors the
    #    inclusive semantics the legacy scorer used for its own error bar.
    if direction <= DIRECTION_BAD:
        return build(DiagnosticStatus.INCORRECT, "strong_negative_evidence")

    # 7. Weak shape + inconclusive direction — unable to call it either way.
    return build(DiagnosticStatus.UNCERTAIN, "weak_shape")


def aggregate_word(statuses: Sequence[DiagnosticStatus]) -> DiagnosticStatus:
    """Roll syllable diagnoses up to a word.

    One uncertain syllable must not condemn a word — that is the whole point
    of having an UNCERTAIN state. Only a syllable the system is prepared to
    call an error makes the word an error.
    """
    if not statuses:
        return DiagnosticStatus.UNCERTAIN
    if any(status is DiagnosticStatus.INCORRECT for status in statuses):
        return DiagnosticStatus.INCORRECT
    if any(status is DiagnosticStatus.INVALID_AUDIO for status in statuses):
        return DiagnosticStatus.INVALID_AUDIO
    if any(status is DiagnosticStatus.UNCERTAIN for status in statuses):
        return DiagnosticStatus.UNCERTAIN
    return DiagnosticStatus.CORRECT


def summarize_sentence(statuses: Sequence[DiagnosticStatus]) -> dict:
    """Counts plus a sentence verdict, for display and for research export.

    Deliberately reports the distribution rather than only a verdict: the
    counts are what a later comparison against human raters needs, and they
    make "5 uncertain, 0 incorrect" legible as the very different situation it
    is from "5 incorrect".
    """
    counts = {
        "correct": 0,
        "uncertain": 0,
        "incorrect": 0,
        "invalid_audio": 0,
    }
    for status in statuses:
        counts[status.value.lower()] += 1

    analyzable = counts["correct"] + counts["uncertain"] + counts["incorrect"]
    if analyzable == 0:
        verdict = DiagnosticStatus.INVALID_AUDIO
    elif counts["incorrect"] > 0:
        verdict = DiagnosticStatus.INCORRECT
    elif counts["uncertain"] > 0 or counts["invalid_audio"] > 0:
        verdict = DiagnosticStatus.UNCERTAIN
    else:
        verdict = DiagnosticStatus.CORRECT

    # What the learner should *do* is a separate question from what the
    # sentence *is*. One bad syllable out of eleven is a real error and the
    # verdict says so, but the useful response is to drill that syllable, not
    # to throw the whole recording away. Re-recording is reserved for the case
    # where there is nothing analyzable to work with.
    if analyzable == 0:
        action = "record_again"
    elif counts["incorrect"] > 0:
        action = "targeted_practice"
    else:
        action = "none"

    return {
        "counts": counts,
        "diagnostic_status": verdict.value,
        "recommended_action": action,
    }
