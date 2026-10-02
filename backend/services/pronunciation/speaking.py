"""Compose the lightweight student speaking result.

The student speaking flow deliberately has three outputs only: Praat/ASR
metrics for visualisation, one OMPAL score request, and AI feedback grounded in
those Praat measurements. The heavier local pronunciation rubric remains
available through the dedicated pronunciation endpoint for staff/admin use.
"""

from __future__ import annotations

import time
from typing import Any

from services.pronunciation.ompal import assess_ompal


SPEAKING_EVALUATION_VERSION = "ompal-praat-ai-v1"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _ai_feedback_view(payload: dict[str, Any]) -> dict[str, Any]:
    """Adapt the existing speaking AI payload to the pronunciation contract."""
    ai_feedback = payload.get("ai_feedback") or {}
    if not isinstance(ai_feedback, dict):
        ai_feedback = {}
    pronunciation_note = ai_feedback.get("pronunciation_note")
    pronunciation_note = pronunciation_note if isinstance(pronunciation_note, dict) else {}
    corrective = ai_feedback.get("corrective_feedback")
    corrective = corrective if isinstance(corrective, dict) else {}
    provenance = payload.get("feedback_provenance") or {}
    provenance = provenance if isinstance(provenance, dict) else {}

    summary = (
        _text(ai_feedback.get("summary"))
        or _text(corrective.get("hint"))
        or _text(pronunciation_note.get("feedback"))
        or _text(payload.get("feedback"))
        or "Listen to the Praat voice visualisation and try the sentence again."
    )
    practice_tip = (
        _text(ai_feedback.get("practice_prompt"))
        or _text(corrective.get("hint"))
        or "Repeat the sentence while matching the model's pitch and rhythm."
    )
    executed_provider = _text(provenance.get("executed_provider")) or _text(ai_feedback.get("provider")) or "local"
    return {
        "summary": summary,
        "focus_words": [],
        "practice_tip": practice_tip,
        "source": "local" if executed_provider == "local" else "llm",
        "model": executed_provider,
    }


def _evaluation_from_ompal(
    *, target_text: str, ompal: dict[str, Any], ai_feedback: dict[str, Any],
) -> dict[str, Any]:
    scores = ompal.get("scores") if ompal.get("status") == "scored" else {}
    scores = scores if isinstance(scores, dict) else {}
    scored = ompal.get("status") == "scored"
    return {
        "target_text": target_text,
        "status": "scored" if scored else "unscorable",
        "reason": None if scored else ompal.get("reason", "ompal_unavailable"),
        "pronunciation_score": scores.get("accuracy"),
        "fluency_score": scores.get("fluency"),
        "prosody_score": scores.get("prosody"),
        "metrics": {},
        "words": [],
        "feedback": ai_feedback,
        "model": {
            "scoring_version": SPEAKING_EVALUATION_VERSION,
            "acoustic_pipeline_version": "praat",
            "feedback_model": ai_feedback.get("model"),
            "feedback_source": ai_feedback.get("source", "local"),
        },
        "reference": {"key": "ompal_api", "cache_hit": False},
        "ompal_comparison": ompal,
    }


async def attach_pronunciation_feedback(
    payload: dict[str, Any], audio: bytes, target: dict[str, Any], difficulty_level: str,
    *, conversation_id: str = "", turn_id: str = "",
) -> dict[str, Any]:
    """Attach OMPAL and reuse the already-computed Praat AI feedback."""
    del difficulty_level, conversation_id, turn_id
    started_at = time.perf_counter()
    ompal = await assess_ompal(audio, target["target_text"])
    ai_feedback = _ai_feedback_view(payload)
    evaluation = _evaluation_from_ompal(
        target_text=target["target_text"], ompal=ompal, ai_feedback=ai_feedback,
    )

    trace = {**(payload.get("processing_trace") or {})}
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    trace["stages"] = [*(trace.get("stages") or []), {
        "stage": "speaking_evaluation", "status": "passed", "duration_ms": elapsed_ms,
        "model": ompal.get("model_version") if ompal.get("status") == "scored" else "ompal_api",
        "provider": "ompal_api",
        "detail": "OMPAL score attached; Praat visualisation and AI feedback came from the shared speaking pipeline.",
        "output": {
            "ompal_comparison": ompal,
            "feedback_provenance": payload.get("feedback_provenance") or {},
        },
    }]
    trace["total_duration_ms"] = round(trace.get("total_duration_ms", 0) + elapsed_ms, 1)

    provenance = payload.get("feedback_provenance") or {
        "requested_provider": "local",
        "executed_provider": "local",
        "fallback_used": False,
        "fallback_reason": None,
        "acoustic_context_used": True,
        "acoustic_context_supplied": True,
        "pronunciation_source": "praat_acoustic_measurements",
    }
    return {
        **payload,
        "pronunciation_evaluation": evaluation,
        "feedback_provenance": provenance,
        "processing_trace": trace,
    }
