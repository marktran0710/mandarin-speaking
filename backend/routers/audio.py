"""Audio record, speech analysis, and ASR transcription endpoints."""
import asyncio
import json
import tempfile
import os

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from ai_feedback import fallback_language_feedback, generate_language_feedback
from chinese_tones import calculate_tone_accuracy, detect_tone, generate_comprehensive_feedback
from config import ANALYZE_TIMEOUT_SECONDS, MAX_AUDIO_BYTES, check_rate_limit, logger
from database import connect_db, row_to_audio_record
from models import AnalysisResponse, AsrStatusResponse, AudioRecordRequest, TranscriptionResponse
from praat_analyzer import (
    analyze_all,
    analyze_fluency,
    calculate_speech_rate,
    estimate_word_prosody,
    extract_formants,
    extract_pitch,
    get_pitch_statistics,
)
from services.asr import (
    _ensure_vibevoice_load_started,
    _vibevoice_asr_model,
    _vibevoice_load_error,
    _vibevoice_load_lock,
    _vibevoice_load_thread,
    transcribe_audio_content,
)
from services.files import extension_from_upload, safe_file_stem, save_uploaded_audio
from config import AUDIO_UPLOAD_DIR

router = APIRouter()


# ── Audio records CRUD ─────────────────────────────────────────────────────

@router.get("/api/audio-records")
async def list_audio_records(
    limit: int = Query(default=200, ge=1, le=1000),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM audio_records ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        ).fetchall()
    return [row_to_audio_record(row) for row in rows]


@router.post("/api/audio-records")
async def create_audio_record(record: AudioRecordRequest):
    _save_audio_record(record)
    return record


@router.post("/api/audio-records/upload")
async def upload_audio_record(
    record: str = Form(...),
    file: UploadFile = File(...),
):
    try:
        audio_record = AudioRecordRequest.model_validate_json(record)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid audio record JSON") from exc
    audio_record.audioUrl = await save_uploaded_audio(file, audio_record.id)
    _save_audio_record(audio_record)
    return audio_record


@router.delete("/api/audio-records/{record_id}")
async def delete_audio_record(record_id: str):
    from services.files import remove_uploaded_file
    with connect_db() as db:
        row = db.execute(
            "SELECT audio_url FROM audio_records WHERE id = ?", (record_id,)
        ).fetchone()
        db.execute("DELETE FROM audio_records WHERE id = ?", (record_id,))
    if row and row["audio_url"]:
        remove_uploaded_file(row["audio_url"])
    return {"ok": True}


def _save_audio_record(record: AudioRecordRequest):
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO audio_records (
                id, timestamp, duration, transcription, model, topic_id,
                image_url, image_index, audio_url, praat_metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.timestamp,
                record.duration,
                record.transcription,
                record.model,
                record.topicId,
                record.imageUrl,
                record.imageIndex,
                record.audioUrl,
                json.dumps(record.praatMetrics),
            ),
        )


# ── ASR status ─────────────────────────────────────────────────────────────

@router.get("/api/asr-status", response_model=AsrStatusResponse)
async def get_asr_status():
    import services.asr as asr
    with asr._vibevoice_load_lock:
        if asr._vibevoice_asr_model is not None:
            return AsrStatusResponse(provider="vibevoice", status="ready",
                                     message="VibeVoice-ASR is ready.")
        if asr._vibevoice_load_error:
            return AsrStatusResponse(provider="vibevoice", status="error",
                                     message=f"VibeVoice-ASR failed to load: {asr._vibevoice_load_error}")
        if asr._vibevoice_load_thread is not None and asr._vibevoice_load_thread.is_alive():
            return AsrStatusResponse(provider="vibevoice", status="loading",
                                     message="VibeVoice-ASR is loading the local model weights.")
    return AsrStatusResponse(
        provider="vibevoice", status="idle",
        message="VibeVoice-ASR is not loaded. It starts only when a VibeVoice transcription request is submitted.",
    )


# ── Transcription endpoint ─────────────────────────────────────────────────

@router.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    model: str = Form("ctwhisper"),
):
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")
    try:
        content = await file.read()
        return await transcribe_audio_content(content, model)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in transcribe_speech")
        raise HTTPException(status_code=500, detail=f"Error transcribing speech: {exc}")


# ── Analysis endpoint ──────────────────────────────────────────────────────

@router.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_speech(
    file: UploadFile = File(...),
    transcription: str = Form(""),
    asr_model: str = Form(""),
    scene_prompt: str = Form(""),
    scene_vocabulary: str = Form(""),
    req: Request = None,
):
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")
    if req is not None:
        client_ip = req.client.host if req.client else "unknown"
        check_rate_limit(f"analyze:{client_ip}", max_requests=30, window_seconds=60)

    content = await file.read()
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum size is {MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
        )
    try:
        return await asyncio.wait_for(
            _do_analyze(content, transcription, asr_model, scene_prompt, scene_vocabulary),
            timeout=ANALYZE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Analysis timed out after {ANALYZE_TIMEOUT_SECONDS}s. Try a shorter recording.",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in analyze_speech")
        raise HTTPException(status_code=500, detail=f"Error analyzing speech: {exc}") from exc


