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
