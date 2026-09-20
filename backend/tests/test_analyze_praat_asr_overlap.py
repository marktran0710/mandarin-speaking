"""Praat should run CONCURRENTLY with ASR for whole-sentence practice (a known
scene_target_text, no verify_word), not sequentially after it - see the
overlap comment in main_parts/part_005.py. These tests prove the overlap
actually happens (timing) and that the rare confirmed-mismatch case still
falls back to scoring the real transcript, unchanged from before."""

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PRAAT_RESULT = ([], {}, 3.0, 72.0, {}, [], 2, 78.0, "Good tone.", {})
QUALITY = {
    "status": "reliable",
    "confidence": 1.0,
    "can_score_pronunciation": True,
    "can_score_content": True,
    "reason_codes": [],
    "student_message": "",
    "metrics": {},
}
LOCAL_FEEDBACK = {
    "provider": "local",
    "vocabulary_coverage": {"score": 80, "used": [], "missing": [], "feedback": ""},
    "coherence": {"score": 70, "feedback": "", "corrections": []},
    "pronunciation_note": {"score": 80, "feedback": ""},
    "improved_version": "",
    "practice_prompt": "",
}


def _common_patches(analyze_all_mock):
    return [
        patch("main.assess_recording_quality", return_value={
            "status": "reliable", "reason_codes": [], "student_message": "Sound check passed.",
        }),
        patch("main.resolve_image_b64", new_callable=AsyncMock, return_value=None),
        patch("main.analyze_all", analyze_all_mock),
        patch("main.generate_language_feedback", new_callable=AsyncMock, return_value=LOCAL_FEEDBACK),
        patch("main.finalize_feedback_quality", return_value=QUALITY),
        patch("main.classify_vowel_quality", return_value="Clear vowels"),
        patch("main.build_tone_direction", return_value="rising"),
        patch("main.caf_metrics.fluency_metrics", return_value={"articulation_rate": 3.0}),
        patch("main.caf_metrics.classify_pauses", return_value={"judged": False}),
        patch("services.ai_feedback.fallback_language_feedback", return_value=LOCAL_FEEDBACK),
        patch("services.ai_feedback.apply_feedback_quality_gate", side_effect=lambda value, *_a, **_k: value),
    ]


@pytest.mark.asyncio
async def test_praat_starts_before_asr_resolves_when_scene_target_is_known():
    import main

    asr_started_at = None
    asr_finished_at = None
    praat_started_at = None

    async def fake_transcribe(*_args, **_kwargs):
        nonlocal asr_started_at, asr_finished_at
        asr_started_at = time.perf_counter()
        await asyncio.sleep(0.08)
        asr_finished_at = time.perf_counter()
        return MagicMock(text="你這個週末要做什麼", model="ctwhisper")

    def fake_analyze_all(_path, _tx, **_kwargs):
        nonlocal praat_started_at
        praat_started_at = time.perf_counter()
        return PRAAT_RESULT

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("main.transcribe_audio_content", fake_transcribe))
        for cm in _common_patches(fake_analyze_all):
            stack.enter_context(cm)
        result = await main._do_analyze(
            b"wav-bytes", "", "ctwhisper",
            scene_target_text="你這個週末要做什麼",
        )

    assert praat_started_at is not None and asr_started_at is not None and asr_finished_at is not None
    # The whole point of the overlap: Praat must start while ASR is still in
    # flight, not after it resolves. Before this change, praat_started_at
    # would always be >= asr_finished_at.
    assert praat_started_at < asr_finished_at
    stages = {stage.stage: stage for stage in result.processing_trace.stages}
    assert stages["praat"].status == "passed"
    assert stages["asr"].status == "passed"


@pytest.mark.asyncio
async def test_confirmed_mismatch_still_scores_the_real_transcript():
    """The speculative pass scores sentence_target; if ASR later confirms the
    student said something else entirely, scoring must fall back to the real
    transcript (unchanged pre-existing contract) - not the discarded guess."""
    import main

    analyze_all_calls: list[str] = []

    async def fake_transcribe(*_args, **_kwargs):
        return MagicMock(text="今天天氣很好", model="ctwhisper")  # nothing like the target

    def fake_analyze_all(_path, tx, **_kwargs):
        analyze_all_calls.append(tx)
        return PRAAT_RESULT

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("main.transcribe_audio_content", fake_transcribe))
        for cm in _common_patches(fake_analyze_all):
            stack.enter_context(cm)
        result = await main._do_analyze(
            b"wav-bytes", "", "ctwhisper",
            scene_target_text="你這個週末要做什麼",
        )

    # The speculative (discarded) pass scored the scene target; a second,
    # real pass must score what was actually said. Thread-scheduling order
    # between the two isn't guaranteed, so assert the set, not the sequence.
    assert sorted(analyze_all_calls) == sorted(["你這個週末要做什麼", "今天天氣很好"])
    assert result.content_match is False


@pytest.mark.asyncio
async def test_word_practice_verify_word_path_is_unaffected():
    """verify_word drills (transcription pre-supplied, no scene_target_text)
    must not speculate at all - same single Praat pass as before."""
    import main

    analyze_all_calls: list[str] = []

    async def fake_verify(*_args, **_kwargs):
        return ("你好", True)

    def fake_analyze_all(_path, tx, **_kwargs):
        analyze_all_calls.append(tx)
        return PRAAT_RESULT

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("main._verify_word_transcription", fake_verify))
        for cm in _common_patches(fake_analyze_all):
            stack.enter_context(cm)
        result = await main._do_analyze(
            b"wav-bytes", "你好", "",
            verify_word="你好",
        )

    assert analyze_all_calls == ["你好"]
    assert result.processing_trace.stages[-1].stage in {"quality_gate"}
