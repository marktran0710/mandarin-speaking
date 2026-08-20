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


def test_mastery_passes_when_every_measured_syllable_passes():
    result = build_pronunciation_mastery(
        [_word("妳" , [80]), _word("做什麼", [72, 76])],
        {"can_score_pronunciation": True},
    )

    assert result["passed"] is True
    assert result["status"] == "passed"
    assert result["passed_syllables"] == 3
    assert result["total_syllables"] == 3
    assert result["failed_words"] == []


def test_mastery_passes_at_or_above_the_eighty_percent_pass_rate():
    """A recording clears the sentence-level pronunciation gate when at
    least 80% of judged syllables passed — students no longer have to hit
    every syllable to move on, but the failed word still surfaces in
    `failed_words` / `practice_parts` so they can drill it if they want."""
    # 8 pass out of 10 = 80% exactly — clears the gate.
    scores = [80] * 8 + [42, 40]
    result = build_pronunciation_mastery(
        [_word("十字", scores)],
        {"can_score_pronunciation": True},
    )
    assert result["passed"] is True
    assert result["status"] == "passed"
    assert result["passed_syllables"] == 8
    assert result["total_syllables"] == 10
    # Failed word is still surfaced so the student can optionally practise it.
    assert "十字" in result["failed_words"]
    assert "十字" in result["practice_parts"]


def test_mastery_fails_below_the_eighty_percent_pass_rate():
    """Anything under 80% syllables passing counts as needs-practice."""
    # 7/10 = 70% — under the bar.
    scores = [80] * 7 + [42] * 3
    result = build_pronunciation_mastery(
        [_word("十字", scores)],
        {"can_score_pronunciation": True},
    )
    assert result["passed"] is False
    assert result["status"] == "needs_practice"
    assert result["passed_syllables"] == 7
    assert result["total_syllables"] == 10


def test_mastery_identifies_the_word_that_needs_practice():
    """A short sentence where 2/3 syllables pass = 66.7% — under the bar,
    so the gate blocks and the failed word is surfaced for practice."""
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


def test_uncertain_syllables_do_not_count_against_the_sentence_gate():
    """UNCERTAIN ("not clear enough to judge") is not negative evidence —
    only INCORRECT (a likely tone mismatch) or INVALID_AUDIO (unusable
    recording) should count against the 80% sentence gate. Regression test:
    audio that used to pass started failing once the per-syllable diagnostic
    verdict collapsed UNCERTAIN and INCORRECT into the same passed=False,
    making an unmeasurable syllable indistinguishable from an actual tone
    mismatch at the sentence-gate level."""
    word = {
        "token": "友美",
        "judged": True,
        "passed": False,
        "syllables": [
            {"char": "友", "passed": True, "diagnostic_status": "CORRECT"},
            {"char": "美", "passed": False, "diagnostic_status": "UNCERTAIN"},
        ],
    }
    result = build_pronunciation_mastery([word], {"can_score_pronunciation": True})

    assert result["passed"] is True
    assert result["status"] == "passed"
    assert result["passed_syllables"] == 2
    assert result["total_syllables"] == 2
    # Still surfaced as optional practice even though the sentence passed.
    assert "友美" in result["failed_words"]


def test_neutral_syllables_are_visible_but_excluded_from_mastery_counts():
    word = {
        "token": "嗎",
        "passed": False,
        "syllables": [
            {"char": "嗎", "passed": False, "diagnostic_status": "UNCERTAIN", "score_provenance": "neutral_not_measured"},
        ],
    }
    measured = {
        "token": "好",
        "passed": True,
        "syllables": [
            {"char": "好", "passed": True, "diagnostic_status": "CORRECT", "score_provenance": "measured"},
        ],
    }

    result = build_pronunciation_mastery([word, measured], {"can_score_pronunciation": True})

    assert result["passed"] is True
    assert result["passed_syllables"] == 1
    assert result["total_syllables"] == 1
    assert result["failed_words"] == []


def test_incorrect_syllables_still_fail_the_sentence_gate():
    word = {
        "token": "妳",
        "judged": True,
        "passed": False,
        "syllables": [
            {"char": "妳", "passed": False, "diagnostic_status": "INCORRECT"},
        ],
    }
    result = build_pronunciation_mastery([word], {"can_score_pronunciation": True})

    assert result["passed"] is False
    assert result["status"] == "needs_practice"
    assert result["passed_syllables"] == 0


def test_invalid_audio_syllables_still_fail_the_sentence_gate():
    word = {
        "token": "妳",
        "judged": True,
        "passed": False,
        "syllables": [
            {"char": "妳", "passed": False, "diagnostic_status": "INVALID_AUDIO"},
        ],
    }
    result = build_pronunciation_mastery([word], {"can_score_pronunciation": True})

    assert result["passed"] is False
    assert result["status"] == "needs_practice"


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
