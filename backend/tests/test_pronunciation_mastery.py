import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import build_pronunciation_mastery


def _word(token, scores, *, judged=True):
    syllables = [
        {"char": str(index), "score": score, "passed": score >= 58}
        for index, score in enumerate(scores)
    ]
    return {
        "token": token,
        "judged": judged,
        "passed": all(item["passed"] for item in syllables) if judged else None,
        "syllables": syllables,
    }


def test_mastery_passes_only_when_every_measured_syllable_passes():
    result = build_pronunciation_mastery(
        [_word("妳" , [80]), _word("做什麼", [72, 76])],
        {"can_score_pronunciation": True},
    )

    assert result["passed"] is True
    assert result["status"] == "passed"
    assert result["passed_syllables"] == 3
    assert result["total_syllables"] == 3
    assert result["failed_words"] == []


def test_mastery_identifies_the_word_that_needs_practice():
    result = build_pronunciation_mastery(
        [_word("妳", [80]), _word("什麼", [42, 76])],
        {"can_score_pronunciation": True},
    )

    assert result["passed"] is False
    assert result["status"] == "needs_practice"
    assert result["passed_syllables"] == 2
    assert result["failed_words"] == ["什麼"]


def test_mastery_does_not_turn_unusable_audio_into_a_fail():
    result = build_pronunciation_mastery(
        [_word("妳", [0], judged=False)],
        {
            "can_score_pronunciation": False,
            "student_message": "Record again.",
        },
    )

    assert result["passed"] is False
    assert result["status"] == "not_judged"
    assert result["message"] == "Record again."


def test_mastery_ignores_a_word_without_measured_pitch_evidence():
    result = build_pronunciation_mastery(
        [
            _word("\u505a", [80]),
            {
                "token": "\u59b3",
                "judged": False,
                "passed": None,
                "syllables": [{"char": "\u59b3", "passed": None}],
            },
        ],
        {"can_score_pronunciation": True},
        content_match=True,
    )

    assert result["passed"] is True
    assert result["failed_words"] == []
    assert result["passed_syllables"] == 1
    assert result["total_syllables"] == 1


def test_mastery_cannot_pass_when_required_scene_content_is_missing():
    result = build_pronunciation_mastery(
        [_word("你這個週末要做什麼", [80] * 9)],
        {"can_score_pronunciation": True},
        content_match=False,
        missing_target_units=["友", "美"],
    )

    assert result["passed"] is False
    assert result["status"] == "needs_practice"
    assert result["missing_target_units"] == ["友", "美"]
    assert "友美" in result["message"]
