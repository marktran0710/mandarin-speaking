from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Tuple
import base64
import os
import tempfile
import httpx
from dotenv import load_dotenv
import json
import asyncio
import numpy as np
import threading
import datetime
from urllib.parse import quote, unquote_to_bytes
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from database import (
    connect_db,
    init_db,
    row_to_audio_record,
    row_to_custom_story,
    row_to_help_request,
)

from praat_analyzer import (
    extract_pitch,
    extract_formants,
    calculate_speech_rate,
    analyze_fluency,
    get_pitch_statistics,
    estimate_word_prosody,
    analyze_all,
)
from chinese_tones import (
    detect_tone,
    calculate_tone_accuracy,
    get_reference_tone_pattern,
    generate_comprehensive_feedback,
)
from ai_feedback import generate_language_feedback

# Load backend/.env first, then root .env.local for local full-stack runs.
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

app = FastAPI(title="Speaking App Backend", version="1.0.0")
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "dist"
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads"))
AUDIO_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "audio")
IMAGE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "images")
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.on_event("startup")
async def startup_event():
    init_db()


def get_cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS")
    if configured_origins:
        return [
            origin.strip()
            for origin in configured_origins.split(",")
            if origin.strip()
        ]

    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:9000",
        "http://127.0.0.1:9000",
        "http://localhost:3000",
    ]

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def warm_vibevoice_asr() -> None:
    if VIBEVOICE_WARM_ON_START:
        _ensure_vibevoice_load_started()

def clean_api_key(value: Optional[str]) -> Optional[str]:
    key = (value or "").strip()
    if not key or "your_" in key.lower() or key.lower().endswith("_here"):
        return None
    return key


# API Keys from environment
OPENAI_API_KEY = clean_api_key(os.getenv("OPENAI_API_KEY") or os.getenv("VITE_OPENAI_API_KEY"))
GEMINI_API_KEY = clean_api_key(os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY"))
ASR_FALLBACK_ORDER = [
    model.strip()
    for model in os.getenv(
        "ASR_FALLBACK_ORDER",
        "ctwhisper",
    ).split(",")
    if model.strip()
]
FUNASR_MODEL = os.getenv("FUNASR_MODEL", "paraformer-zh")
FUNASR_VAD_MODEL = os.getenv("FUNASR_VAD_MODEL", "fsmn-vad")
FUNASR_PUNC_MODEL = os.getenv("FUNASR_PUNC_MODEL", "ct-punc")
CT_WHISPER_MODEL = os.getenv("CT_WHISPER_MODEL", "openai/whisper-small")
CT_WHISPER_DEVICE = os.getenv("CT_WHISPER_DEVICE", "cpu")
CT_WHISPER_LANGUAGE = os.getenv("CT_WHISPER_LANGUAGE", "chinese")
CT_WHISPER_TASK = os.getenv("CT_WHISPER_TASK", "transcribe")
CT_WHISPER_CACHE_DIR = os.getenv(
    "CT_WHISPER_CACHE_DIR",
    os.path.join(os.path.dirname(__file__), "..", ".models", "huggingface"),
)
VIBEVOICE_ASR_MODEL = os.getenv("VIBEVOICE_ASR_MODEL", "microsoft/VibeVoice-ASR")
VIBEVOICE_DEVICE = os.getenv("VIBEVOICE_DEVICE", "cpu")
VIBEVOICE_TORCH_DTYPE = os.getenv("VIBEVOICE_TORCH_DTYPE", "bfloat16")
VIBEVOICE_WARM_ON_START = os.getenv("VIBEVOICE_WARM_ON_START", "false").lower() == "true"
VIBEVOICE_MAX_NEW_TOKENS = int(os.getenv("VIBEVOICE_MAX_NEW_TOKENS", "64"))
VIBEVOICE_MAX_TIME_SECONDS = float(os.getenv("VIBEVOICE_MAX_TIME_SECONDS", "45"))
VIBEVOICE_CACHE_DIR = os.getenv(
    "VIBEVOICE_CACHE_DIR",
    os.path.join(os.path.dirname(__file__), "..", ".models", "huggingface"),
)
_funasr_model = None
_ct_whisper_model = None
_vibevoice_asr_model = None
_vibevoice_load_lock = threading.Lock()
_vibevoice_load_thread = None
_vibevoice_load_error = None


# Pydantic models
class AnalysisResponse(BaseModel):
    description: str = ""
    transcription: str = ""
    transcription_model: str = ""
    pitch_contour: List[Tuple[float, float]]
    word_prosody: List[dict]
    detected_tone: int
    tone_accuracy: float
    formants: dict
    vowel_quality: str = ""
    speech_rate: float
    fluency_score: float
    pitch_statistics: dict
    tone_direction: str = ""
    pause_analysis: dict = {}
    feedback: str
    ai_feedback: dict


class AsrStatusResponse(BaseModel):
    provider: str
    status: str
    message: str


class ReferenceToneResponse(BaseModel):
    tone: int
    name: str
    character: str
    pinyin: str
    description: str
    pitch_pattern: List[float]
    frequency_range: Tuple[int, int]
    expected_mean: int


class TranscriptionResponse(BaseModel):
    text: str
    model: str


class StoryImageGenerationRequest(BaseModel):
    situation: str
    level: str = "Beginner speaking"
    style: str = "warm educational comic"
    language_focus: str = "Mandarin story speaking with who, where, event, problem, solution, and feeling"


class StoryImageFrame(BaseModel):
    index: int
    title: str
    student_prompt: str
    vocabulary: List[str]
    image_prompt: str
    image_url: str


class StoryImageGenerationResponse(BaseModel):
    provider: str
    title: str
    learning_goal: str
    frames: List[StoryImageFrame]


class AudioRecordRequest(BaseModel):
    id: str
    timestamp: str
    duration: int
    transcription: str = ""
    model: str
    topicId: Optional[str] = None
    imageUrl: Optional[str] = None
    imageIndex: Optional[int] = None
    audioUrl: Optional[str] = None
    praatMetrics: Optional[dict] = None


class CustomStoryFrameRequest(BaseModel):
    imageUrl: str
    prompt: str
    vocabulary: str = ""


class CustomStoryRequest(BaseModel):
    id: str
    title: str
    learningGoal: str
    level: str
    frames: List[CustomStoryFrameRequest]
    published: bool = False


class HelpRequest(BaseModel):
    id: str
    studentName: str
    message: str = "I need teacher help."
    status: str = "open"
    createdAt: str
    resolvedAt: Optional[str] = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Speaking App Backend"}


@app.get("/api/audio-records")
async def list_audio_records():
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM audio_records ORDER BY created_at DESC"
        ).fetchall()
    return [row_to_audio_record(row) for row in rows]


