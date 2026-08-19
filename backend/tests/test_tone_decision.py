"""The four-state tone decision, and the bugs it was written to kill.

The old system turned one heuristic number into ✓ or ✗. That made three very
different situations look identical to a learner:

    the pitch moved the wrong way        (a real error)
    the tracker had almost nothing       (a measurement failure)
    the syllable has no tone target      (neutral tone)

Only the first deserves a red mark. Most of what follows pins the other two
down so they can never be reported as learner mistakes again.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chinese_tones import (
    directional_tone_scores,
    directional_tone_scores_with_provenance,
)
from tone_decision import (
    PROVENANCE_MEASURED,
    PROVENANCE_NEUTRAL_CONSTANT,
    PROVENANCE_NONE,
    PROVENANCE_SHORT_SEGMENT_CONSTANT,
    TONE_CONFIRM_THRESHOLD,
    TONE_ERROR_THRESHOLD,
    DiagnosticStatus,
    QcEvidence,
    aggregate_word,
    decide_tone,
    summarize_sentence,
)

GOOD_QC = QcEvidence(
    can_score_pronunciation=True, judged=True, pitch_points=40, minimum_pitch_points=8
)


def status(score, provenance=PROVENANCE_MEASURED, qc=GOOD_QC, **kwargs):
    return decide_tone(score, provenance, qc, **kwargs).status


# ── A: the scorer's output is per syllable, not a class distribution ──────


def test_scores_are_one_per_syllable_not_a_tone_distribution():
    """The single most consequential misreading of this codebase.

    `directional_tone_scores` is handed the tones the syllables are supposed
    to carry and returns one score per *syllable*. It is not a classifier and
    there is no argmax over T1-T4 anywhere: three tones in, three scores out,
    aligned by position. Anything that treats index 0 as "P(T1)" is wrong.
    """
    contour = [(i * 0.01, 200.0 + i) for i in range(90)]

    assert len(directional_tone_scores(contour, [2])) == 1
    assert len(directional_tone_scores(contour, [2, 3])) == 2
    assert len(directional_tone_scores(contour, [2, 3, 4])) == 3

    # A four-class distribution would sum to 1 (or 100). These do not, and are
    # not comparable across positions.
    scores = directional_tone_scores(contour, [1, 1, 1, 1])
    assert sum(scores) > 100.0

    # Each syllable's score depends only on its own window and its own tone,
    # which is what makes scoring one syllable at a time exact.
    windows = [(0, 30), (30, 60), (60, 90)]
    together = directional_tone_scores(contour, [2, 3, 4], syllable_windows=windows)
    apart = [
        directional_tone_scores(contour, [tone], [window])[0]
        for tone, window in zip([2, 3, 4], windows)
    ]
    assert together == pytest.approx(apart)


# ── C / D: the two placeholder constants are not evidence ────────────────


def test_short_segment_constant_never_becomes_correct():
    """65 is what the scorer returns when a segment is too short to judge.

    It sits above the legacy pass bar of 58, so today an unmeasurable syllable
    silently reads as a pass. The diagnostic path must refuse it in *both*
    directions: not CORRECT, and not INCORRECT either.
    """
    assert 65.0 > TONE_CONFIRM_THRESHOLD, "premise: the constant clears the legacy bar"
    result = decide_tone(65.0, PROVENANCE_SHORT_SEGMENT_CONSTANT, GOOD_QC)
    assert result.status is DiagnosticStatus.UNCERTAIN
    assert result.reason == "segment_too_short_to_measure"
    assert result.contour_match_score is None, "a constant must not be shown as a score"


def test_neutral_tone_constant_is_not_a_measurement():
    """75 is returned for every neutral-tone syllable, always, regardless of
    what the learner did. It is a placeholder, not pronunciation quality."""
    result = decide_tone(
        75.0, PROVENANCE_NEUTRAL_CONSTANT, GOOD_QC, measurable_by_contour=False
    )
    assert result.status is DiagnosticStatus.UNCERTAIN
    assert result.reason == "neutral_tone_has_no_contour_target"
    assert result.contour_match_score is None


def test_the_constants_are_labelled_at_source():
    """The provenance labels have to actually come out of the scorer, or the
    decision layer is guessing."""
    contour = [(i * 0.01, 200.0 + i) for i in range(90)]
    _, provenance = directional_tone_scores_with_provenance(contour, [2, 5])
    assert provenance == [PROVENANCE_MEASURED, PROVENANCE_NEUTRAL_CONSTANT]

    # The contour is always resampled to 100 points, so "too short" is a
    # property of the syllable *window*, not of the recording: a syllable the
    # aligner gave fewer than four frames to cannot be judged.
    scores, provenance = directional_tone_scores_with_provenance(
        contour, [2, 2], syllable_windows=[(0, 2), (2, 60)]
    )
    assert scores[0] == 65.0
    assert provenance == [PROVENANCE_SHORT_SEGMENT_CONSTANT, PROVENANCE_MEASURED]


# ── H: a weak match is not an accusation ─────────────────────────────────


def test_a_middling_score_is_uncertain_not_incorrect():
    """The original complaint. A score between the error and confirm bars
    means the system is unsure, not that the learner was wrong. Generated
    relative to the two threshold constants so this stays correct across
    calibration passes rather than pinning to the original 45-58 band."""
    midpoint = (TONE_ERROR_THRESHOLD + TONE_CONFIRM_THRESHOLD) / 2
    for score in (
        TONE_ERROR_THRESHOLD + 0.1,
        midpoint,
        TONE_CONFIRM_THRESHOLD - 0.1,
    ):
        assert status(score) is DiagnosticStatus.UNCERTAIN, score


def test_a_clear_match_is_correct():
    for score in (58.0, 69.0, 94.0, 100.0):
        assert status(score) is DiagnosticStatus.CORRECT, score


# ── I: a clear contradiction may be called an error ──────────────────────


def test_a_contour_moving_against_the_target_is_incorrect():
    """Below the error bar the pitch did not merely fail to move enough — it
    moved the other way. That is the weakest claim this scorer can support for
    an error, and it is still the only place INCORRECT comes from."""
    for score in (0.0, 20.0, 37.0, 45.0):
        assert status(score) is DiagnosticStatus.INCORRECT, score


def test_the_uncertain_band_is_not_empty():
    """A regression guard: collapsing the two thresholds onto each other would
    silently restore the old binary behaviour."""
    assert TONE_ERROR_THRESHOLD < TONE_CONFIRM_THRESHOLD


def test_thresholds_are_configurable_per_call():
    assert (
        decide_tone(53.0, PROVENANCE_MEASURED, GOOD_QC, confirm_threshold=50.0).status
        is DiagnosticStatus.CORRECT
    )
    # 42 sits below the module's default confirm bar, so raising the error
    # override to 60 is what decides this one, not the confirm default.
    assert (
        decide_tone(42.0, PROVENANCE_MEASURED, GOOD_QC, error_threshold=60.0).status
        is DiagnosticStatus.INCORRECT
    )


# ── J / G: QC gates the verdict, it never scores the learner ─────────────


def test_an_unusable_recording_is_never_a_pronunciation_error():
    """Praat failing to track pitch is the system's problem, not the
    student's. Even a score of zero cannot produce INCORRECT here."""
    unusable = QcEvidence(can_score_pronunciation=False)
    result = decide_tone(0.0, PROVENANCE_MEASURED, unusable)
    assert result.status is DiagnosticStatus.INVALID_AUDIO
    assert result.contour_match_score is None