async def _do_analyze(
    content: bytes,
    transcription: str,
    asr_model: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
) -> AnalysisResponse:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        transcription_model = ""
        if not transcription.strip() and asr_model.strip():
            result = await transcribe_audio_content(content, asr_model.strip())
            transcription = result.text
            transcription_model = result.model

        (praat_result, ai_feedback) = await asyncio.gather(
            run_in_threadpool(lambda: analyze_all(tmp_path, transcription)),
            generate_language_feedback(transcription, scene_prompt, scene_vocabulary),
        )
        (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
         word_prosody, detected_tone, tone_accuracy, feedback, pause_analysis) = praat_result

        vowel_quality = _classify_vowel_quality(formants)
        tone_direction = _build_tone_direction(pitch_contour, detected_tone, tone_accuracy)

        pron_patch = fallback_language_feedback(
            transcription, scene_prompt, scene_vocabulary,
            praat_tone_accuracy=float(tone_accuracy),
            praat_fluency_score=float(fluency_score),
            praat_vowel_quality=vowel_quality or "",
        )
        if isinstance(ai_feedback, dict):
            ai_feedback["pronunciation_note"] = pron_patch["pronunciation_note"]

        description = _build_analysis_description(transcription, transcription_model, word_prosody)
        return AnalysisResponse(
            description=description,
            transcription=transcription,
            transcription_model=transcription_model,
            pitch_contour=pitch_contour,
            word_prosody=word_prosody,
            detected_tone=detected_tone,
            tone_accuracy=tone_accuracy,
            formants=formants,
            vowel_quality=vowel_quality,
            speech_rate=speech_rate,
            fluency_score=fluency_score,
            pitch_statistics=pitch_stats,
            tone_direction=tone_direction,
            pause_analysis=pause_analysis,
            feedback=feedback,
            ai_feedback=ai_feedback,
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _classify_vowel_quality(formants: dict) -> str:
    f1 = formants.get("F1", 0)
    f2 = formants.get("F2", 0)
    if f1 <= 0 or f2 <= 0:
        return ""
    if f1 < 400:
        return ("High front vowel — mouth nearly closed, tongue forward (like 你 nǐ)"
                if f2 > 2000
                else "High back vowel — mouth nearly closed, lips rounded (like 書 shū)")
    if f1 < 650:
        if f2 > 1800:
            return "Mid front vowel — tongue mid-high, forward (like 姐 jiě)"
        if f2 > 1200:
            return "Mid central vowel — tongue in centre (like 的 de)"
        return "Mid back vowel — tongue mid, lips rounded (like 我 wǒ)"
    return "Open vowel — mouth wide open, jaw dropped (like 啊 ā / 媽 mā)"


def _build_tone_direction(pitch_contour: list, detected_tone: int, tone_accuracy: float) -> str:
    if not pitch_contour or len(pitch_contour) < 3:
        return ""
    freqs = [p[1] for p in pitch_contour]
    start = float(np.mean(freqs[:max(1, len(freqs) // 5)]))
    end   = float(np.mean(freqs[-max(1, len(freqs) // 5):]))
    mid   = float(np.mean(freqs[len(freqs) // 3: 2 * len(freqs) // 3]))
    delta = end - start
    dip   = (start + end) / 2 - mid
    tone_hints = {
        1: "Tone 1 should stay high and flat the whole time (→).",
        2: "Tone 2 should rise steadily from mid to high (↗).",
        3: "Tone 3 dips low in the middle then rises slightly (↘↗).",
        4: "Tone 4 should fall sharply from high to low (↘).",
    }
    if dip > 30:
        shape, arrow = "dips in the middle", "↘↗"
    elif delta > 25:
        shape, arrow = "rises", "↗"
    elif delta < -25:
        shape, arrow = "falls", "↘"
    else:
        shape, arrow = "stays roughly level", "→"
    quality = "Good match." if tone_accuracy >= 72 else "Needs more contrast."
    hint = tone_hints.get(detected_tone, "")
    return f"Your voice {shape} {arrow}. {quality} {hint}".strip()


def _build_analysis_description(
    transcription: str,
    transcription_model: str,
    word_prosody: list[dict],
) -> str:
    text = transcription.strip()
    if not text:
        return (
            "The audio was analyzed for pitch and fluency, but no transcript was "
            "returned. Try a clearer recording with one short sentence."
        )
    model_note = f" using {transcription_model}" if transcription_model else ""
    count = len(word_prosody)
    return (
        f"The system transcribed your recording{model_note} and found "
        f"{count} word-level prosody item{'s' if count != 1 else ''} for review."
    )