@app.post("/api/audio-records")
async def create_audio_record(record: AudioRecordRequest):
    save_audio_record(record)
    return record


@app.post("/api/audio-records/upload")
async def upload_audio_record(
    record: str = Form(...),
    file: UploadFile = File(...),
):
    try:
        audio_record = AudioRecordRequest.model_validate_json(record)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid audio record JSON") from exc

    audio_record.audioUrl = await save_uploaded_audio(file, audio_record.id)
    save_audio_record(audio_record)
    return audio_record


def save_audio_record(record: AudioRecordRequest):
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO audio_records (
                id, timestamp, duration, transcription, model, topic_id,
                image_url, image_index, audio_url, praat_metrics
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


@app.delete("/api/audio-records/{record_id}")
async def delete_audio_record(record_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT audio_url FROM audio_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        db.execute("DELETE FROM audio_records WHERE id = ?", (record_id,))
    if row and row["audio_url"]:
        remove_uploaded_file(row["audio_url"])
    return {"ok": True}


@app.get("/api/custom-stories")
async def list_custom_stories():
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM custom_stories ORDER BY created_at DESC"
        ).fetchall()
    return [row_to_custom_story(row) for row in rows]


@app.post("/api/custom-stories")
async def create_custom_story(story: CustomStoryRequest):
    frames = [frame.model_dump() for frame in story.frames]
    stored_frames = persist_story_frame_images(story.id, frames)
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO custom_stories (
                id, title, learning_goal, level, frames, published
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                story.id,
                story.title,
                story.learningGoal,
                story.level,
                json.dumps(stored_frames),
                1 if story.published else 0,
            ),
        )
    return {
        **story.model_dump(),
        "frames": stored_frames,
    }


@app.delete("/api/custom-stories/{story_id}")
async def delete_custom_story(story_id: str):
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = ?",
            (story_id,),
        ).fetchone()
        db.execute("DELETE FROM custom_stories WHERE id = ?", (story_id,))
    if row:
        for frame in json.loads(row["frames"] or "[]"):
            remove_uploaded_file(frame.get("imageUrl", ""))
    return {"ok": True}


