"""Attach strict model coaching to a server-resolved speaking attempt."""

import time

from services.pronunciation.rubric_evaluator import evaluate_rubric_pronunciation
from services.pronunciation.presenter import present_evaluation
from services.pronunciation.reference_source import resolve_reference_source


async def attach_pronunciation_feedback(
    payload: dict, audio: bytes, target: dict, difficulty_level: str,
    *, conversation_id: str = "", turn_id: str = "",
) -> dict:
    started_at = time.perf_counter()
    reference = resolve_reference_source(
        target["story_id"], target["scene_index"], difficulty_level=difficulty_level,
        conversation_id=conversation_id, turn_id=turn_id, expected_text=target["target_text"],
    )
    evaluation = await evaluate_rubric_pronunciation(
        student_audio=audio, reference_audio_path=reference.audio_path,
        reference_key=reference.reference_key, expected_text=target["target_text"],
    )
    result = present_evaluation(evaluation, include_debug=False)
    result["target_text"] = target["target_text"]
    result["reference"]["audio_url"] = reference.audio_url
    feedback = result["feedback"]
    provenance = {
        "requested_provider": feedback["model"],
        "executed_provider": feedback["model"],
        "fallback_used": False, "fallback_reason": None,
        "acoustic_context_used": True, "acoustic_context_supplied": True,
        "pronunciation_source": "wav2vec2_plus_praat_f0",
    }
    language = {**(payload.get("ai_feedback") or {})}
    pronunciation_dimension = result["dimensions"]["pronunciation"]
    language.update({
        "provider": feedback["model"],
        "pronunciation_score": pronunciation_dimension["score"],
        "pronunciation_errors": result.get("pronunciation_errors", []),
        "tone_errors": result.get("tone_errors", []),
        "pronunciation_note": {"score": pronunciation_dimension["score"], "feedback": feedback["summary"]},
        "corrective_feedback": {"errors": [], "hint": feedback["summary"], "reveal_answer": False, "correct_version": ""},
        "practice_prompt": feedback["practice_tip"],
        "feedback_provenance": provenance,
    })
    trace = {**(payload.get("processing_trace") or {})}
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    trace["stages"] = [*(trace.get("stages") or []), {
        "stage": "pronunciation_feedback", "status": "passed", "duration_ms": elapsed_ms,
        "model": feedback["model"], "provider": "openai",
        "detail": "Wav2Vec2 scores initial/final similarity; Praat scores tone, Fluency and Prosody separately; Luna explains.",
        "output": {"dimensions": result["dimensions"], "feedback_provenance": provenance},
    }]
    trace["total_duration_ms"] = round(trace.get("total_duration_ms", 0) + elapsed_ms, 1)
    # Content verification and progression remain the server's existing verdicts.
    return {**payload, "pronunciation_evaluation": result,
            "ai_feedback": language, "feedback": feedback["summary"],
            "feedback_provenance": provenance, "processing_trace": trace}
