"""Known-script pronunciation evaluation.

The sentence and the reference recording are resolved server-side from the
published story; the client sends only audio and which exercise it belongs to.
The result is informational: nothing here passes, fails or unlocks anything.
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

import security.auth as auth
from routers.verified_speaking import resolve_verified_speaking_target
from services.pronunciation.evaluator import EvaluationError
from services.pronunciation.rubric_evaluator import evaluate_rubric_pronunciation
from services.pronunciation.presenter import present_evaluation
from services.pronunciation.reference_source import resolve_reference_source

router = APIRouter()

STUDENT_VISIBLE_ENV = "PRONUNCIATION_SCORE_STUDENT_VISIBLE"
_TRUTHY = {"1", "true", "yes", "on"}
_STATUS_FOR_CODE = {
    "empty_audio": 400,
    "no_syllables": 422,
    "reference_audio_missing": 409,
    "reference_unreadable": 422,
    "reference_mismatch": 422,
}


def _student_score_visible() -> bool:
    return os.getenv(STUDENT_VISIBLE_ENV, "true").strip().lower() in _TRUTHY


def _main_module():
    # Lazy import avoids main/router initialisation cycles.
    import main

    return main


def _error(exc: EvaluationError) -> HTTPException:
    status = _STATUS_FOR_CODE.get(exc.code, 422)
    if exc.code == "llm_not_configured":
        status = 503
    elif exc.code == "rubric_policy_invalid":
        status = 503
    elif exc.code.startswith("llm_") or exc.code in {"invalid_reply", "missing_summary", "reply_not_an_object"}:
        status = 502
    return HTTPException(
        status_code=status,
        detail={"code": exc.code, "message": str(exc)},
    )


@router.post("/api/pronunciation/evaluate")
async def evaluate_speaking_pronunciation(
    request: Request,
    file: UploadFile = File(...),
    story_id: str = Form(..., min_length=1, max_length=200),
    scene_index: int = Form(..., ge=0),
    conversation_id: str = Form("", max_length=200),
    turn_id: str = Form("", max_length=128),
    turn_index: int | None = Form(None, ge=0),
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    is_student = identity.role == "student"
    if is_student and not _student_score_visible():
        raise HTTPException(
            status_code=403,
            detail={
                "code": "pronunciation_score_not_enabled",
                "message": "The pronunciation score is not enabled for students.",
            },
        )

    app_main = _main_module()
    client_ip = request.client.host if request.client else "unknown"
    app_main._check_rate_limit(f"pronunciation:{client_ip}", max_requests=30, window_seconds=60)

    content = await file.read()
    if len(content) > app_main._MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large.")
    if not content:
        raise _error(EvaluationError("empty_audio", "No audio was received."))

    # The target sentence is re-derived from the published story, never taken
    # from the client; this also validates the scene and conversation turn.
    target = resolve_verified_speaking_target(
        story_id, scene_index, "easy",
        conversation_id=conversation_id, turn_id=turn_id, turn_index=turn_index,
    )
    try:
        reference = resolve_reference_source(
            target["story_id"], target["scene_index"],
            conversation_id=conversation_id, turn_id=turn_id,
        )

        async def run():
            async with app_main.acquire_analysis_slot():
                return await evaluate_rubric_pronunciation(
                    student_audio=content,
                    reference_audio_path=reference.audio_path,
                    reference_key=reference.reference_key,
                    expected_text=target["target_text"],
                )

        evaluation = await asyncio.wait_for(run(), timeout=app_main.ANALYZE_TIMEOUT_SECONDS)
    except EvaluationError as exc:
        raise _error(exc) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Pronunciation evaluation timed out.") from exc

    result = present_evaluation(evaluation, include_debug=not is_student)
    result["reference"]["audio_url"] = reference.audio_url
    return result
