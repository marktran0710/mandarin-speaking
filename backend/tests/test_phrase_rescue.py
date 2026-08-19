"""Phrase-context rescue: a teacher-designated target phrase (e.g. "這個週末")
that jieba splits into more than one word is re-scored as one combined span.

Motivation (from a real live session): 這個週末 was recorded correctly, but
jieba split it into 這個 + 週末. The word-boundary split cut 末's pitch window
right at the split point, distorting its measured contour independently of
末's own diagnostic_status — the whole-word verdict for 週末 came back
INCORRECT purely from that one syllable, even though the combined 這個週末
span reads as a much better match. `_apply_phrase_rescue` re-scores the
combined span and, when the combined evidence clears a bar stricter than the
normal per-word promotion, promotes even an individually INCORRECT syllable.

This is a rescue, never a downgrade, and never for placeholder syllables
(neutral tone / too-short-to-measure) or invalid audio — those exemptions
mirror the ones `_combine_word_verdict` already enforces at the word level.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from praat_analyzer import _apply_phrase_rescue, _clean_target_phrases, _find_contiguous_token_run
from tone_decision import PHRASE_RESCUE_DIRECTION_SUPPORT, PHRASE_RESCUE_SHAPE_STRONG


def _syllable(char, tone, status, *, provenance="measured", score=50.0):
    return {
        "char": char,
        "tone": tone,
        "score": score,
        "passed": status == "CORRECT",
        "diagnostic_status": status,
        "diagnostic_reason": "test_fixture",
        "score_provenance": provenance,
    }


def _segment(token, syllables, verdict, *, pitch_contour=None):
    return {
        "token": token,
        "syllables": syllables,
        "verdict": verdict,
        "diagnostic_status": verdict,
        "passed": verdict == "CORRECT",
        "reason": "test_fixture",
        "pitch_contour": pitch_contour or [(float(i) * 0.01, 250.0) for i in range(20)],
    }


# A pitch contour whose directional evidence unambiguously matches T4+T4+T1+T4
# (falling, falling, level, falling) so the merged-phrase shape/direction both
# clear PHRASE_RESCUE_SHAPE_STRONG/PHRASE_RESCUE_DIRECTION_SUPPORT regardless
# of exactly where those bars are calibrated.
def _strong_merged_contour():
    import numpy as np

    def falling(n):
        return list(300.0 - 100.0 * np.linspace(0, 1, n))

    def level(n):
        return [230.0] * n

    points = []
    t = 0.0
    for block in (falling(20), falling(20), level(20), falling(20)):
        for hz in block:
            points.append((round(t, 3), hz))
            t += 0.01
    return points


def test_clean_target_phrases_filters_and_dedupes():
    assert _clean_target_phrases(["這個週末", " 這個週末 ", "", "hello", None]) == [
        "這個週末"
    ]


def test_clean_target_phrases_handles_none():
    assert _clean_target_phrases(None) == []


def test_find_contiguous_token_run_matches_adjacent_tokens():
    assert _find_contiguous_token_run(["友美", "妳", "這個", "週末", "要"], "這個週末") == (2, 4)


def test_find_contiguous_token_run_returns_none_when_not_contiguous():
    # "這個" and "要" are not adjacent, so no run joins to "這個要".
    assert _find_contiguous_token_run(["這個", "週末", "要"], "這個要") is None


def test_rescue_promotes_incorrect_syllable_when_merged_evidence_is_strong():
    """The core case: 末 measured INCORRECT on its own, but the combined
    這個週末 span clears the strict phrase-rescue bar."""
    contour = _strong_merged_contour()
    zhege = _segment(
        "這個",
        [_syllable("這", 4, "CORRECT"), _syllable("個", 4, "CORRECT")],
        "CORRECT",
        pitch_contour=contour[:40],
    )
    weimo = _segment(
        "週末",
        [_syllable("週", 1, "CORRECT"), _syllable("末", 4, "INCORRECT")],
        "INCORRECT",
        pitch_contour=contour[40:],
    )
    segments = [zhege, weimo]

    _apply_phrase_rescue(segments, ["這個週末"])

    mo = weimo["syllables"][1]
    assert mo["diagnostic_status"] == "CORRECT"
    assert mo["passed"] is True
    assert mo["phrase_rescue"]["phrase"] == "這個週末"
    assert mo["phrase_rescue"]["promoted_from"] == "INCORRECT"
    assert weimo["verdict"] == "CORRECT"
    assert weimo["passed"] is True
    assert weimo["reason"] == "phrase_context_rescued"


def test_rescue_does_not_trigger_below_the_strict_bar():
    """A weak/ambiguous merged contour must not rescue anything — the whole
    point of the stricter bar is that ordinary word-level evidence is not
    enough to override an individually-measured INCORRECT syllable."""
    flat_contour = [(float(i) * 0.01, 200.0 + (i % 3)) for i in range(80)]
    zhege = _segment(
        "這個",
        [_syllable("這", 4, "CORRECT"), _syllable("個", 4, "CORRECT")],
        "CORRECT",
        pitch_contour=flat_contour[:40],
    )
    weimo = _segment(
        "週末",
        [_syllable("週", 1, "CORRECT"), _syllable("末", 4, "INCORRECT")],
        "INCORRECT",
        pitch_contour=flat_contour[40:],
    )
    segments = [zhege, weimo]

    _apply_phrase_rescue(segments, ["這個週末"])

    assert weimo["syllables"][1]["diagnostic_status"] == "INCORRECT"
    assert weimo["verdict"] == "INCORRECT"
    assert "phrase_rescue" not in weimo["syllables"][1]


def test_rescue_never_promotes_a_placeholder_syllable():
    """A neutral-tone syllable inside a rescued run stays UNCERTAIN — it has
    no contour target to have been "rescued" against, mirroring the same
    exemption `_combine_word_verdict` applies at the word level."""
    contour = _strong_merged_contour()
    zuo = _segment(
        "做",
        [_syllable("做", 4, "INCORRECT")],
        "INCORRECT",
        pitch_contour=contour[:20],
    )
    sheme = _segment(
        "什麼",
        [
            _syllable("什", 2, "INCORRECT"),
            _syllable("麼", 5, "UNCERTAIN", provenance="neutral_not_measured"),
        ],
        "INCORRECT",
        pitch_contour=contour[20:],
    )
    segments = [zuo, sheme]

    _apply_phrase_rescue(segments, ["做什麼"])

    me = sheme["syllables"][1]
    assert me["diagnostic_status"] == "UNCERTAIN"
    assert "phrase_rescue" not in me


def test_rescue_never_touches_invalid_audio():
    """A recording that's unusable for one syllable in the run must block
    the whole rescue — wider context cannot fix bad audio."""
    contour = _strong_merged_contour()
    zhege = _segment(
        "這個",
        [_syllable("這", 4, "CORRECT"), _syllable("個", 4, "INVALID_AUDIO")],
        "INVALID_AUDIO",
        pitch_contour=contour[:40],
    )
    weimo = _segment(
        "週末",
        [_syllable("週", 1, "CORRECT"), _syllable("末", 4, "INCORRECT")],
        "INCORRECT",
        pitch_contour=contour[40:],
    )
    segments = [zhege, weimo]

    _apply_phrase_rescue(segments, ["這個週末"])

    assert weimo["syllables"][1]["diagnostic_status"] == "INCORRECT"
    assert "phrase_rescue" not in weimo["syllables"][1]


def test_rescue_skips_a_phrase_that_is_already_one_token():
    """Nothing to merge when jieba already grouped the phrase as one word."""
    contour = _strong_merged_contour()
    one_word = _segment(
        "這個",
        [_syllable("這", 4, "INCORRECT"), _syllable("個", 4, "CORRECT")],
        "INCORRECT",
        pitch_contour=contour,
    )
    segments = [one_word]

    _apply_phrase_rescue(segments, ["這個"])

    assert one_word["syllables"][0]["diagnostic_status"] == "INCORRECT"


def test_rescue_skips_when_run_is_already_all_correct():
    """No-op when there is nothing to rescue — avoids doing unnecessary work
    and, more importantly, never re-labels an already-CORRECT verdict."""
    contour = _strong_merged_contour()
    zhege = _segment(
        "這個",
        [_syllable("這", 4, "CORRECT"), _syllable("個", 4, "CORRECT")],
        "CORRECT",
        pitch_contour=contour[:40],
    )
    weimo = _segment(
        "週末",
        [_syllable("週", 1, "CORRECT"), _syllable("末", 4, "CORRECT")],
        "CORRECT",
        pitch_contour=contour[40:],
    )
    segments = [zhege, weimo]
    original_reason = weimo["reason"]

    _apply_phrase_rescue(segments, ["這個週末"])

    assert weimo["reason"] == original_reason


def test_thresholds_are_stricter_than_the_normal_word_level_bars():
    """The whole safety argument for allowing this mechanism to override an
    individually-measured INCORRECT syllable depends on it demanding more
    evidence than an ordinary word-level promotion, not the same or less."""
    from tone_decision import DIRECTION_SUPPORT, SHAPE_STRONG

    assert PHRASE_RESCUE_SHAPE_STRONG >= SHAPE_STRONG
    assert PHRASE_RESCUE_DIRECTION_SUPPORT >= DIRECTION_SUPPORT
