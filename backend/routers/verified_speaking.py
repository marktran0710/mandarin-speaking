"""Server-authoritative, stable speaking analysis for progression records."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import security.auth as auth
from db import connect_db
from repositories import verified_speech_repository as repo

router = APIRouter()

VERIFICATION_VERSION = "verified-speaking-stable-v1"
_TIER_SUFFIX = {"easy": "", "medium": "Medium", "hard": "Hard"}


def _main_module():
    # Lazy import avoids main/router initialization cycles and keeps this
    # module easy to exercise with a fake stable analyzer.
    import main

    return main


def _tier_value(frame: dict[str, Any], field: str, difficulty_level: str) -> Any:
    """Use a populated tier override, falling back to the base field."""
    suffix = _TIER_SUFFIX[difficulty_level]
    tier_value = frame.get(f"{field}{suffix}") if suffix else None
    return tier_value if tier_value not in (None, "", [], {}) else frame.get(field)


def _reference_curves(frame: dict[str, Any], vocabulary: str, difficulty_level: str) -> dict[str, list]:
    raw = _tier_value(frame, "sentenceReferenceCurves", difficulty_level)
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        parsed = None
    curves = {
        str(key): value
        for key, value in (parsed.items() if isinstance(parsed, dict) else [])
        if isinstance(value, list) and value
    }

    raw_word_curves = _tier_value(frame, "vocabularyReferenceCurves", difficulty_level)
    try:
        word_curves = json.loads(raw_word_curves) if isinstance(raw_word_curves, str) else raw_word_curves
    except (TypeError, json.JSONDecodeError):
        word_curves = None
    words = [word.strip() for word in (vocabulary or "").split(",") if word.strip()]
    if isinstance(word_curves, list):
        for word, curve in zip(words, word_curves):
            if isinstance(curve, list) and curve and word not in curves:
                curves[word] = curve
    return curves


def _load_published_scene(story_id: str, scene_index: int, difficulty_level: str) -> dict[str, Any]:
    with connect_db() as db:
        row = repo.find_published_scene(db, story_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Published story not found.")
    frames = row.get("frames") or []
    if scene_index >= len(frames) or not isinstance(frames[scene_index], dict):
        raise HTTPException(status_code=422, detail="Scene index is not valid for this published story.")
    frame = frames[scene_index]
    vocabulary = str(_tier_value(frame, "vocabulary", difficulty_level) or "")
    suggested_answer = str(_tier_value(frame, "suggestedAnswer", difficulty_level) or "")
    listen_script = str(_tier_value(frame, "listenScript", difficulty_level) or "")
    return {
        "story_id": row["id"], "scene_index": scene_index, "image_url": str(_tier_value(frame, "imageUrl", difficulty_level) or ""),
        "prompt": str(_tier_value(frame, "prompt", difficulty_level) or ""), "vocabulary": vocabulary,
        "phrases": str(_tier_value(frame, "phrases", difficulty_level) or ""),
        "suggested_answer": suggested_answer, "target_text": listen_script or suggested_answer,
        "reference_word_curves": _reference_curves(frame, vocabulary, difficulty_level),
    }


def _load_conversation_turns(story_id: str) -> list[dict[str, Any]] | None:
    with connect_db() as db:
        row = repo.find_published_conversation_turns(db, story_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Published story not found.")
    turns = row.get("conversation_turns")
    return turns if isinstance(turns, list) else None


def resolve_verified_speaking_target(
    story_id: str,
    scene_index: int,
    difficulty_level: str,
    *,
    conversation_id: str = "",
    turn_id: str = "",
    turn_index: int | None = None,
) -> dict[str, Any]:
    """Server-authoritative target resolution (Dual Speaking Modes plan,
    Epic 2). Never trust a client-submitted target sentence for verified
    scoring.

    No conversation identity -> the existing scene-based target (legacy
    Story Practice path, unchanged). Conversation identity present -> the
    student's OWN resolved turn's targetText, re-derived server-side from
    the published story's conversation_turns - never the scene's
    suggestedAnswer/listenScript, which is a different sentence belonging
    to a different (legacy) activity. A conversation turn also does not
    reuse the scene's reference pitch curves (Epic 2's "do not forge a
    reference curve" rule): those curves were recorded for the scene's own
    target sentence, not this turn's, so comparing against them would
    silently score the wrong contour.
    """
    scene = _load_published_scene(story_id, scene_index, difficulty_level)
    if not conversation_id and not turn_id:
        return scene

    turns = _load_conversation_turns(story_id)
    if not turns:
        raise HTTPException(status_code=422, detail="This story has no conversation turns to resolve.")

    if turn_index is not None:
        if (
            turn_index < 0
            or turn_index >= len(turns)
            or not isinstance(turns[turn_index], dict)
            or turns[turn_index].get("id") != turn_id
        ):
            raise HTTPException(status_code=422, detail="Conversation turn index does not match turn id.")
        turn = turns[turn_index]
    else:
        matches = [row for row in turns if isinstance(row, dict) and row.get("id") == turn_id]
        if len(matches) != 1:
            raise HTTPException(status_code=422, detail="Conversation turn id not found for this story.")
        turn = matches[0]

    if turn.get("speaker") != "student":
        raise HTTPException(status_code=422, detail="Only a student conversation turn can be analyzed as a response.")

    target_text = str(turn.get("targetText") or turn.get("text") or "").strip()
    if not target_text:
        raise HTTPException(status_code=422, detail="Conversation turn has no target text.")

    return {**scene, "target_text": target_text, "reference_word_curves": {}}


def _find_attempts(attempt_id: str) -> list[dict]:
    with connect_db() as db:
        return repo.find_attempts_by_id(db, attempt_id)


def _progress_verdicts(payload: dict[str, Any]) -> dict[str, bool]:
    mastery = payload.get("pronunciation_mastery") or {}
    # An unknown content result is not a pass. Policy 1 may ignore these
    # booleans, but policy 2 must never unlock on an unjudged content check.
    return {
        "pronunciationPassed": bool(mastery.get("passed")),
        "contentPassed": payload.get("content_match") is True,
        "masteryPassed": bool(mastery.get("passed")) and payload.get("content_match") is True,
    }


def _response(record_id: str, attempt_id: str, scene: dict[str, Any], difficulty_level: str, payload: dict[str, Any], audio_url: str | None = None) -> dict:
    return {
        "serverVerified": True,
        "audioRecordId": record_id,
        "attemptId": attempt_id,
        "storyId": scene["story_id"],
        "baseStoryId": scene["story_id"],
        "sceneIndex": scene["scene_index"],
        "difficultyLevel": difficulty_level,
        "audioUrl": audio_url,
        "progressionEligible": payload.get("progression_eligible") is not False,
        "analysis": payload,
        "verdicts": _progress_verdicts(payload),
    }


@router.post("/api/analyze/verified")
async def analyze_verified_speech(
    file: UploadFile = File(...),
    attempt_id: str = Form(..., min_length=1, max_length=200),
    story_id: str = Form("", max_length=200),
    base_story_id: str = Form("", max_length=200),
    scene_index: int = Form(..., ge=0),
    difficulty_level: str = Form("easy"),
    asr_model: str = Form(""),
    ai_provider: str = Form(""),
    transcription: str = Form(""),
    conversation_id: str = Form("", max_length=200),
    turn_id: str = Form("", max_length=128),
    turn_index: int | None = Form(None, ge=0),
    identity: auth.Identity = Depends(auth.require_student),
):
    if difficulty_level not in _TIER_SUFFIX:
        raise HTTPException(status_code=422, detail="difficulty_level must be easy, medium, or hard.")
    if not story_id and not base_story_id:
        raise HTTPException(status_code=422, detail="story_id or base_story_id is required.")
    if story_id and base_story_id and story_id != base_story_id:
        raise HTTPException(status_code=422, detail="story_id and base_story_id must identify the same story.")
    if file is None:
        raise HTTPException(status_code=400, detail="No audio file provided.")

    content = await file.read()
    app_main = _main_module()
    if len(content) > app_main._MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large.")
    audio_sha256 = hashlib.sha256(content).hexdigest()
    attempts = _find_attempts(attempt_id)
    if any(row.get("student_id") != identity.id for row in attempts):
        raise HTTPException(status_code=409, detail="Attempt already belongs to another student.")
    existing = next((row for row in attempts if row.get("server_verified_at") is not None), None)
    if existing is not None:
        if existing.get("audio_sha256") != audio_sha256:
            raise HTTPException(status_code=409, detail="Attempt ID was already used with different audio.")
        # The scene/turn is resolved even for a replay so the response cannot
        # echo forged client scene data and a removed/unpublished story or an
        # invalid conversation turn stays rejected.
        scene = resolve_verified_speaking_target(
            base_story_id or story_id, scene_index, difficulty_level,
            conversation_id=conversation_id, turn_id=turn_id, turn_index=turn_index,
        )
        if existing.get("topic_id") != scene["story_id"] or existing.get("image_index") != scene["scene_index"]:
            raise HTTPException(status_code=409, detail="Attempt ID was already used for a different scene.")
        return _response(existing["id"], attempt_id, scene, difficulty_level, existing.get("praat_metrics") or {}, existing.get("audio_url"))
    if attempts:
        raise HTTPException(status_code=409, detail="Attempt ID already exists without server verification.")

    scene = resolve_verified_speaking_target(
        base_story_id or story_id, scene_index, difficulty_level,
        conversation_id=conversation_id, turn_id=turn_id, turn_index=turn_index,
    )
    try:
        async def run_stable_analysis():
            async with app_main.acquire_analysis_slot():
                return await app_main._do_analyze(
                    content, transcription, asr_model, scene["prompt"], scene["vocabulary"], ai_provider,
                    scene["image_url"], scene["phrases"], scene["suggested_answer"],
                    scene_attempt_number=1,
                    verify_word="",
                    pinyin_hint="",
                    reference_word_curves=scene["reference_word_curves"],
                    scene_target_text=scene["target_text"],
                    attempt_id=attempt_id,
                )

        stable = await asyncio.wait_for(run_stable_analysis(), timeout=app_main.ANALYZE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Verified analysis timed out.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        app_main.logger.exception("Verified stable analysis failed")
        raise HTTPException(status_code=500, detail="Verified analysis failed.") from exc

    payload = stable.model_dump() if hasattr(stable, "model_dump") else stable.dict()
    record_id = str(uuid.uuid4())
    audio_url = ""
    try:
        await file.seek(0)
        audio_url = await app_main.save_uploaded_audio(file, record_id, identity.id)
        persisted = app_main.save_verified_audio_record(
            record_id=record_id, student_id=identity.id, attempt_id=attempt_id,
            audio_sha256=audio_sha256, verification_version=VERIFICATION_VERSION,
            topic_id=scene["story_id"], scene_index=scene["scene_index"], audio_url=audio_url,
            audio_name=audio_url.rsplit("/", 1)[-1], image_url=scene["image_url"],
            transcription=str(payload.get("transcription") or transcription),
            model=asr_model or "stable", praat_metrics=payload,
            conversation_id=conversation_id or None,
            turn_id=turn_id or None,
            turn_index=turn_index,
        )
    except Exception:
        if audio_url:
            app_main.remove_uploaded_file(audio_url)
        raise
    if persisted["id"] != record_id and audio_url:
        # A concurrent same-attempt request may have won the insert while this
        # request was analyzing. Its uploaded file is not referenced by the
        # returned canonical record and must be removed.
        app_main.remove_uploaded_file(audio_url)
    return _response(persisted["id"], attempt_id, scene, difficulty_level, payload, persisted.get("audio_url") or audio_url)
