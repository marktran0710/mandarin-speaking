from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Tuple
import base64
import logging
import mimetypes
import os
import tempfile
import time
import collections
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

# ── Structured logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("speaking_app")
from database import (
    connect_db,
    init_db,
    row_to_audio_record,
    row_to_custom_story,
    row_to_help_request,
    row_to_story_submission,
)

from praat_analyzer import (
    extract_pitch,
    extract_formants,
    calculate_speech_rate,
    analyze_fluency,
    get_pitch_statistics,
    estimate_word_prosody,
    word_stress_summary,
    analyze_all,
)
from chinese_tones import (
    detect_tone,
    calculate_tone_accuracy,
    get_reference_tone_pattern,
    generate_comprehensive_feedback,
)
from ai_feedback import (
    generate_language_feedback,
    available_providers,
    default_provider,
    generate_story_feedback,
)
from audio_concat import concatenate_scene_audio
from pypinyin import lazy_pinyin, Style
import taiwan_pinyin; taiwan_pinyin.apply()

# Load backend/.env first, then root .env.local for local full-stack runs.
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

app = FastAPI(title="Speaking App Backend", version="1.0.0")
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "dist"
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads"))
AUDIO_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "audio")
IMAGE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "images")
STORY_AUDIO_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "story_audio")
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)
os.makedirs(STORY_AUDIO_UPLOAD_DIR, exist_ok=True)
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

    # Vite picks the next free port when 5173 is taken (5174, 5175, 5176…),
    # so allow the common dev fallbacks to avoid CORS-blocked /api calls.
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5176",
        "http://localhost:9000",
        "http://127.0.0.1:9000",
        "http://localhost:3000",
    ]

# ── In-memory rate limiter ─────────────────────────────────────────────────
# Keyed by (route, client_ip). Tracks request timestamps in a deque.
_rate_limits: dict[str, collections.deque] = {}
_rate_limit_lock = threading.Lock()

def _check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _rate_limit_lock:
        dq = _rate_limits.setdefault(key, collections.deque())
        # Drop timestamps outside the window
        while dq and now - dq[0] > window_seconds:
            dq.popleft()
        if len(dq) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s.",
            )
        dq.append(now)

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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
GROQ_API_KEY = clean_api_key(os.getenv("GROQ_API_KEY") or os.getenv("VITE_GROQ_API_KEY"))
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
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
    vocabularyGroups: Optional[List[dict]] = None
    grammarPattern: Optional[str] = None
    grammarExample: Optional[str] = None
    vocabularyPinyin: Optional[str] = None
    suggestedAnswer: Optional[str] = None
    listenAudioUrl: Optional[str] = None
    listenScript: Optional[str] = None


class CustomStoryRequest(BaseModel):
    id: str
    title: str
    learningGoal: str
    level: str
    frames: List[CustomStoryFrameRequest]
    published: bool = False
    linear: bool = False
    firstFrameIsExample: bool = False
    lessonNumber: Optional[int] = None
    narrativeMode: str = "story"


class HelpRequest(BaseModel):
    id: str = Field(..., max_length=128)
    studentName: str = Field(default="Student", max_length=100)
    message: str = Field(default="I need teacher help.", max_length=500)
    status: str = "open"
    createdAt: str
    resolvedAt: Optional[str] = None


class SceneSubmission(BaseModel):
    sceneIndex: int
    imageUrl: str = ""
    transcription: str = ""
    vocabUsed: List[str] = []
    vocabMissing: List[str] = []
    vocabScore: float = 0
    toneAccuracy: float = 0
    pronScore: float = 0
    fluencyScore: float = 0
    audioUrl: Optional[str] = None


class StorySubmissionRequest(BaseModel):
    id: str = Field(..., max_length=128)
    storyId: str = Field(..., max_length=128)
    storyTitle: str = Field(default="", max_length=200)
    studentName: str = Field(default="Student", max_length=100)
    submittedAt: str
    scenes: List[SceneSubmission] = []


@app.get("/health")
async def health_check():
    """Health check endpoint with database connectivity status."""
    db_ok = False
    try:
        with connect_db() as db:
            db.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "Speaking App Backend",
        "database": "ok" if db_ok else "error",
    }


