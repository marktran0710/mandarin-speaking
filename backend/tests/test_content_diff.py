import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import (
    _acoustic_scoring_source,
    _scene_content_diff,
    _scene_content_match,
    build_pronunciation_mastery,
)


def test_content_diff_marks_replacement():
    assert _scene_content_diff("abc", "axc") == [
        {"type": "match", "target": "a", "heard": "a"},
        {"type": "replace", "target": "b", "heard": "x"},
        {"type": "match", "target": "c", "heard": "c"},
    ]
    assert _scene_content_match("abc", "axc") is False


def test_content_diff_marks_missing_and_extra():
    assert _scene_content_diff("abcd", "acd")[1] == {
        "type": "missing",
        "target": "b",
        "heard": "",
    }
    assert _scene_content_diff("abcd", "abxcd")[1] == {
        "type": "extra",
        "target": "",
        "heard": "x",
    }


def test_empty_transcript_is_unverified_without_a_fake_diff():
    assert _scene_content_match("abc", "") is None
    assert _scene_content_diff("abc", "") == []


def test_unverified_target_fails_open_on_pronunciation_mastery():
    # A null content_match means the independent ASR verification check
    # errored, timed out, or ran without a configured model — not that the
    # student said the wrong thing. That should never cost them a pass that
    # their actual measured pronunciation earned.
    word = {
        "token": "abc",
        "passed": True,
        "syllables": [{"passed": True}],
    }
    result = build_pronunciation_mastery(
        [word],
        {"can_score_pronunciation": True},
        content_match=None,
        content_check_requested=True,
    )
    assert result["passed"] is True


def test_scoring_uses_the_scene_target_when_content_is_confirmed():
    assert _acoustic_scoring_source("你這個週末要做什麼", True) == "scene_target"


def test_scoring_uses_the_scene_target_when_content_check_is_unverified():
    # A None verdict means the content check never ran or couldn't confirm
    # anything (verify_word drill, empty transcript, ASR hiccup) — not that
    # the learner said the wrong thing. Falling back to the raw ASR
    # transcript here used to silently truncate scoring to whatever partial
    # text the ASR produced, undercounting the measured syllables for a
    # correctly-spoken attempt.
    assert _acoustic_scoring_source("你這個週末要做什麼", None) == "scene_target"


def test_scoring_falls_back_to_the_asr_transcript_on_a_confirmed_mismatch():
    # Only a confirmed False (real evidence of a mismatch) should give up the
    # known-correct sentence — scoring the full target against a wrong or
    # incomplete attempt would fabricate a score for words never said.
    assert _acoustic_scoring_source("你這個週末要做什麼", False) == "asr_transcript"


def test_scoring_falls_back_to_the_asr_transcript_without_a_scene_target():
    assert _acoustic_scoring_source("", None) == "asr_transcript"


def test_explicit_content_mismatch_still_blocks_pronunciation_mastery():
    word = {
        "token": "abc",
        "passed": True,
        "syllables": [{"passed": True}],
    }
    result = build_pronunciation_mastery(
        [word],
        {"can_score_pronunciation": True},
        content_match=False,
        content_check_requested=True,
    )
    assert result["passed"] is False