@pytest.mark.parametrize(
    "reason",
    ["recording_too_short", "signal_too_quiet", "insufficient_speech", "audio_clipping"],
)
def test_recording_quality_reason_codes_gate_the_verdict(reason):
    qc = QcEvidence(reason_codes=(reason,))
    assert status(10.0, qc=qc) is DiagnosticStatus.INVALID_AUDIO


def test_thin_pitch_evidence_downgrades_to_uncertain_not_incorrect():
    """The recording is fine, but this syllable had too few voiced frames to
    stand behind either verdict."""
    thin = QcEvidence(judged=True, pitch_points=3, minimum_pitch_points=8)
    result = decide_tone(12.0, PROVENANCE_MEASURED, thin)
    assert result.status is DiagnosticStatus.UNCERTAIN
    assert result.reason == "insufficient_pitch_evidence"

    unjudged = QcEvidence(judged=False, pitch_points=40, minimum_pitch_points=8)
    assert status(12.0, qc=unjudged) is DiagnosticStatus.UNCERTAIN


def test_qc_is_a_gate_and_never_moves_the_score():
    """Explicitly not a weighted blend: good and thin evidence produce the
    same number, and differ only in whether a verdict is allowed."""
    good = decide_tone(72.0, PROVENANCE_MEASURED, GOOD_QC)
    thin = decide_tone(
        72.0, PROVENANCE_MEASURED, QcEvidence(pitch_points=1, minimum_pitch_points=8)
    )
    assert good.contour_match_score == thin.contour_match_score == 72.0
    assert good.status is DiagnosticStatus.CORRECT
    assert thin.status is DiagnosticStatus.UNCERTAIN