@app.get("/api/audio-records")
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
async def list_custom_stories(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM custom_stories ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, skip),
        ).fetchall()
    return [row_to_custom_story(row) for row in rows]


@app.post("/api/custom-stories")
async def create_custom_story(story: CustomStoryRequest):
    frames = [frame.model_dump() for frame in story.frames]
    stored_frames = persist_story_frame_images(story.id, frames)
    stored_frames = persist_story_frame_audio(story.id, stored_frames)
    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO custom_stories (
                id, title, learning_goal, level, frames, published, linear, lesson_number, narrative_mode, first_frame_is_example
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                story.id,
                story.title,
                story.learningGoal,
                story.level,
                json.dumps(stored_frames),
                1 if story.published else 0,
                1 if story.linear else 0,
                story.lessonNumber,
                story.narrativeMode,
                1 if story.firstFrameIsExample else 0,
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
            remove_uploaded_file(frame.get("listenAudioUrl", ""))
    return {"ok": True}


@app.get("/api/help-requests")
async def list_help_requests(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    with connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM help_requests
            ORDER BY
                CASE status WHEN 'open' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip),
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


@app.get("/api/story-submissions")
async def list_story_submissions(story_id: Optional[str] = None):
    with connect_db() as db:
        if story_id:
            rows = db.execute(
                "SELECT * FROM story_submissions WHERE story_id = ? ORDER BY submitted_at DESC",
                (story_id,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM story_submissions ORDER BY submitted_at DESC"
            ).fetchall()
    return [row_to_story_submission(row) for row in rows]


@app.post("/api/story-submissions")
async def create_story_submission(submission: StorySubmissionRequest):
    scenes_sorted = sorted(submission.scenes, key=lambda s: s.sceneIndex)

    with connect_db() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO story_submissions
                (id, story_id, story_title, student_name, submitted_at, scenes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                submission.id,
                submission.storyId,
                submission.storyTitle,
                submission.studentName,
                submission.submittedAt,
                json.dumps([s.model_dump() for s in scenes_sorted]),
            ),
        )

    # Story-level concatenated audio + holistic feedback are best-effort: the
    # scenes above are already durably saved, so a failure here must never
    # fail the whole submission — the student just doesn't get the story-level
    # extras this time (no retry, per the synchronous/no-background-job design).
    concatenated_audio_url: Optional[str] = None
    try:
        story_audio_path = os.path.join(
            STORY_AUDIO_UPLOAD_DIR, f"{safe_file_stem(submission.id)}.wav"
        )
        wrote_file = concatenate_scene_audio(
            [s.audioUrl for s in scenes_sorted if s.audioUrl],
            upload_dir=UPLOAD_DIR,
            output_path=story_audio_path,
        )
        if wrote_file:
            concatenated_audio_url = f"/uploads/story_audio/{os.path.basename(story_audio_path)}"
    except Exception as exc:
        logger.error("Story audio concatenation failed for %s: %s", submission.id, exc)

    story_feedback: Optional[dict] = None
    try:
        # Keep every scene in the transcript, even ones the ASR came back empty
        # for (silence, recognition miss) — dropping them would silently shrink
        # a 3-scene story down to whatever subset had text, so the "whole story"
        # feedback would really only be judging part of it.
        combined_transcript = "\n".join(
            f"[Scene {s.sceneIndex + 1}] {s.transcription.strip() or '(no speech transcribed for this scene)'}"
            for s in scenes_sorted
        )
        has_any_speech = any(s.transcription.strip() for s in scenes_sorted)
        if has_any_speech:
            # Average the per-scene Praat metrics already computed during
            # recording (tone accuracy, fluency, word-prosody/pronunciation)
            # across the whole story, so the story-level Fluency-and-Coherence
            # and Pronunciation dimensions are grounded in real acoustic data
            # instead of a text-only guess. Scenes with no speech contribute a
            # real 0, which correctly drags the average down for a genuine gap.
            scene_count = len(scenes_sorted) or 1
            avg_tone_accuracy = sum(s.toneAccuracy for s in scenes_sorted) / scene_count
            avg_fluency_score = sum(s.fluencyScore for s in scenes_sorted) / scene_count
            avg_pron_score = sum(s.pronScore for s in scenes_sorted) / scene_count
            story_feedback = await generate_story_feedback(
                combined_transcript,
                avg_tone_accuracy=avg_tone_accuracy,
                avg_fluency_score=avg_fluency_score,
                avg_pron_score=avg_pron_score,
            )
    except Exception as exc:
        logger.error("Story feedback generation failed for %s: %s", submission.id, exc)

    with connect_db() as db:
        db.execute(
            "UPDATE story_submissions SET concatenated_audio_url = ?, story_feedback = ? WHERE id = ?",
            (
                concatenated_audio_url,
                json.dumps(story_feedback) if story_feedback else None,
                submission.id,
            ),
        )

    return {
        **submission.model_dump(),
        "scenes": [s.model_dump() for s in scenes_sorted],
        "concatenatedAudioUrl": concatenated_audio_url,
        "storyFeedback": story_feedback,
    }


async def save_uploaded_audio(file: UploadFile, record_id: str) -> str:
    extension = extension_from_upload(file.filename, file.content_type, default=".wav")
    filename = f"{safe_file_stem(record_id)}{extension}"
    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
    content = await file.read()
    with open(path, "wb") as output:
        output.write(content)
    return f"/uploads/audio/{filename}"


def persist_story_frame_images(story_id: str, frames: list[dict]) -> list[dict]:
    # Load existing frames so we can delete replaced image files
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = ?", (story_id,)
        ).fetchone()
    old_frames = json.loads(row["frames"] or "[]") if row else []

    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        image_url = frame.get("imageUrl", "")
        if image_url.startswith("data:image/"):
            new_url = save_data_url_image(image_url, story_id, index)
            # Remove the old uploaded file if it differs from the new one
            old_url = old_frames[index - 1].get("imageUrl", "") if index - 1 < len(old_frames) else ""
            if old_url and old_url != new_url and old_url.startswith("/uploads/"):
                remove_uploaded_file(old_url)
            frame = {**frame, "imageUrl": new_url}
        stored_frames.append(frame)
    return stored_frames


