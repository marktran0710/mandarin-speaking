import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import _scene_content_diff, _scene_content_match, build_pronunciation_mastery


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


def test_unverified_target_cannot_pass_pronunciation_mastery():
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
    assert result["passed"] is False
    assert "verify" in result["message"].lower()
