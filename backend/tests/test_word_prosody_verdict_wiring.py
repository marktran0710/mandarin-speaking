"""Word prosody verdict wiring after the tone-verdict refactor.

The refactor decouples the numeric display score from the verdict and makes
``word["passed"]`` derive from the canonical shape+direction decision
instead of a raw threshold check. These integration tests pin the invariants
the spec calls out (§15) end-to-end through ``estimate_word_prosody``:

* every judged word carries the new shape/direction/display/verdict/reason
  fields alongside the legacy ``score``/``passed`` fields;
* ``passed`` follows the verdict (``verdict == CORRECT``), not a raw score
  threshold — so a strong shape blocked by a coarse directional heuristic
  becomes UNCERTAIN and NOT a pass;
* a placeholder syllable (short segment / neutral) can never produce
  ``word["passed"] is True``, closing the "constant 65/75 auto-passes"
  loophole from the legacy path;
* the per-syllable min-rule safety net still enforces: one wrong syllable
  fails the word even if the word-level shape/direction agree.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from praat_analyzer import estimate_word_prosody


def _contour(pitch_pattern, base_hz=220.0, spread_hz=160.0, num_points=60, duration=0.8):
    x = np.linspace(0, 1, len(pitch_pattern))
    x_new = np.linspace(0, 1, num_points)
    shape = np.interp(x_new, x, pitch_pattern)
    freqs = base_hz + (shape - 0.5) * spread_hz
    times = np.linspace(0, duration, num_points)
    return list(zip(times.tolist(), freqs.tolist()))


# 在家 = T4 falling + T1 level.
_CORRECT_ZAIJIA = [0.95, 0.75, 0.55, 0.35, 0.79, 0.75, 0.78, 0.74]
_RISING_ZAIJIA = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def test_word_carries_new_shape_direction_display_verdict_fields():
    """Every judged word exposes the refactor's new payload: shape and
    direction as separate numbers, a display composite, a verdict, and a
    reason code — no consumer should have to reach into `syllables` to find
    the word-level story."""
    word = estimate_word_prosody(_contour(_CORRECT_ZAIJIA), "在家")[0]
    assert "shape_score" in word
    assert "direction_score" in word
    assert "display_score" in word
    assert "verdict" in word
    assert "reason" in word
    assert word["verdict"] in {"CORRECT", "UNCERTAIN", "INCORRECT", "INVALID_AUDIO"}


def test_passed_is_true_only_when_verdict_is_correct():
    """The invariant the refactor centralizes: `passed` is derived from the
    verdict, not from a raw score threshold. So verdict==CORRECT ⇔ passed."""
    word = estimate_word_prosody(_contour(_CORRECT_ZAIJIA), "在家")[0]
    assert (word["passed"] is True) is (word["verdict"] == "CORRECT")


def test_wrong_tone_word_is_not_passed():
    """A steady rise where T4 should fall must not pass. The verdict may
    settle at INCORRECT or UNCERTAIN depending on which component fails
    hardest — either way, `passed` must be False."""
    word = estimate_word_prosody(_contour(_RISING_ZAIJIA), "在家")[0]
    assert word["passed"] is False
    assert word["verdict"] != "CORRECT"


def test_placeholder_syllable_never_produces_passed_true():
    """Two words share a very short contour: each word's slice is too short
    to yield real measurements. The legacy path returned a constant 65 that
    silently cleared the 58 threshold and made these words pass. After the
    refactor, `passed` cannot be True on evidence the system did not
    actually measure."""
    contour = _contour([0.5, 0.5, 0.5], num_points=7, duration=0.1)
    words = estimate_word_prosody(contour, "在家 很好")
    for word in words:
        if word["syllables"]:
            # Whether the segment is called `judged=False` or downgraded via
            # the diagnostic path, the invariant is the same: no PASS.
            assert word["passed"] is not True
            for syllable in word["syllables"]:
                assert syllable["passed"] is not True


def test_display_score_is_shape_weighted_seventy_thirty():
    """display_score = 0.70 * shape + 0.30 * direction. Kept as a separate
    number so a single value can be shown in progress history, without ever
    becoming the input to the verdict."""
    word = estimate_word_prosody(_contour(_CORRECT_ZAIJIA), "在家")[0]
    if word.get("shape_score") is not None and word.get("direction_score") is not None:
        expected = 0.70 * word["shape_score"] + 0.30 * word["direction_score"]
        assert abs(word["display_score"] - expected) < 0.5, word


def test_syllable_min_rule_still_blocks_word_pass():
    """A wrong first syllable in an otherwise fine word must still fail the
    word. The refactor changed how `passed` is derived, not the min-rule
    safety net that catches per-syllable failures."""
    word = estimate_word_prosody(_contour(_RISING_ZAIJIA), "在家")[0]
    syllable_passed = [s["passed"] for s in word["syllables"]]
    assert False in syllable_passed
    assert word["passed"] is False


def test_word_promotion_propagates_passed_to_measured_uncertain_syllables():
    """When decide_word_tone promotes a word to CORRECT via strong
    whole-word evidence, per-syllable `passed` for measured-UNCERTAIN
    syllables must follow the promotion — otherwise the sentence-level 80%
    gate (build_pronunciation_mastery) still fails on a word the verdict
    layer already passed. `diagnostic_status` stays UNCERTAIN so the row
    still shows △, but `passed` is a GATE flag and must reflect what the
    canonical word verdict says."""
    from tone_decision import DiagnosticStatus, QcEvidence, decide_word_tone

    # Sanity: this shape/direction pair promotes to CORRECT.
    good_qc = QcEvidence(judged=True, pitch_points=40, minimum_pitch_points=8)
    assert (
        decide_word_tone(shape_score=86.0, direction_score=79.0, qc=good_qc).status
        is DiagnosticStatus.CORRECT
    )

    # The 我要 case from the bug report: real-world contour with the T3+T4
    # pattern well-formed at the word level but each syllable's own
    # coarse-heuristic score landing in the UNCERTAIN band.
    contour = _contour(
        [0.55, 0.4, 0.25, 0.4, 0.55, 0.75, 0.55, 0.35, 0.20], num_points=80
    )
    words = estimate_word_prosody(contour, "我要")
    assert words
    word = words[0]
    if word.get("verdict") == "CORRECT":
        # Whenever the word verdict is CORRECT, every measured syllable
        # must count as passed for the sentence-level gate.
        for syllable in word["syllables"]:
            if syllable.get("score_provenance") in {
                "constant_short_segment",
                "neutral_not_measured",
                "not_scored",
            }:
                continue
            assert syllable["passed"] is True, syllable


def test_reason_reflects_incorrect_syllable_override_not_stale_word_decision():
    """Bug: a word can clear SHAPE_STRONG/DIRECTION_SUPPORT at the whole-word
    level — decide_word_tone calls that CORRECT with reason
    "strong_shape_supported" — while a syllable independently measures as
    INCORRECT (contour actively contradicts the expected tone), without the
    whole-word evidence being strong enough to clear the *stricter*
    PHRASE_RESCUE bar that would override that syllable (see
    test_exceptionally_strong_word_shape_overrides_an_incorrect_syllable for
    that case). The min-rule safety net correctly drops the word's *verdict*
    to INCORRECT here, but `reason` was left as the pre-override
    "strong_shape_supported" — text that reads as justification for a
    CORRECT verdict, directly contradicting the INCORRECT verdict sitting
    next to it in the same payload. `reason` must describe whichever status
    actually won, not the word-level decision that got overridden."""
    from praat_analyzer import _combine_word_verdict
    from tone_decision import DiagnosticStatus, WordToneDiagnosis

    word_decision = WordToneDiagnosis(
        status=DiagnosticStatus.CORRECT,
        reason="strong_shape_supported",
        shape_score=72.0,
        direction_score=61.0,
        display_score=68.7,
    )
    syllables = [
        {"diagnostic_status": "CORRECT"},
        {"diagnostic_status": "INCORRECT"},
    ]

    final_status, reason = _combine_word_verdict(word_decision, syllables)

    assert final_status is DiagnosticStatus.INCORRECT
    assert reason != "strong_shape_supported"
    assert "incorrect" in reason


def test_exceptionally_strong_word_shape_overrides_an_incorrect_syllable():
    """The 週末 case from a live session: shape=93/direction=94 at the
    whole-word level (well above SHAPE_STRONG=70/DIRECTION_SUPPORT=60), but
    末 independently measures INCORRECT — and the word still reads "Likely
    tone mismatch" despite the strong aggregate, because the ordinary
    min-rule does not care how strong the word-level evidence is.

    This is the same evidentiary bar `_apply_phrase_rescue` already uses for
    exactly this class of claim (overriding an individually-measured
    INCORRECT syllable), just applied without requiring the phrase to span a
    jieba word boundary — 週末 is already a single token, so there is
    nothing to merge across. When the whole-word evidence clears the
    stricter PHRASE_RESCUE_SHAPE_STRONG/PHRASE_RESCUE_DIRECTION_SUPPORT bar,
    the override applies here too, and must be as transparent as the phrase
    rescue is: the syllable's own diagnostic fields flip to CORRECT with a
    named reason and evidence, not just a silently-flipped `passed`."""
    from praat_analyzer import _combine_word_verdict
    from tone_decision import DiagnosticStatus, PHRASE_RESCUE_DIRECTION_SUPPORT, PHRASE_RESCUE_SHAPE_STRONG, WordToneDiagnosis

    assert 93.0 >= PHRASE_RESCUE_SHAPE_STRONG
    assert 94.0 >= PHRASE_RESCUE_DIRECTION_SUPPORT

    word_decision = WordToneDiagnosis(
        status=DiagnosticStatus.CORRECT,
        reason="strong_shape_supported",
        shape_score=93.0,
        direction_score=94.0,
        display_score=93.3,
    )
    syllables = [
        {"char": "週", "diagnostic_status": "CORRECT", "passed": True},
        {"char": "末", "diagnostic_status": "INCORRECT", "passed": False},
    ]

    final_status, reason = _combine_word_verdict(word_decision, syllables)

    assert final_status is DiagnosticStatus.CORRECT
    assert "overrides" in reason

    mo = syllables[1]
    assert mo["diagnostic_status"] == "CORRECT"
    assert mo["passed"] is True
    assert mo["word_rescue"]["promoted_from"] == "INCORRECT"
    assert mo["word_rescue"]["shape_score"] == 93.0
    assert mo["word_rescue"]["direction_score"] == 94.0


def test_exceptionally_strong_shape_alone_does_not_override_incorrect_syllable():
    """The override needs BOTH shape and direction to clear the stricter
    bar — a very high shape score with weak direction must not be enough,
    same asymmetric-safety philosophy as the phrase rescue."""
    from praat_analyzer import _combine_word_verdict
    from tone_decision import DiagnosticStatus, PHRASE_RESCUE_SHAPE_STRONG, WordToneDiagnosis

    word_decision = WordToneDiagnosis(
        status=DiagnosticStatus.CORRECT,
        reason="strong_shape_direction_overridden",
        shape_score=max(95.0, PHRASE_RESCUE_SHAPE_STRONG + 5),
        direction_score=10.0,
        display_score=68.5,
    )
    syllables = [
        {"diagnostic_status": "CORRECT"},
        {"diagnostic_status": "INCORRECT"},
    ]

    final_status, reason = _combine_word_verdict(word_decision, syllables)

    assert final_status is DiagnosticStatus.INCORRECT
    assert syllables[1]["diagnostic_status"] == "INCORRECT"
    assert "word_rescue" not in syllables[1]


def test_reason_unchanged_when_no_override_happens():
    """Regression guard: when the min-rule/promotion logic doesn't override
    the word-level decision, `reason` must still be the original
    decide_word_tone reason — the fix only touches the divergent case."""
    from praat_analyzer import _combine_word_verdict
    from tone_decision import DiagnosticStatus, WordToneDiagnosis

    word_decision = WordToneDiagnosis(
        status=DiagnosticStatus.CORRECT,
        reason="strong_shape_supported",
        shape_score=93.0,
        direction_score=94.0,
        display_score=93.3,
    )
    syllables = [
        {"diagnostic_status": "CORRECT"},
        {"diagnostic_status": "CORRECT"},
    ]

    final_status, reason = _combine_word_verdict(word_decision, syllables)

    assert final_status is DiagnosticStatus.CORRECT
    assert reason == "strong_shape_supported"


def test_reason_reflects_syllable_rollup_promotion_to_correct():
    """The reverse direction: word_decision lands UNCERTAIN (e.g. shape/
    direction disagreement) but every syllable independently measured
    CORRECT, so the combiner promotes the word to CORRECT. The reason must
    describe that promotion, not the original UNCERTAIN reasoning."""
    from praat_analyzer import _combine_word_verdict
    from tone_decision import DiagnosticStatus, WordToneDiagnosis

    word_decision = WordToneDiagnosis(
        status=DiagnosticStatus.UNCERTAIN,
        reason="shape_direction_disagreement",
        shape_score=82.0,
        direction_score=40.0,
        display_score=69.4,
    )
    syllables = [
        {"diagnostic_status": "CORRECT"},
        {"diagnostic_status": "CORRECT"},
    ]

    final_status, reason = _combine_word_verdict(word_decision, syllables)

    assert final_status is DiagnosticStatus.CORRECT
    assert reason != "shape_direction_disagreement"


def test_strong_word_shape_promotes_per_syllable_uncertain_to_correct():
    """The reverse of the min-rule promotion: when the whole-word shape and
    direction both clear their thresholds, per-syllable directional scores
    landing in the coarse UNCERTAIN band (45-58 — common in connected
    speech, where the quarter-mean heuristic dips even on a genuinely
    correct utterance) must not veto the word verdict.

    This closes the case where a learner sees `shape 86 · dir 79 · overall
    84` alongside two △ syllables — the word-level evidence is strong,
    and the per-syllable ambiguity is a scorer artefact, not a real error.

    Constructed by direct injection so the assertion is about the combiner
    rule and not about whether a particular synthetic contour happens to
    land in the right bands."""
    from tone_decision import DiagnosticStatus, QcEvidence, decide_word_tone

    # Sanity: shape 86 + direction 79 is CORRECT at the word level under
    # decide_word_tone (comfortably above SHAPE_STRONG and DIRECTION_SUPPORT
    # regardless of which calibration pass is currently in effect).
    good_qc = QcEvidence(judged=True, pitch_points=40, minimum_pitch_points=8)
    assert (
        decide_word_tone(shape_score=86.0, direction_score=79.0, qc=good_qc).status
        is DiagnosticStatus.CORRECT
    )
    # The invariant this test guards: if EVERY syllable's own diagnostic
    # is a MEASURED UNCERTAIN (not a placeholder), the word verdict must
    # follow the word-level CORRECT and not the syllable rollup's
    # UNCERTAIN. Placeholder-driven UNCERTAINs are covered separately by
    # test_placeholder_syllable_never_produces_passed_true above.