def persist_story_frame_audio(story_id: str, frames: list[dict]) -> list[dict]:
    # Load existing frames so we can delete replaced audio files
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = ?", (story_id,)
        ).fetchone()
    old_frames = json.loads(row["frames"] or "[]") if row else []

    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        audio_url = frame.get("listenAudioUrl") or ""
        if audio_url.startswith("data:audio/"):
            new_url = save_data_url_audio(audio_url, story_id, index)
            old_url = old_frames[index - 1].get("listenAudioUrl", "") if index - 1 < len(old_frames) else ""
            if old_url and old_url != new_url and old_url.startswith("/uploads/"):
                remove_uploaded_file(old_url)
            frame = {**frame, "listenAudioUrl": new_url}
        stored_frames.append(frame)
    return stored_frames


def save_data_url_audio(data_url: str, story_id: str, index: int) -> str:
    header, _, data = data_url.partition(",")
    if not data:
        return data_url

    mime = header.removeprefix("data:").split(";")[0]
    extension = extension_from_mime(mime, default=".webm")
    ts = int(time.time() * 1000) % 1_000_000
    filename = f"{safe_file_stem(story_id)}-frame-{index}-audio-{ts}{extension}"
    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
    content = (
        base64.b64decode(data)
        if ";base64" in header
        else unquote_to_bytes(data)
    )
    with open(path, "wb") as output:
        output.write(content)
    return f"/uploads/audio/{filename}"


def save_data_url_image(data_url: str, story_id: str, index: int) -> str:
    header, _, data = data_url.partition(",")
    if not data:
        return data_url

    mime = header.removeprefix("data:").split(";")[0]
    extension = extension_from_mime(mime, default=".png")
    ts = int(time.time() * 1000) % 1_000_000  # 6-digit ms suffix busts cache on replace
    filename = f"{safe_file_stem(story_id)}-frame-{index}-{ts}{extension}"
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


_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