@app.get("/api/help-requests")
async def list_help_requests():
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM help_requests
            ORDER BY
                CASE status WHEN 'open' THEN 0 ELSE 1 END,
                created_at DESC
            """
        ).fetchall()
    return [row_to_help_request(row) for row in rows]


@app.post("/api/help-requests")
async def create_help_request(request: HelpRequest):
    student_name = request.studentName.strip() or "Student"
    message = request.message.strip() or "I need teacher help."
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO help_requests (
                id, student_name, message, status, created_at, resolved_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                request.id,
                student_name,
                message,
                "open",
                request.createdAt,
                None,
            ),
        )
    return {
        **request.model_dump(),
        "studentName": student_name,
        "message": message,
        "status": "open",
        "resolvedAt": None,
    }


@app.post("/api/help-requests/{request_id}/resolve")
async def resolve_help_request(request_id: str):
    resolved_at = datetime.datetime.utcnow().isoformat() + "Z"
    with connect_db() as db:
        row = db.execute(
            "SELECT * FROM help_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Help request not found")
        db.execute(
            """
            UPDATE help_requests
            SET status = 'resolved', resolved_at = ?
            WHERE id = ?
            """,
            (resolved_at, request_id),
        )
        updated = db.execute(
            "SELECT * FROM help_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
    return row_to_help_request(updated)


async def save_uploaded_audio(file: UploadFile, record_id: str) -> str:
    extension = extension_from_upload(file.filename, file.content_type, default=".wav")
    filename = f"{safe_file_stem(record_id)}{extension}"
    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
    content = await file.read()
    with open(path, "wb") as output:
        output.write(content)
    return f"/uploads/audio/{filename}"


def persist_story_frame_images(story_id: str, frames: list[dict]) -> list[dict]:
    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        image_url = frame.get("imageUrl", "")
        if image_url.startswith("data:image/"):
            frame = {
                **frame,
                "imageUrl": save_data_url_image(image_url, story_id, index),
            }
        stored_frames.append(frame)
    return stored_frames


def save_data_url_image(data_url: str, story_id: str, index: int) -> str:
    header, _, data = data_url.partition(",")
    if not data:
        return data_url

    mime = header.removeprefix("data:").split(";")[0]
    extension = extension_from_mime(mime, default=".png")
    filename = f"{safe_file_stem(story_id)}-frame-{index}{extension}"
    path = os.path.join(IMAGE_UPLOAD_DIR, filename)
    content = (
        base64.b64decode(data)
        if ";base64" in header
        else unquote_to_bytes(data)
    )
    with open(path, "wb") as output:
        output.write(content)
    return f"/uploads/images/{filename}"


def extension_from_upload(
    filename: Optional[str],
    content_type: Optional[str],
    default: str,
) -> str:
    if filename:
        extension = os.path.splitext(filename)[1].lower()
        if extension:
            return extension
    return extension_from_mime(content_type or "", default)


def extension_from_mime(mime: str, default: str) -> str:
    return {
        "audio/wav": ".wav",
        "audio/wave": ".wav",
        "audio/webm": ".webm",
        "audio/mpeg": ".mp3",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/svg+xml": ".svg",
    }.get(mime.lower(), default)


def safe_file_stem(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in ("-", "_") else "-"
        for character in value
    ).strip("-") or "upload"


def remove_uploaded_file(url: str) -> None:
    if not url.startswith("/uploads/"):
        return
    relative_path = url.removeprefix("/uploads/").replace("/", os.sep)
    path = os.path.abspath(os.path.join(UPLOAD_DIR, relative_path))
    upload_root = os.path.abspath(UPLOAD_DIR)
    if path.startswith(upload_root) and os.path.exists(path):
        os.remove(path)


@app.post("/api/generate-story-images", response_model=StoryImageGenerationResponse)
async def generate_story_images(request: StoryImageGenerationRequest):
    """
    Generate a six-image story sequence plan from a classroom situation.
    Gemini creates the scene plan when configured; deterministic local fallback
    keeps the teacher workflow usable offline.
    """
    situation = request.situation.strip()
    if len(situation) < 8:
        raise HTTPException(
            status_code=400,
            detail="Describe the situation context with at least 8 characters.",
        )

    if GEMINI_API_KEY:
        try:
            return await generate_story_images_with_gemini(request)
        except Exception as exc:
            print(f"Gemini story image planning failed, using local fallback: {exc}")

    fallback = build_story_image_fallback(request, provider="local")
    return await normalize_story_image_response(
        {"title": fallback.title, "learning_goal": fallback.learning_goal,
         "frames": [{"title": f.title, "student_prompt": f.student_prompt,
                     "vocabulary": f.vocabulary, "image_prompt": f.image_prompt}
                    for f in fallback.frames]},
        request,
        provider="local",
    )


@app.get("/api/asr-status", response_model=AsrStatusResponse)
async def get_asr_status():
    with _vibevoice_load_lock:
        if _vibevoice_asr_model is not None:
            return AsrStatusResponse(
                provider="vibevoice",
                status="ready",
                message="VibeVoice-ASR is ready.",
            )
        if _vibevoice_load_error:
            return AsrStatusResponse(
                provider="vibevoice",
                status="error",
                message=f"VibeVoice-ASR failed to load: {_vibevoice_load_error}",
            )
        if _vibevoice_load_thread is not None and _vibevoice_load_thread.is_alive():
            return AsrStatusResponse(
                provider="vibevoice",
                status="loading",
                message="VibeVoice-ASR is loading the local model weights.",
            )

    return AsrStatusResponse(
        provider="vibevoice",
        status="idle",
        message="VibeVoice-ASR is not loaded. It starts only when a VibeVoice transcription request is submitted.",
    )


ANALYZE_TIMEOUT_SECONDS = int(os.getenv("ANALYZE_TIMEOUT_SECONDS", "120"))


def classify_vowel_quality(formants: dict) -> str:
    """Translate F1/F2 Hz into a plain-language vowel quality label."""
    f1 = formants.get("F1", 0)
    f2 = formants.get("F2", 0)
    if f1 <= 0 or f2 <= 0:
        return ""
    # High vowel: low F1 (closed mouth)
    if f1 < 400:
        if f2 > 2000:
            return "High front vowel — mouth nearly closed, tongue forward (like 你 nǐ)"
        return "High back vowel — mouth nearly closed, lips rounded (like 書 shū)"
    # Mid vowel
    if f1 < 650:
        if f2 > 1800:
            return "Mid front vowel — tongue mid-high, forward (like 姐 jiě)"
        if f2 > 1200:
            return "Mid central vowel — tongue in centre (like 的 de)"
        return "Mid back vowel — tongue mid, lips rounded (like 我 wǒ)"
    # Low vowel: high F1 (open mouth)
    return "Open vowel — mouth wide open, jaw dropped (like 啊 ā / 媽 mā)"


def build_tone_direction(
    pitch_contour: list,
    detected_tone: int,
    tone_accuracy: float,
) -> str:
    """Return a plain-language description of the pitch movement the student produced."""
    if not pitch_contour or len(pitch_contour) < 3:
        return ""
    freqs = [p[1] for p in pitch_contour]
    start = float(np.mean(freqs[:max(1, len(freqs) // 5)]))
    end   = float(np.mean(freqs[-max(1, len(freqs) // 5):]))
    mid   = float(np.mean(freqs[len(freqs) // 3 : 2 * len(freqs) // 3]))
    delta = end - start
    dip   = (start + end) / 2 - mid  # positive = dip in middle

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


async def _do_analyze(
    content: bytes,
    transcription: str,
    asr_model: str,
    scene_prompt: str = "",
    scene_vocabulary: str = "",
) -> AnalysisResponse:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        transcription_model = ""
        if not transcription.strip() and asr_model.strip():
            transcription_result = await transcribe_audio_content(content, asr_model.strip())
            transcription = transcription_result.text
            transcription_model = transcription_result.model

        def _run_praat(path: str, tx: str):
            return analyze_all(path, tx)

        # Run Praat (CPU-bound, threadpool) and AI feedback (I/O-bound) in parallel.
        # AI uses local fallback by default (instant); if an external provider is
        # configured the network call hides behind Praat's CPU time.
        # After both finish, patch pronunciation_note with real Praat numbers.
        (praat_result, ai_feedback) = await asyncio.gather(
            run_in_threadpool(_run_praat, tmp_path, transcription),
            generate_language_feedback(transcription, scene_prompt, scene_vocabulary),
        )
        (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
         word_prosody, detected_tone, tone_accuracy, feedback,
         pause_analysis) = praat_result

        vowel_quality = classify_vowel_quality(formants)
        tone_direction = build_tone_direction(pitch_contour, detected_tone, tone_accuracy)

        # Patch pronunciation_note with real Praat numbers now that we have them
        from ai_feedback import fallback_language_feedback as _local_fb
        pron_patch = _local_fb(
            transcription, scene_prompt, scene_vocabulary,
            praat_tone_accuracy=float(tone_accuracy),
            praat_fluency_score=float(fluency_score),
            praat_vowel_quality=vowel_quality or "",
        )
        if isinstance(ai_feedback, dict):
            ai_feedback["pronunciation_note"] = pron_patch["pronunciation_note"]
        description = build_analysis_description(transcription, transcription_model, word_prosody)

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


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_speech(
    file: UploadFile = File(...),
    transcription: str = Form(""),
    asr_model: str = Form(""),
    scene_prompt: str = Form(""),
    scene_vocabulary: str = Form(""),
):
    """
    Analyze Chinese speech for tone, pitch, formants, speech rate, and fluency.
    If transcription is empty and asr_model is provided, transcribe first, then
    run Praat against the same audio. scene_prompt and scene_vocabulary are used
    to make AI and local feedback context-aware.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    content = await file.read()
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
    except Exception as e:
        print(f"Error in analyze_speech: {e}")
        raise HTTPException(status_code=500, detail=f"Error analyzing speech: {str(e)}")


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    model: str = Form("ctwhisper"),
):
    """
    Transcribe audio to text using the requested backend ASR model.
    The default upload flow uses local Chinese/Taiwanese Whisper.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    try:
        content = await file.read()

        return await transcribe_audio_content(content, model)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in transcribe_speech: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error transcribing speech: {str(e)}"
        )


async def transcribe_audio_content(
    audio_content: bytes,
    model: str,
) -> TranscriptionResponse:
    if model == "auto":
        return await transcribe_with_auto_fallback(audio_content)

    if model == "openai":
        if not OPENAI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key not configured"
            )
        return await transcribe_with_openai(audio_content)

    if model == "gemini":
        if not GEMINI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="Gemini API key not configured"
            )
        return await transcribe_with_gemini(audio_content)

    if model == "funasr":
        return await transcribe_with_funasr(audio_content)

    if model in {"ctwhisper", "chinese_taiwanese_whisper"}:
        return await transcribe_with_ct_whisper(audio_content)

    if model == "vibevoice":
        return await transcribe_with_vibevoice(audio_content)

    raise HTTPException(
        status_code=400,
        detail="Invalid model. Use 'auto', 'ctwhisper', 'openai', 'gemini', 'funasr', or 'vibevoice'"
    )


async def transcribe_with_auto_fallback(audio_content: bytes) -> TranscriptionResponse:
    errors = []
    for provider in ASR_FALLBACK_ORDER:
        if provider == "gemini" and not GEMINI_API_KEY:
            errors.append("gemini: missing API key")
            continue
        if provider == "openai" and not OPENAI_API_KEY:
            errors.append("openai: missing API key")
            continue

        try:
            result = await transcribe_audio_content(audio_content, provider)
            if result.text.strip():
                return TranscriptionResponse(
                    text=result.text,
                    model=f"auto:{result.model}",
                )
            errors.append(f"{provider}: empty transcription")
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    detail = (
        "No local ASR model produced a transcript. Make sure the Chinese/Taiwanese "
        "Whisper model is installed on the backend. Tried: "
        + "; ".join(errors)
    )
    print(f"Auto ASR failed. Errors: {errors}")
    raise HTTPException(status_code=503, detail=detail)


def build_analysis_description(
    transcription: str,
    transcription_model: str,
    word_prosody: list[dict],
) -> str:
    text = transcription.strip()
    word_count = len(word_prosody)

    if not text:
        return (
            "The audio was analyzed for pitch and fluency, but no transcript was "
            "returned. Try a clearer recording with one short sentence."
        )

    model_note = (
        f" using {transcription_model}"
        if transcription_model
        else ""
    )
    return (
        f"The system transcribed your recording{model_note} and found "
        f"{word_count} word-level prosody item{'s' if word_count != 1 else ''} "
        "for review."
    )


async def generate_story_images_with_gemini(
    request: StoryImageGenerationRequest,
) -> StoryImageGenerationResponse:
    prompt = f"""