def test_no_measurement_at_all_is_uncertain():
    assert status(None, PROVENANCE_NONE) is DiagnosticStatus.UNCERTAIN


# ── B: nothing here may be called a probability ──────────────────────────


def test_the_schema_never_calls_a_heuristic_score_a_probability():
    """Naming guard. `directional_tone_scores` is a rule-based contour match;
    a field called confidence or probability would invite every reader to
    treat 53 as P(correct) = 0.53."""
    payload = decide_tone(53.0, PROVENANCE_MEASURED, GOOD_QC).as_dict()
    banned = ("probability", "confidence", "likelihood", "predicted_tone")
    for key in payload:
        assert not any(word in key for word in banned), key
    assert "contour_match_score" in payload
    assert payload["contour_match_score"] == 53.0
    # And the number stays on its native 0-100 scale — not rescaled into
    # something that looks like a probability.
    assert payload["contour_match_score"] > 1.0


# ── Word and sentence roll-up ────────────────────────────────────────────


def test_one_uncertain_syllable_does_not_condemn_the_word():
    assert (
        aggregate_word([DiagnosticStatus.CORRECT, DiagnosticStatus.UNCERTAIN])
        is DiagnosticStatus.UNCERTAIN
    )
    assert (
        aggregate_word([DiagnosticStatus.CORRECT, DiagnosticStatus.CORRECT])
        is DiagnosticStatus.CORRECT
    )
    assert (
        aggregate_word([DiagnosticStatus.UNCERTAIN, DiagnosticStatus.INCORRECT])
        is DiagnosticStatus.INCORRECT
    )
    assert aggregate_word([]) is DiagnosticStatus.UNCERTAIN


def test_a_single_error_asks_for_targeted_practice_not_a_whole_retake():
    """Nine good syllables and one bad one is a reason to drill that syllable,
    not to throw the recording away."""
    summary = summarize_sentence(
        [DiagnosticStatus.CORRECT] * 9 + [DiagnosticStatus.INCORRECT]
    )
    assert summary["counts"] == {
        "correct": 9,
        "uncertain": 0,
        "incorrect": 1,
        "invalid_audio": 0,
    }
    assert summary["recommended_action"] == "targeted_practice"


def test_a_sentence_of_uncertainties_does_not_fail():
    summary = summarize_sentence(
        [DiagnosticStatus.CORRECT] * 5 + [DiagnosticStatus.UNCERTAIN] * 5
    )
    assert summary["diagnostic_status"] == "UNCERTAIN"
    assert summary["recommended_action"] == "none"


def test_nothing_analyzable_asks_for_a_new_recording():
    summary = summarize_sentence([DiagnosticStatus.INVALID_AUDIO] * 4)
    assert summary["diagnostic_status"] == "INVALID_AUDIO"
    assert summary["recommended_action"] == "record_again"