async def resolve_media_b64(ref: str) -> Optional[Tuple[str, str]]:
    """Resolve a data:, local /uploads/..., or remote http(s) reference to
    (base64_data, mime_type), fetching remote URLs from the server rather
    than the browser.

    This matters because story frames built via AI image generation
    (DALL-E / Pollinations.ai) keep their original third-party URL, and
    those hosts don't grant CORS permission for arbitrary origins — a
    browser-side fetch() of them is blocked. A server-to-server request has
    no CORS restriction at all, so resolving here sidesteps the problem.
    """
    ref = (ref or "").strip()
    if not ref:
        return None

    if ref.startswith("data:"):
        header, _, data = ref.partition(",")
        mime = header.removeprefix("data:").split(";")[0] or "application/octet-stream"
        return data, mime

    if ref.startswith("/uploads/"):
        relative_path = ref.removeprefix("/uploads/").replace("/", os.sep)
        path = os.path.abspath(os.path.join(UPLOAD_DIR, relative_path))
        upload_root = os.path.abspath(UPLOAD_DIR)
        if not path.startswith(upload_root) or not os.path.exists(path):
            return None
        mime = (
            _IMAGE_MIME_BY_EXT.get(os.path.splitext(path)[1].lower())
            or mimetypes.guess_type(path)[0]
            or "application/octet-stream"
        )
        with open(path, "rb") as fh:
            return base64.b64encode(fh.read()).decode(), mime

    if ref.startswith("http://") or ref.startswith("https://"):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(ref)
            if response.status_code != 200:
                return None
            mime = response.headers.get("content-type", "application/octet-stream").split(";")[0]
            return base64.b64encode(response.content).decode(), mime
        except Exception:
            return None

    return None


async def resolve_image_b64(image_ref: str) -> Optional[Tuple[str, str]]:
    """Resolve a scene image reference to (base64_data, mime_type) for vision
    prompts. SVG is excluded since vision models (Gemini, OpenAI) don't
    support it."""
    result = await resolve_media_b64(image_ref)
    if result and result[1] == "image/svg+xml":
        return None
    return result


@app.get("/api/inline-media")
async def inline_media(url: str = Query(..., max_length=2000)):
    """Resolve an image/audio reference (local /uploads/... path or a remote
    http(s) URL, e.g. a DALL-E/Pollinations.ai-hosted story image) to a
    base64 data URL. Used by story export so the browser never has to
    fetch() a third-party host directly, which CORS would otherwise block.
    """
    result = await resolve_media_b64(url)
    if result is None:
        raise HTTPException(status_code=404, detail="Could not resolve that media reference.")
    data, mime = result
    return {"dataUrl": f"data:{mime};base64,{data}"}


@app.post("/api/generate-story-images", response_model=StoryImageGenerationResponse)
async def generate_story_images(request: StoryImageGenerationRequest, req: Request):
    """
    Generate a six-image story sequence plan from a classroom situation.
    Gemini creates the scene plan when configured; deterministic local fallback
    keeps the teacher workflow usable offline.
    """
    client_ip = req.client.host if req.client else "unknown"
    _check_rate_limit(f"gen-images:{client_ip}", max_requests=10, window_seconds=60)

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
            logger.warning("Gemini story image planning failed, using local fallback: %s", exc)

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