You are helping a Mandarin teacher create a six-picture speaking story.

Situation context:
{request.situation}

Student level:
{request.level}

Visual style:
{request.style}

Language focus:
{request.language_focus}

Return only valid JSON shaped exactly like:
{{
  "title": "short activity title",
  "learning_goal": "one sentence learning goal",
  "frames": [
    {{
      "title": "scene title",
      "student_prompt": "student speaking prompt",
      "vocabulary": ["word", "word", "word"],
      "image_prompt": "specific image generation prompt for one coherent story scene"
    }}
  ]
}}

Rules:
- Return exactly 6 frames.
- The 6 frames must tell one connected real-life story with clear narrative progression.
- Each frame shows ONE specific visible action — not just a place or object.
- image_prompt must be highly specific: describe the exact people (age, clothing, expression),
  their action (gesture, body language), the precise setting (specific location details,
  background objects), and the mood/lighting. Write it as a detailed scene description
  for a photorealistic image generator. Minimum 30 words per image_prompt.
  Example: "Photorealistic photo of a teenage Taiwanese girl in school uniform looking
  at her empty hands with a worried expression, standing on a Taipei MRT platform,
  other commuters visible in background, bright fluorescent station lighting."
- Do NOT use vague words like "scene", "illustration", "image of", "depicts".
- Use safe, real-life content appropriate for middle school students.
- Use Traditional Chinese vocabulary when useful, but keep JSON keys in English.
"""

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return await normalize_story_image_response(
        data,
        request,
        provider="gemini-2.0-flash",
    )


def build_story_image_fallback(
    request: StoryImageGenerationRequest,
    provider: str,
) -> StoryImageGenerationResponse:
    situation = request.situation.strip()
    title = title_from_situation(situation)
    scene_templates = [
        (
            "Set the scene",
            "Describe who is there and where the story begins.",
            ["who", "where", "today"],
        ),
        (
            "First action",
            "Tell what the main person does first.",
            ["first", "go", "meet"],
        ),
        (
            "Small problem",
            "Explain the problem or surprise in the situation.",
            ["problem", "because", "need"],
        ),
        (
            "Ask for help",
            "Say how someone asks, answers, or helps.",
            ["ask", "help", "together"],
        ),
        (
            "Solve it",
            "Describe what changes and how the problem is solved.",
            ["then", "finish", "better"],
        ),
        (
            "Ending feeling",
            "Finish the story with a feeling or lesson.",
            ["finally", "feel", "next time"],
        ),
    ]

    frames = []
    for index, (scene_title, prompt, vocabulary) in enumerate(scene_templates, start=1):
        image_prompt = (
            f"{request.style}, frame {index} of 6, {scene_title.lower()} for "
            f"the situation: {situation}. Show people doing a clear classroom-safe "
            "real-life action, consistent characters, soft colors, storybook composition."
        )
        frames.append(
            StoryImageFrame(
                index=index,
                title=scene_title,
                student_prompt=prompt,
                vocabulary=vocabulary,
                image_prompt=image_prompt,
                image_url=build_scene_svg_data_url(index, scene_title, situation),
            )
        )

    return StoryImageGenerationResponse(
        provider=provider,
        title=title,
        learning_goal=(
            "Students build a six-part Mandarin story by describing the scene, "
            "event, problem, help, solution, and feeling."
        ),
        frames=frames,
    )


async def generate_real_image(image_prompt: str, seed: int) -> str:
    """
    Download a real generated image and save it to uploads.
    Uses DALL-E 3 when OPENAI_API_KEY is set, otherwise Pollinations.ai (free).
    Returns a /uploads/images/... path on success, or "" on failure.
    """
    try:
        if OPENAI_API_KEY:
            payload = {
                "model": "dall-e-3",
                "prompt": image_prompt,
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "url",
            }
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
                )
            if resp.status_code != 200:
                raise RuntimeError(resp.text)
            img_url = resp.json()["data"][0]["url"]
        else:
            # Pollinations.ai — free, no key needed
            from urllib.parse import quote as url_quote
            encoded = url_quote(image_prompt)
            img_url = (
                f"https://image.pollinations.ai/prompt/{encoded}"
                f"?width=800&height=600&seed={seed}&model=flux&nologo=true"
            )

        # Download the image and save locally
        async with httpx.AsyncClient(timeout=60) as client:
            img_resp = await client.get(img_url, follow_redirects=True)
        if img_resp.status_code != 200:
            return ""

        content_type = img_resp.headers.get("content-type", "image/jpeg")
        ext = ".jpg" if "jpeg" in content_type else ".png"
        filename = f"gen-{seed}{ext}"
        path = os.path.join(IMAGE_UPLOAD_DIR, filename)
        with open(path, "wb") as f:
            f.write(img_resp.content)
        return f"/uploads/images/{filename}"
    except Exception as exc:
        print(f"Image generation failed (seed={seed}): {exc}")
        return ""


async def normalize_story_image_response(
    data: dict,
    request: StoryImageGenerationRequest,
    provider: str,
) -> StoryImageGenerationResponse:
    fallback = build_story_image_fallback(request, provider=provider)
    raw_frames = data.get("frames", [])

    # Collect frame metadata first
    frame_meta = []
    for index in range(6):
        fallback_frame = fallback.frames[index]
        raw_frame = raw_frames[index] if index < len(raw_frames) and isinstance(raw_frames[index], dict) else {}
        title = str(raw_frame.get("title") or fallback_frame.title).strip()
        student_prompt = str(raw_frame.get("student_prompt") or fallback_frame.student_prompt).strip()
        vocabulary = raw_frame.get("vocabulary") or fallback_frame.vocabulary
        if not isinstance(vocabulary, list):
            vocabulary = fallback_frame.vocabulary
        raw_image_prompt = str(raw_frame.get("image_prompt") or fallback_frame.image_prompt).strip()
        # Enrich with realism instruction
        image_prompt = (
            f"Photorealistic scene, natural lighting, Taiwan setting. {raw_image_prompt} "
            f"No text overlays. Real people, real environment. Frame {index + 1} of a connected story."
        )
        frame_meta.append((index, title, student_prompt, vocabulary, image_prompt))

    # Generate all 6 images in parallel
    base_seed = abs(hash(request.situation)) % 100000
    image_urls = await asyncio.gather(*[
        generate_real_image(meta[4], base_seed + meta[0])
        for meta in frame_meta
    ])

    frames = []
    for (index, title, student_prompt, vocabulary, image_prompt), img_url in zip(frame_meta, image_urls):
        # Fall back to SVG placeholder only if image generation failed
        url = img_url or build_scene_svg_data_url(index + 1, title, request.situation)
        frames.append(StoryImageFrame(
            index=index + 1,
            title=title,
            student_prompt=student_prompt,
            vocabulary=[str(word) for word in vocabulary[:5]],
            image_prompt=image_prompt,
            image_url=url,
        ))

    return StoryImageGenerationResponse(
        provider=provider,
        title=str(data.get("title") or fallback.title).strip(),
        learning_goal=str(data.get("learning_goal") or fallback.learning_goal).strip(),
        frames=frames,
    )


def strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json"):
        return stripped.removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("```"):
        return stripped.removeprefix("```").removesuffix("```").strip()
    return stripped


def title_from_situation(situation: str) -> str:
    words = " ".join(situation.split()[:8])
    return f"{words} Story" if words else "Six Picture Story"


def build_scene_svg_data_url(index: int, title: str, situation: str) -> str:
    palettes = [
        ("#dff7ef", "#2f9e83", "#f7c948"),
        ("#e9f0ff", "#5778c7", "#f4a261"),
        ("#fff3df", "#d9822b", "#59a14f"),
        ("#f0ecff", "#7c65d1", "#ffb703"),
        ("#e8f6ff", "#2786a5", "#f77f00"),
        ("#f8efe6", "#8f6b4a", "#4cc9f0"),
    ]
    background, primary, accent = palettes[(index - 1) % len(palettes)]
    safe_title = escape_svg_text(title[:36])
    safe_context = escape_svg_text(situation[:64])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 640">
<rect width="960" height="640" fill="{background}"/>
<rect x="48" y="52" width="864" height="536" rx="30" fill="#fffaf3" stroke="#263238" stroke-width="5"/>
<path d="M82 455 C170 395 250 430 322 382 C430 310 545 390 642 326 C722 274 800 298 878 244 L878 588 L82 588 Z" fill="{accent}" opacity="0.28"/>
<rect x="96" y="116" width="230" height="168" rx="20" fill="#ffffff" stroke="{primary}" stroke-width="5"/>
<rect x="642" y="112" width="220" height="172" rx="20" fill="#ffffff" stroke="{primary}" stroke-width="5"/>
<circle cx="440" cy="246" r="58" fill="{primary}"/>
<circle cx="560" cy="246" r="58" fill="{accent}"/>
<path d="M408 340 C436 296 468 296 496 340 L496 458 L370 458 Z" fill="{primary}"/>
<path d="M530 340 C558 296 590 296 618 340 L652 458 L496 458 Z" fill="{accent}"/>
<path d="M365 492 L662 492" stroke="#263238" stroke-width="8" stroke-linecap="round"/>
<circle cx="130" cy="150" r="16" fill="{accent}"/>
<circle cx="178" cy="150" r="16" fill="{primary}"/>
<circle cx="690" cy="150" r="16" fill="{accent}"/>
<circle cx="738" cy="150" r="16" fill="{primary}"/>
<text x="96" y="82" fill="#263238" font-family="Arial, sans-serif" font-size="30" font-weight="800">Frame {index}</text>
<text x="96" y="540" fill="#263238" font-family="Arial, sans-serif" font-size="34" font-weight="800">{safe_title}</text>
<text x="96" y="574" fill="#455a64" font-family="Arial, sans-serif" font-size="20">{safe_context}</text>
</svg>"""
    return "data:image/svg+xml;charset=utf-8," + quote(svg.replace("\n", ""))


