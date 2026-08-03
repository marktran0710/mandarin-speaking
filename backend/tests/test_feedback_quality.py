"""Safety-contract tests for student-facing voice feedback."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from fixtures import SILENT_WAV, SPEECH_WAV


def test_silence_is_retry_and_cannot_be_scored():
    from main import assess_recording_quality

    quality = assess_recording_quality(SILENT_WAV)

    assert quality["status"] == "retry"
    assert quality["can_score_pronunciation"] is False
    assert quality["can_score_content"] is False
    assert "signal_too_quiet" in quality["reason_codes"]
    assert "insufficient_speech" in quality["reason_codes"]


@pytest.mark.asyncio
async def test_silence_never_reaches_direct_audio_ai_or_language_ai(monkeypatch):
    import ai_feedback
    import main

    monkeypatch.setattr(main, "GEMINI_API_KEY", "test-key")
    empty_analysis = (
        [],  # pitch contour
        {},  # formants
        0.0,  # speech rate
        0.0,  # fluency
        {},  # pitch stats
        [],  # word prosody
        0,  # detected tone
        0.0,  # tone accuracy
        "",  # feedback
        {
            "pause_count": 0,
            "total_pause_duration": 0.0,
            "longest_pause": 0.0,
            "utterance_count": 0,
            "mean_utterance_duration": 0.0,
            "speaking_duration": 0.0,
            "pauses": [],
            "utterances": [],
        },
    )

    with (
        patch.object(
            ai_feedback,
            "assess_audio_with_gemini",
            new_callable=AsyncMock,
        ) as audio_ai,
        patch.object(
            main,
            "generate_language_feedback",
            new_callable=AsyncMock,
        ) as language_ai,
        patch.object(main, "analyze_all", return_value=empty_analysis),
        patch.object(
            main,
            "resolve_image_b64",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        result = await main._do_analyze(
            SILENT_WAV,
            transcription="",
            asr_model="",
            ai_provider="gemini",
        )

    audio_ai.assert_not_awaited()
    language_ai.assert_not_awaited()
    assert result.feedback_quality.status == "retry"
    assert result.ai_feedback["pronunciation_note"]["judged"] is False


def test_audible_signal_needs_post_analysis_before_it_can_be_scored():
    from main import assess_recording_quality

    quality = assess_recording_quality(SPEECH_WAV)

    assert quality["status"] == "review"
    assert quality["can_score_pronunciation"] is False
    assert "awaiting_acoustic_analysis" in quality["reason_codes"]
    assert "low_signal_variation" in quality["reason_codes"]


def test_open_story_audio_is_review_only_without_independent_content_check():
    from main import assess_recording_quality, finalize_feedback_quality

    preflight = assess_recording_quality(SPEECH_WAV)
    pitch = [(index * 0.02, 200.0 + index) for index in range(20)]
    quality = finalize_feedback_quality(preflight, pitch, "我喜歡喝水")

    assert quality["status"] == "review"
    assert quality["can_score_pronunciation"] is True
    assert quality["can_score_content"] is False
    assert "content_not_independently_verified" in quality["reason_codes"]


def test_verified_target_can_be_reliable():
    from main import finalize_feedback_quality

    preflight = {
        "status": "review",
        "confidence": 0.7,
        "can_score_pronunciation": False,
        "can_score_content": False,
        "reason_codes": ["awaiting_acoustic_analysis"],
        "metrics": {},
    }
    pitch = [(index * 0.02, 200.0 + index) for index in range(20)]
    quality = finalize_feedback_quality(
        preflight,
        pitch,
        "喝水",
        content_match=True,
        content_was_verified=True,
    )

    assert quality["status"] == "reliable"
    assert quality["can_score_pronunciation"] is True
    assert quality["can_score_content"] is True


def test_sustained_tone_never_becomes_reliable_mastery_evidence():
    from main import assess_recording_quality, finalize_feedback_quality

    preflight = assess_recording_quality(SPEECH_WAV)
    pitch = [(index * 0.02, 220.0) for index in range(20)]
    quality = finalize_feedback_quality(
        preflight,
        pitch,
        "喝水",
        content_match=True,
        content_was_verified=True,
    )

    assert quality["status"] == "review"
    assert quality["can_score_content"] is False
    assert "low_signal_variation" in quality["reason_codes"]


def test_unverified_target_cannot_receive_pronunciation_score():
    from main import assess_recording_quality, finalize_feedback_quality

    preflight = assess_recording_quality(SPEECH_WAV)
    pitch = [(index * 0.02, 200.0 + index) for index in range(20)]
    quality = finalize_feedback_quality(
        preflight,
        pitch,
        "喝水",
        content_match=None,
        content_was_verified=True,
    )

    assert quality["status"] == "review"
    assert quality["can_score_pronunciation"] is False
    assert "target_content_unverified" in quality["reason_codes"]


def test_feedback_quality_serializes_stable_contract_and_defaults_are_isolated():
    from main import FeedbackQuality

    first = FeedbackQuality()
    second = FeedbackQuality()
    first.reason_codes.append("changed")
    first.metrics.pitch_points = 99

    assert second.reason_codes == []
    assert second.metrics.pitch_points == 0
    assert set(second.model_dump()) == {
        "status",
        "confidence",
        "can_score_pronunciation",
        "can_score_content",
        "reason_codes",
        "student_message",
        "metrics",
    }


def test_feedback_gate_replaces_unsupported_claims_with_retry_message():
    from ai_feedback import apply_feedback_quality_gate

    feedback = {
        "provider": "ai",
        "vocabulary_coverage": {
            "score": 100,
            "used": ["喝水"],
            "missing": [],
            "feedback": "Perfect.",
        },
        "coherence": {"score": 100, "feedback": "Perfect.", "corrections": []},
        "pronunciation_note": {"score": 100, "feedback": "Perfect."},
        "improved_version": "喝水",
    }
    quality = {
        "status": "retry",
        "confidence": 0,
        "can_score_pronunciation": False,
        "can_score_content": False,
        "reason_codes": ["insufficient_speech"],
        "student_message": "Please record again.",
    }

    result = apply_feedback_quality_gate(
        feedback,
        quality,
        transcription="喝水",
        scene_vocabulary="喝水",
    )

    assert result["pronunciation_note"]["judged"] is False
    assert result["pronunciation_note"]["score"] == 0
    assert result["vocabulary_coverage"]["judged"] is False
    assert result["coherence"]["judged"] is False
    assert result["content_accuracy"]["judged"] is False
    assert result["improved_version"] == ""


def test_feedback_gate_sanitizes_vocab_lists_to_teacher_vocabulary():
    from ai_feedback import apply_feedback_quality_gate

    feedback = {
        "provider": "ai",
        "vocabulary_coverage": {
            "score": 100,
            "used": ["invented", "喝水"],
            "missing": ["also-invented"],
            "feedback": "AI text",
        },
        "pronunciation_note": {"score": 80, "feedback": "Grounded later by Praat."},
    }
    quality = {
        "status": "reliable",
        "confidence": 0.9,
        "can_score_pronunciation": True,
        "can_score_content": True,
        "reason_codes": [],
    }

    result = apply_feedback_quality_gate(
        feedback,
        quality,
        transcription="我喝水",
        scene_vocabulary="喝水,吃飯",
    )

    assert result["vocabulary_coverage"]["used"] == ["喝水"]
    assert result["vocabulary_coverage"]["missing"] == ["吃飯"]
    assert result["vocabulary_coverage"]["score"] == 50


def test_content_acceptance_is_derived_from_score_not_llm_boolean():
    from ai_feedback import _normalize_feedback

    low = _normalize_feedback(
        {"content_accuracy": {"score": 20, "accepted": "true"}}
    )
    high = _normalize_feedback(
        {"content_accuracy": {"score": 90, "accepted": "false"}}
    )

    assert low["content_accuracy"]["accepted"] is False
    assert high["content_accuracy"]["accepted"] is True