@app.get("/api/ai-providers")
async def get_ai_providers():
    """List language-feedback engines for the student-facing engine picker.

    Each entry reports whether it is usable right now (cloud engines need an
    API key). ``default`` is the env-configured engine used when the student
    doesn't pick one.
    """
    return {"providers": available_providers(), "default": default_provider()}


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
    ai_provider: str = "",
    scene_image_url: str = "",
    scene_grammar_pattern: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
) -> AnalysisResponse:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        transcription_model = ""
        ai_feedback = None
        image_b64, image_mime = await resolve_image_b64(scene_image_url) or (None, "")

        # For cloud AI providers that support audio input, send the recording +
        # vocabulary together so the model can directly hear which words were spoken.
        # Groq chains Whisper → LLaMA in one call (no audio LLM yet).
        # Falls back to the normal ASR → text → feedback path on any error.
        _audio_assessors = {
            "gemini": (GEMINI_API_KEY, "ai_feedback", "assess_audio_with_gemini", "gemini-audio"),
            "openai": (OPENAI_API_KEY, "ai_feedback", "assess_audio_with_openai", "openai-audio"),
            "groq":   (GROQ_API_KEY,   "ai_feedback", "assess_audio_with_groq",   "groq-audio"),
        }
        chosen_provider = (ai_provider or "").strip().lower()
        audio_assessed = False
        if not transcription.strip() and chosen_provider in _audio_assessors:
            api_key, module, fn_name, tag = _audio_assessors[chosen_provider]
            if api_key:
                try:
                    import importlib
                    mod = importlib.import_module(module)
                    audio_result = await getattr(mod, fn_name)(
                        content, scene_prompt, scene_vocabulary,
                        image_b64=image_b64, image_mime=image_mime,
                        scene_grammar_pattern=scene_grammar_pattern, scene_suggested_answer=scene_suggested_answer,
                        scene_attempt_number=scene_attempt_number,
                    )
                    transcription = convert_to_traditional_chinese(audio_result["transcription"])
                    transcription_model = tag
                    ai_feedback = audio_result["feedback"]
                    audio_assessed = True
                except Exception as exc:
                    logger.warning(f"{chosen_provider} audio assessment failed, falling back: {exc}")

        if not transcription.strip() and asr_model.strip():
            transcription_result = await transcribe_audio_content(
                content, asr_model.strip(), vocab_hint=scene_vocabulary
            )
            transcription = transcription_result.text
            transcription_model = transcription_result.model

        def _run_praat(path: str, tx: str):
            return analyze_all(path, tx)

        # Run Praat (CPU-bound, threadpool) and AI feedback (I/O-bound) in parallel.
        # If audio assessment already produced feedback above, skip the feedback call.
        # After both finish, patch pronunciation_note with real Praat numbers.
        feedback_coro = (
            asyncio.sleep(0)  # no-op placeholder when feedback already done
            if audio_assessed
            else generate_language_feedback(
                transcription, scene_prompt, scene_vocabulary, provider=ai_provider or None,
                image_b64=image_b64, image_mime=image_mime,
                scene_grammar_pattern=scene_grammar_pattern, scene_suggested_answer=scene_suggested_answer,
                scene_attempt_number=scene_attempt_number,
            )
        )
        (praat_result, maybe_feedback) = await asyncio.gather(
            run_in_threadpool(_run_praat, tmp_path, transcription),
            feedback_coro,
        )
        if not audio_assessed:
            ai_feedback = maybe_feedback
        (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
         word_prosody, detected_tone, tone_accuracy, feedback,
         pause_analysis) = praat_result

        # No speech → noise from the mic can spuriously match a tone reference
        if not transcription.strip():
            tone_accuracy = 0
            detected_tone = 0
            fluency_score = 0.0

        vowel_quality = classify_vowel_quality(formants)
        tone_direction = build_tone_direction(pitch_contour, detected_tone, tone_accuracy)

        # The parallel feedback call ran before Praat finished. Recompute the
        # local CAF feedback now that we have the acoustic numbers: when the
        # provider is local, swap in the full grounded result; for an external
        # provider, only patch its pronunciation_note with the real Praat data.
        from ai_feedback import fallback_language_feedback as _local_fb
        local_fb = _local_fb(
            transcription, scene_prompt, scene_vocabulary,
            praat_tone_accuracy=float(tone_accuracy),
            praat_fluency_score=float(fluency_score),
            praat_vowel_quality=vowel_quality or "",
            praat_pause_analysis=pause_analysis,
            praat_speech_rate=float(speech_rate),
            word_prosody=word_prosody,
            image_b64=image_b64,
            scene_grammar_pattern=scene_grammar_pattern,
            scene_suggested_answer=scene_suggested_answer,
            scene_attempt_number=scene_attempt_number,
        )
        if isinstance(ai_feedback, dict):
            if ai_feedback.get("provider") == "local":
                ai_feedback = local_fb
            else:
                ai_feedback["pronunciation_note"] = local_fb["pronunciation_note"]
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


_MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(10 * 1024 * 1024)))  # 10 MB


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_speech(
    file: UploadFile = File(...),
    transcription: str = Form(""),
    asr_model: str = Form(""),
    scene_prompt: str = Form(""),
    scene_vocabulary: str = Form(""),
    ai_provider: str = Form(""),
    scene_image_url: str = Form(""),
    scene_grammar_pattern: str = Form(""),
    scene_suggested_answer: str = Form(""),
    scene_attempt_number: int = Form(1),
    req: Request = None,
):
    """
    Analyze Chinese speech for tone, pitch, formants, speech rate, and fluency.
    If transcription is empty and asr_model is provided, transcribe first, then
    run Praat against the same audio. scene_prompt and scene_vocabulary are used
    to make AI and local feedback context-aware. scene_grammar_pattern and
    scene_suggested_answer give the AI a reference for judging whether the
    student's sentence actually means the right thing, before pronunciation
    feedback matters. scene_attempt_number drives indirect corrective feedback —
    hints only for the first two attempts on a scene, then the correct answer
    is revealed.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    if req is not None:
        client_ip = req.client.host if req.client else "unknown"
        _check_rate_limit(f"analyze:{client_ip}", max_requests=30, window_seconds=60)

    content = await file.read()
    if len(content) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum size is {_MAX_AUDIO_BYTES // (1024 * 1024)} MB.",
        )

    try:
        return await asyncio.wait_for(
            _do_analyze(
                content, transcription, asr_model, scene_prompt, scene_vocabulary, ai_provider, scene_image_url,
                scene_grammar_pattern, scene_suggested_answer, scene_attempt_number,
            ),
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


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    model: str = Form("ctwhisper"),
    vocab_hint: str = Form(""),
):
    """
    Transcribe audio to text using the requested backend ASR model.
    The default upload flow uses local Chinese/Taiwanese Whisper.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    try:
        content = await file.read()
        result = await transcribe_audio_content(content, model, vocab_hint=vocab_hint)
        if vocab_hint.strip():
            result.text = correct_homophones(result.text, vocab_hint)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in transcribe_speech")
        raise HTTPException(
            status_code=500,
            detail=f"Error transcribing speech: {str(e)}"
        )


async def transcribe_audio_content(
    audio_content: bytes,
    model: str,
    vocab_hint: str = "",
) -> TranscriptionResponse:
    if model == "auto":
        return await transcribe_with_auto_fallback(audio_content, vocab_hint=vocab_hint)

    if model == "openai":
        if not OPENAI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key not configured"
            )
        return await transcribe_with_openai(audio_content, vocab_hint=vocab_hint)

    if model == "gemini":
        if not GEMINI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="Gemini API key not configured"
            )
        return await transcribe_with_gemini(audio_content, vocab_hint=vocab_hint)

    if model == "groq":
        if not GROQ_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="Groq API key not configured"
            )
        return await transcribe_with_groq(audio_content, vocab_hint=vocab_hint)

    if model == "funasr":
        return await transcribe_with_funasr(audio_content)

    if model in {"ctwhisper", "chinese_taiwanese_whisper"}:
        return await transcribe_with_ct_whisper(audio_content, vocab_hint=vocab_hint)

    if model == "vibevoice":
        return await transcribe_with_vibevoice(audio_content)

    raise HTTPException(
        status_code=400,
        detail="Invalid model. Use 'auto', 'ctwhisper', 'openai', 'gemini', 'groq', 'funasr', or 'vibevoice'"
    )