def escape_svg_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


async def transcribe_with_openai(audio_content: bytes) -> TranscriptionResponse:
    """Transcribe using OpenAI Whisper API."""
    async with httpx.AsyncClient() as client:
        files = {"file": ("audio.wav", audio_content, "audio/wav")}
        data = {"model": "whisper-1", "language": "zh"}

        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files=files,
            data=data,
        )

        if response.status_code != 200:
            raise Exception(f"OpenAI API error: {response.text}")

        result = response.json()
        return TranscriptionResponse(text=result["text"], model="openai")


async def transcribe_with_gemini(audio_content: bytes) -> TranscriptionResponse:
    """Transcribe using Google Gemini API."""
    import base64

    audio_base64 = base64.b64encode(audio_content).decode()

    async with httpx.AsyncClient() as client:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "audio/wav",
                                "data": audio_base64,
                            }
                        },
                        {
                            "text": "Please transcribe this audio to text. Only provide the transcription without any additional explanation."
                        },
                    ]
                }
            ]
        }

        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

        if response.status_code != 200:
            raise Exception(f"Gemini API error: {response.text}")

        result = response.json()
        text = result["candidates"][0]["content"]["parts"][0]["text"]
        return TranscriptionResponse(text=text, model="gemini")


def _get_funasr_model():
    global _funasr_model

    if _funasr_model is None:
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "FunASR is not installed on the backend. Install backend requirements "
                "or run `pip install funasr modelscope`."
            ) from exc

        _funasr_model = AutoModel(
            model=FUNASR_MODEL,
            vad_model=FUNASR_VAD_MODEL,
            punc_model=FUNASR_PUNC_MODEL,
            disable_update=True,
        )

    return _funasr_model


