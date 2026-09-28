"""Student-facing coaching must not grade tones (contour visualization only)."""

import pytest

from services.speech.feedback.pipeline import (
    _feedback_prompt,
    _prosody_for_coaching,
    fallback_language_feedback,
)

WORD_PROSODY = [
    {
        "token": "要",
        "start_time": 1.0,
        "end_time": 1.3,
        "contour_shape": "falling",
        "verdict": "INCORRECT",
        "diagnostic_status": "INCORRECT",
        "passed": False,
        "tone_accuracy": 20.0,
        "feedback": "Likely tone mismatch",
        "syllables": [
            {
                "char": "要",
                "tone": 4,
                "final": "iao",
                "diagnostic_status": "INCORRECT",
                "contour_match_score": 20.0,
                "passed": False,
            }
        ],
    }
]


@pytest.mark.parametrize("tone_accuracy", [0, 30, 65, 95])
def test_fallback_pronunciation_text_does_not_depend_on_tone_score(tone_accuracy):
    result = fallback_language_feedback(
        "我要看書",
        praat_tone_accuracy=tone_accuracy,
        praat_fluency_score=80,
        word_prosody=WORD_PROSODY,
    )
    tone_detail = next(d for d in result["pronunciation_note"]["details"] if d["key"] == "tone")
    assert "pitch line" in tone_detail["text"]
    assert not any("tone" in error.lower() for error in result["corrective_feedback"]["errors"])


def test_prosody_for_coaching_drops_verdicts_and_scores():
    coaching = _prosody_for_coaching(WORD_PROSODY)
    assert coaching == [
        {
            "token": "要",
            "start_time": 1.0,
            "end_time": 1.3,
            "contour_shape": "falling",
            "syllables": [{"char": "要", "tone": 4, "final": "iao"}],
        }
    ]


def test_llm_prompt_carries_no_tone_score_or_verdict():
    prompt = _feedback_prompt("我要看書", praat_tone_accuracy=42, word_prosody=WORD_PROSODY)
    assert "Tone accuracy" not in prompt
    assert "INCORRECT" not in prompt
    assert "contour_match_score" not in prompt
    assert "tone mismatch" not in prompt