async def transcribe_with_auto_fallback(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    errors = []
    for provider in ASR_FALLBACK_ORDER:
        if provider == "gemini" and not GEMINI_API_KEY:
            errors.append("gemini: missing API key")
            continue
        if provider == "openai" and not OPENAI_API_KEY:
            errors.append("openai: missing API key")
            continue
        if provider == "groq" and not GROQ_API_KEY:
            errors.append("groq: missing API key")
            continue

        try:
            result = await transcribe_audio_content(audio_content, provider, vocab_hint=vocab_hint)
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
    logger.error("Auto ASR failed. Errors: %s", errors)
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
        logger.warning("Image generation failed (seed=%s): %s", seed, exc)
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


def correct_homophones(text: str, vocab_hint: str) -> str:
    """Replace homophones in transcript with vocab words that share the same tone-aware pinyin."""
    vocab_words = [w.strip() for w in vocab_hint.split(",") if w.strip()]
    # Build mapping: pinyin-with-tones -> vocab word (longest match wins)
    vocab_words.sort(key=len, reverse=True)
    pinyin_to_vocab: dict[str, str] = {}
    for word in vocab_words:
        py = " ".join(lazy_pinyin(word, style=Style.TONE3))
        pinyin_to_vocab[py] = word

    if not pinyin_to_vocab:
        return text

    # Slide a window over the transcript characters and replace matching runs
    chars = list(text)
    max_len = max(len(w) for w in vocab_words)
    i = 0
    result: list[str] = []
    while i < len(chars):
        replaced = False
        for length in range(min(max_len, len(chars) - i), 0, -1):
            segment = "".join(chars[i : i + length])
            py = " ".join(lazy_pinyin(segment, style=Style.TONE3))
            if py in pinyin_to_vocab and segment != pinyin_to_vocab[py]:
                result.append(pinyin_to_vocab[py])
                i += length
                replaced = True
                break
        if not replaced:
            result.append(chars[i])
            i += 1
    return "".join(result)


async def transcribe_with_openai(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    """Transcribe using OpenAI Whisper API."""
    async with httpx.AsyncClient() as client:
        files = {"file": ("audio.wav", audio_content, "audio/wav")}
        data = {"model": "whisper-1", "language": "zh"}
        if vocab_hint.strip():
            # Whisper uses the prompt to bias recognition toward these words/phrases.
            data["prompt"] = vocab_hint.strip()

        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files=files,
            data=data,
        )

        if response.status_code != 200:
            raise Exception(f"OpenAI API error: {response.text}")

        result = response.json()
        text = convert_to_traditional_chinese(result["text"])
        return TranscriptionResponse(text=text, model="openai")


async def transcribe_with_groq(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    """Transcribe using Groq's whisper-large-v3 (free, fast, accurate for Traditional Chinese)."""
    async with httpx.AsyncClient(timeout=30) as client:
        files = {"file": ("audio.wav", audio_content, "audio/wav")}
        data = {
            "model": GROQ_WHISPER_MODEL,
            "language": "zh",
            "response_format": "text",
        }
        if vocab_hint.strip():
            data["prompt"] = vocab_hint.strip()

        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files=files,
            data=data,
        )

        if response.status_code != 200:
            raise Exception(f"Groq API error: {response.text}")

        text = convert_to_traditional_chinese(response.text.strip())
        return TranscriptionResponse(text=text, model="groq")


async def transcribe_with_gemini(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    """Transcribe using Google Gemini API."""
    import base64

    audio_base64 = base64.b64encode(audio_content).decode()

    vocab_line = (
        f" The speaker may use these words: {vocab_hint.strip()}."
        if vocab_hint.strip() else ""
    )

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
                            "text": (
                                "Transcribe this Mandarin audio to Traditional Chinese (繁體中文)."
                                f"{vocab_line}"
                                " Output only the transcription — no explanations, no pinyin, no added punctuation."
                            )
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
        text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = convert_to_traditional_chinese(text)
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
        return convert_to_traditional_chinese(text)
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


def _transcribe_with_ct_whisper_sync(audio_content: bytes, vocab_hint: str = "") -> str:
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

        generate_kwargs: dict = {
            "forced_decoder_ids": forced_decoder_ids,
            "max_new_tokens": 128,
        }
        if vocab_hint.strip():
            prompt_ids = processor.get_prompt_ids(vocab_hint.strip(), return_tensors="pt")
            generate_kwargs["prompt_ids"] = prompt_ids.to(device)

        with torch.no_grad():
            predicted_ids = model.generate(input_features, **generate_kwargs)

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


async def transcribe_with_ct_whisper(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    """Transcribe using a Chinese/Taiwanese Whisper model."""
    text = await run_in_threadpool(_transcribe_with_ct_whisper_sync, audio_content, vocab_hint)
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