def _extract_funasr_text(result) -> str:
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict):
            return str(first.get("text", "")).strip()
        return str(first).strip()

    if isinstance(result, dict):
        return str(result.get("text", "")).strip()

    return str(result or "").strip()


def _transcribe_with_funasr_sync(audio_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_content)
        tmp_path = tmp_file.name

    try:
        model = _get_funasr_model()
        result = model.generate(input=tmp_path, language="zh", batch_size_s=60)
        text = _extract_funasr_text(result)
        if not text:
            raise RuntimeError("FunASR did not return transcription text.")
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_with_funasr(audio_content: bytes) -> TranscriptionResponse:
    """Transcribe using local FunASR on the backend."""
    text = await run_in_threadpool(_transcribe_with_funasr_sync, audio_content)
    return TranscriptionResponse(text=text, model="funasr")


def _get_ct_whisper_model():
    global _ct_whisper_model

    if _ct_whisper_model is None:
        try:
            import torch
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
        except ImportError as exc:
            raise RuntimeError(
                "Chinese/Taiwanese Whisper requires torch and transformers."
            ) from exc

        os.makedirs(CT_WHISPER_CACHE_DIR, exist_ok=True)
        processor = WhisperProcessor.from_pretrained(
            CT_WHISPER_MODEL,
            cache_dir=CT_WHISPER_CACHE_DIR,
        )
        model = WhisperForConditionalGeneration.from_pretrained(
            CT_WHISPER_MODEL,
            cache_dir=CT_WHISPER_CACHE_DIR,
            low_cpu_mem_usage=True,
        )
        device = CT_WHISPER_DEVICE
        if device != "auto":
            model = model.to(device)
        model.eval()
        _ct_whisper_model = (processor, model, device)

    return _ct_whisper_model


def _transcribe_with_ct_whisper_sync(audio_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_content)
        tmp_path = tmp_file.name

    try:
        import librosa
        import torch

        processor, model, device = _get_ct_whisper_model()
        audio, _ = librosa.load(tmp_path, sr=16000, mono=True)
        inputs = processor(
            audio,
            sampling_rate=16000,
            return_tensors="pt",
        )
        input_features = inputs.input_features.to(device)
        forced_decoder_ids = processor.get_decoder_prompt_ids(
            language=CT_WHISPER_LANGUAGE,
            task=CT_WHISPER_TASK,
        )

        with torch.no_grad():
            predicted_ids = model.generate(
                input_features,
                forced_decoder_ids=forced_decoder_ids,
                max_new_tokens=128,
            )

        text = processor.batch_decode(
            predicted_ids,
            skip_special_tokens=True,
        )[0].strip()
        text = convert_to_traditional_chinese(text)
        if not text:
            raise RuntimeError("Chinese/Taiwanese Whisper returned an empty transcript.")
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def convert_to_traditional_chinese(text: str) -> str:
    try:
        from opencc import OpenCC

        return OpenCC("s2twp").convert(text)
    except Exception:
        return text


async def transcribe_with_ct_whisper(audio_content: bytes) -> TranscriptionResponse:
    """Transcribe using a Chinese/Taiwanese Whisper model."""
    text = await run_in_threadpool(_transcribe_with_ct_whisper_sync, audio_content)
    return TranscriptionResponse(text=text, model="ctwhisper")


def _load_vibevoice_asr_model():
    try:
        import torch
        from transformers import AutoModel, AutoModelForCausalLM

        patch_transformers_duplicate_registration(AutoModel)
        patch_transformers_duplicate_registration(AutoModelForCausalLM)

        from vibevoice.modular.modeling_vibevoice_asr import (
            VibeVoiceASRForConditionalGeneration,
        )
        from vibevoice.processor.vibevoice_asr_processor import (
            VibeVoiceASRProcessor,
        )
    except ImportError as exc:
        raise RuntimeError(
            "VibeVoice-ASR library is not installed on the backend. "
            "Install the VibeVoice package and its torch/transformers dependencies."
        ) from exc

    device = VIBEVOICE_DEVICE
    dtype_by_name = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }
    dtype = dtype_by_name.get(VIBEVOICE_TORCH_DTYPE.lower(), torch.bfloat16)
    os.makedirs(VIBEVOICE_CACHE_DIR, exist_ok=True)
    processor = VibeVoiceASRProcessor.from_pretrained(
        VIBEVOICE_ASR_MODEL,
        cache_dir=VIBEVOICE_CACHE_DIR,
        local_files_only=True,
    )
    model = VibeVoiceASRForConditionalGeneration.from_pretrained(
        VIBEVOICE_ASR_MODEL,
        cache_dir=VIBEVOICE_CACHE_DIR,
        local_files_only=True,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
        device_map="auto" if device == "auto" else None,
        attn_implementation="sdpa",
        trust_remote_code=True,
    )
    if device != "auto":
        model = model.to(device)
    model.eval()
    return processor, model, device


def _load_vibevoice_asr_model_background():
    global _vibevoice_asr_model, _vibevoice_load_error

    try:
        model_bundle = _load_vibevoice_asr_model()
        with _vibevoice_load_lock:
            _vibevoice_asr_model = model_bundle
            _vibevoice_load_error = None
    except Exception as exc:
        with _vibevoice_load_lock:
            _vibevoice_load_error = str(exc)


def _ensure_vibevoice_load_started() -> None:
    global _vibevoice_load_thread

    with _vibevoice_load_lock:
        if _vibevoice_asr_model is not None or _vibevoice_load_error:
            return
        if _vibevoice_load_thread is not None and _vibevoice_load_thread.is_alive():
            return

        _vibevoice_load_thread = threading.Thread(
            target=_load_vibevoice_asr_model_background,
            name="vibevoice-asr-loader",
            daemon=True,
        )
        _vibevoice_load_thread.start()


def _get_vibevoice_asr_model():
    with _vibevoice_load_lock:
        if _vibevoice_asr_model is not None:
            return _vibevoice_asr_model
        if _vibevoice_load_error:
            raise HTTPException(
                status_code=503,
                detail=f"VibeVoice-ASR failed to load: {_vibevoice_load_error}",
            )

    _ensure_vibevoice_load_started()
    raise HTTPException(
        status_code=503,
        detail=(
            "VibeVoice-ASR is loading the local model weights. "
            "Please try again in a few minutes."
        ),
    )


def patch_transformers_duplicate_registration(auto_class):
    original_register = auto_class.register
    if getattr(original_register, "_vibevoice_duplicate_safe", False):
        return

    def safe_register(config_class, model_class, exist_ok=False):
        try:
            return original_register(config_class, model_class, exist_ok=exist_ok)
        except ValueError as exc:
            if "is already used by a Transformers model" in str(exc):
                return None
            raise

    safe_register._vibevoice_duplicate_safe = True
    auto_class.register = safe_register


def _extract_vibevoice_text(result: dict) -> str:
    segments = result.get("segments") if isinstance(result, dict) else None
    if isinstance(segments, list) and segments:
        return " ".join(
            str(segment.get("text", "")).strip()
            for segment in segments
            if isinstance(segment, dict) and segment.get("text")
        ).strip()

    return str(result.get("raw_text", "") if isinstance(result, dict) else "").strip()


def _transcribe_with_vibevoice_sync(audio_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_content)
        tmp_path = tmp_file.name

    try:
        import torch

        processor, model, device = _get_vibevoice_asr_model()
        inputs = processor(
            audio=tmp_path,
            sampling_rate=None,
            return_tensors="pt",
            add_generation_prompt=True,
        )
        inputs = {
            key: value.to(device) if isinstance(value, torch.Tensor) else value
            for key, value in inputs.items()
        }

        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=VIBEVOICE_MAX_NEW_TOKENS,
                max_time=VIBEVOICE_MAX_TIME_SECONDS,
                do_sample=False,
                num_beams=1,
                pad_token_id=processor.pad_id,
                eos_token_id=processor.tokenizer.eos_token_id,
            )

        generated_ids = output_ids[0, inputs["input_ids"].shape[1]:]
        generated_text = processor.decode(generated_ids, skip_special_tokens=True)
        try:
            segments = processor.post_process_transcription(generated_text)
        except Exception:
            segments = []
        result = {"raw_text": generated_text, "segments": segments}
        text = _extract_vibevoice_text(result)
        if not text:
            raise RuntimeError("VibeVoice-ASR did not return transcription text.")
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_with_vibevoice(audio_content: bytes) -> TranscriptionResponse:
    """Transcribe using local VibeVoice-ASR through Transformers on the backend."""
    try:
        text = await asyncio.wait_for(
            run_in_threadpool(_transcribe_with_vibevoice_sync, audio_content),
            timeout=VIBEVOICE_MAX_TIME_SECONDS + 20,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=(
                "VibeVoice-ASR transcription is too slow on this machine. "
                "Try a shorter recording or run the backend on a GPU."
            ),
        ) from exc
    return TranscriptionResponse(text=text, model="vibevoice")


@app.get("/api/reference-tone/{tone_number}", response_model=ReferenceToneResponse)
async def get_reference_tone(tone_number: int):
    """
    Get reference pitch contour for a Mandarin tone (1-4).
    """
    if tone_number not in [1, 2, 3, 4]:
        raise HTTPException(
            status_code=400,
            detail="Tone number must be 1, 2, 3, or 4"
        )

    ref = get_reference_tone_pattern(tone_number)

    if not ref:
        raise HTTPException(status_code=404, detail="Tone reference not found")

    return ReferenceToneResponse(
        tone=ref["tone"],
        name=ref["name"],
        character=ref["character"],
        pinyin=ref["pinyin"],
        description=ref["description"],
        pitch_pattern=ref["pitch_pattern"],
        frequency_range=ref["frequency_range"],
        expected_mean=ref["expected_mean"],
    )


@app.get("/api/all-tones")
async def get_all_tones():
    """
    Get all Mandarin tone references.
    """
    tones = {}
    for tone_num in [1, 2, 3, 4]:
        ref = get_reference_tone_pattern(tone_num)
        tones[tone_num] = ref

    return tones


@app.get("/{frontend_path:path}")
async def serve_frontend(frontend_path: str):
    """
    Serve the built React app from the backend port for local single-port use.
    """
    requested_file = (FRONTEND_DIST / frontend_path).resolve()

    if FRONTEND_DIST.exists() and requested_file.is_file():
        return FileResponse(requested_file)

    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    raise HTTPException(
        status_code=404,
        detail="Frontend build not found. Run `npm run build` first.",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
