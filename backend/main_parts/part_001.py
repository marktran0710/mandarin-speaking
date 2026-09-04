from fastapi import Depends, FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from typing import Any, Callable, Dict, Literal, Optional, List, Tuple
import base64
import io
import ipaddress
import logging
import logging.handlers
import mimetypes
import os
import tempfile
import secrets
import time
import collections
import httpx
from dotenv import load_dotenv
import json
import asyncio
import numpy as np
import threading
import datetime
import socket
from contextlib import asynccontextmanager
from urllib.parse import quote, unquote_to_bytes, urlparse
from pathlib import Path
from starlette.concurrency import run_in_threadpool
from config import settings
import auth

# ── Structured logging ─────────────────────────────────────────────────────
# File handler alongside the console one - a PowerShell window's scrollback
# is gone the moment it closes or scrolls past its buffer, so a crash or an
# overnight incident during an unattended classroom session had nothing to
# review after the fact. 10MB x 5 backups keeps this bounded without a
# separate log-rotation job.
_LOG_DIR = Path(os.getenv("LOG_DIR", Path(__file__).parent / "logs"))
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_log_formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_log_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
)
_log_file_handler.setFormatter(_log_formatter)
_log_console_handler = logging.StreamHandler()
_log_console_handler.setFormatter(_log_formatter)
logging.basicConfig(level=logging.INFO, handlers=[_log_console_handler, _log_file_handler])
logger = logging.getLogger("speaking_app")
from database import (
    close_db,
    connect_db,
    init_db,
    pool_max_size,
)
import anyio
from psycopg.types.json import Jsonb

import caf_metrics

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
    generate_comprehensive_feedback,
)
from ai_feedback import (
    generate_language_feedback,
    GEMINI_FEEDBACK_MODEL,
    GROQ_FEEDBACK_MODEL,
)
from reference_voice import (
    extract_scene_reference_curves,
    extract_scene_reference_from_audio,
)
from pinyin_service import canonical_pinyin, canonical_pinyin_tone3

# Load backend/.env first, then root .env.local for local full-stack runs.
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

OPENAPI_TAGS = [
    {
        "name": "admin",
        "description": "Administration endpoints for managing application data and settings.",
    },
    {
        "name": "teacher-review",
        "description": "Teacher-only endpoints for reviewing student work and feedback.",
    },
]

app = FastAPI(
    title="Mandarin Speaking Practice API",
    version="1.0.0",
    description=(
        "Backend API for the Mandarin Speaking Practice application. "
        "It supports learning content, speech analysis, audio submissions, "
        "and teacher review workflows."
    ),
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)
FRONTEND_DIST = settings.frontend_dist
REMOTE_MEDIA_ALLOWED_HOSTS = settings.remote_media_allowed_hosts
UPLOAD_DIR = settings.upload_dir
AUDIO_UPLOAD_DIR = settings.audio_upload_dir
IMAGE_UPLOAD_DIR = settings.image_upload_dir
STORY_AUDIO_UPLOAD_DIR = settings.story_audio_upload_dir
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)
os.makedirs(STORY_AUDIO_UPLOAD_DIR, exist_ok=True)
@app.get("/uploads/{relative_path:path}")
def serve_upload(
    relative_path: str,
    identity: auth.Identity = Depends(auth.get_current_identity),
):
    """Serve uploaded media only to an authenticated session."""
    upload_root = Path(UPLOAD_DIR).resolve()
    requested = (upload_root / unquote_to_bytes(relative_path).decode("utf-8")).resolve()
    if requested != upload_root and upload_root not in requested.parents:
        raise HTTPException(status_code=404, detail="Media not found.")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Media not found.")
    if identity.role == "student":
        stored_url = f"/uploads/{relative_path.replace(os.sep, '/')}"
        with connect_db() as db:
            owns_audio = db.execute(
                "SELECT 1 FROM audio_records WHERE student_id = %s AND audio_url = %s LIMIT 1",
                (identity.id, stored_url),
            ).fetchone()
            owns_story_audio = db.execute(
                "SELECT 1 FROM story_submissions WHERE student_id = %s AND concatenated_audio_url = %s LIMIT 1",
                (identity.id, stored_url),
            ).fetchone()
            is_published_lesson_media = db.execute(
                "SELECT 1 FROM custom_stories WHERE published = TRUE AND frames::text LIKE %s LIMIT 1",
                (f"%{stored_url}%",),
            ).fetchone()
        if not owns_audio and not owns_story_audio and not is_published_lesson_media:
            raise HTTPException(status_code=403, detail="Media access is not allowed.")
    media_type, _ = mimetypes.guess_type(str(requested))
    return FileResponse(requested, media_type=media_type or "application/octet-stream")


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), payment=()")
    return response


@app.on_event("startup")
async def startup_event():
    if os.getenv("APP_ENV", "development").lower() == "production":
        if os.getenv("COOKIE_SECURE", "false").lower() != "true":
            raise RuntimeError("COOKIE_SECURE=true is required in production.")
        if not os.getenv("ADMIN_PASSWORD", ""):
            raise RuntimeError("ADMIN_PASSWORD must be configured in production.")
        if not Path(UPLOAD_DIR).is_absolute() or not str(Path(UPLOAD_DIR)).startswith("/data"):
            raise RuntimeError("Production uploads must live on the persistent /data volume.")
    init_db()

    # DB-backed routes are plain `def`, so Starlette dispatches each to a
    # worker thread. Align the default thread limiter with the DB pool size so
    # we never run more concurrent blocking queries than the pool can serve -
    # extra threads would otherwise pile up waiting on connection checkout and
    # hit the pool timeout. ASR/Praat keep their own smaller semaphore on top.
    anyio.to_thread.current_default_thread_limiter().total_tokens = pool_max_size()


@app.on_event("shutdown")
async def shutdown_database():
    close_db()


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


def get_cors_origin_regex() -> str | None:
    """Allow the local pilot UI to use the computer as a LAN server.

    A production deployment should set CORS_ORIGINS explicitly. The fallback
    only accepts HTTP origins on loopback/private IPv4 ranges and the local
    development ports used by this project.
    """
    if os.getenv("CORS_ORIGINS"):
        return None
    return (
        r"^https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])"
        r"(?:\.\d{1,3}){2}):(?:3000|5173|5174|5175|5176|9000)$"
    )

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
    allow_origin_regex=get_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
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
OPENAI_API_KEY = settings.openai_api_key
GEMINI_API_KEY = settings.gemini_api_key
GROQ_API_KEY = settings.groq_api_key
GROQ_WHISPER_MODEL = settings.groq_whisper_model
# Groq's whisper-large-v3 leads: it's dramatically more accurate for
# Traditional Chinese than the local whisper-small, and the deployed backend
# (Render free tier, CPU-only) has a GROQ_API_KEY but no GPU. The auto chain
# already skips providers whose key is missing, so local-only setups still
# fall through to ctwhisper unchanged.
ASR_FALLBACK_ORDER = list(settings.asr_fallback_order)
FUNASR_MODEL = settings.funasr_model
FUNASR_VAD_MODEL = settings.funasr_vad_model
FUNASR_PUNC_MODEL = settings.funasr_punc_model
CT_WHISPER_MODEL = settings.ct_whisper_model
CT_WHISPER_DEVICE = settings.ct_whisper_device
CT_WHISPER_LANGUAGE = settings.ct_whisper_language
CT_WHISPER_TASK = settings.ct_whisper_task
CT_WHISPER_CACHE_DIR = settings.ct_whisper_cache_dir
VIBEVOICE_ASR_MODEL = settings.vibevoice_asr_model
VIBEVOICE_DEVICE = settings.vibevoice_device
VIBEVOICE_TORCH_DTYPE = settings.vibevoice_torch_dtype
VIBEVOICE_WARM_ON_START = settings.vibevoice_warm_on_start
VIBEVOICE_MAX_NEW_TOKENS = settings.vibevoice_max_new_tokens
VIBEVOICE_MAX_TIME_SECONDS = settings.vibevoice_max_time_seconds
VIBEVOICE_CACHE_DIR = settings.vibevoice_cache_dir
_funasr_model = None
_ct_whisper_model = None
_vibevoice_asr_model = None
_vibevoice_load_lock = threading.Lock()
_vibevoice_load_thread = None
_vibevoice_load_error = None


# Pydantic models
class RecordingQualityMetrics(BaseModel):
    duration_seconds: float = Field(default=0.0, ge=0.0)
    rms: float = Field(default=0.0, ge=0.0)
    peak: float = Field(default=0.0, ge=0.0)
    clipping_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    voiced_seconds: float = Field(default=0.0, ge=0.0)
    voiced_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    energy_variation: float = Field(default=0.0, ge=0.0)
    pitch_points: int = Field(default=0, ge=0)


class FeedbackQuality(BaseModel):
    """Evidence gate for student-facing automated feedback.

    ``status`` is one of reliable/review/retry.  A score is only suitable
    for mastery/progress decisions when its corresponding ``can_score_*``
    flag is true.  Reason codes are stable API values; ``student_message`` is
    presentation text and may evolve independently.
    """

    status: Literal["reliable", "review", "retry"] = "retry"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    can_score_pronunciation: bool = False
    can_score_content: bool = False
    reason_codes: List[str] = Field(default_factory=list)
    student_message: str = ""
    metrics: RecordingQualityMetrics = Field(default_factory=RecordingQualityMetrics)


class ProcessingTraceStage(BaseModel):
    stage: str
    status: str
    duration_ms: float = 0.0
    model: Optional[str] = None
    provider: Optional[str] = None
    detail: Optional[str] = None
    reason_codes: List[str] = Field(default_factory=list)
    # What this stage actually received/produced, for the teacher debugger's
    # per-step input/output cards. Deliberately compact (not the full
    # response) — just this stage's own contract.
    input: Optional[Dict[str, Any]] = None
    output: Optional[Dict[str, Any]] = None


class ProcessingTrace(BaseModel):
    stages: List[ProcessingTraceStage] = Field(default_factory=list)
    total_duration_ms: float = 0.0


class ContentDiffSegment(BaseModel):
    type: Literal["match", "replace", "missing", "extra"]
    target: str = ""
    heard: str = ""


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
    # Set only when the caller passed `verify_word` — an independent real ASR
    # pass confirming whether the recording actually contains that word,
    # since `transcription` may have been supplied by the caller (not
    # detected) to score tone against a known target. None means no check
    # was requested (e.g. this wasn't a word-practice attempt).
    recognized_text: Optional[str] = None
    content_match: Optional[bool] = None
    content_diff: List[ContentDiffSegment] = Field(default_factory=list)
    feedback_quality: FeedbackQuality = Field(default_factory=FeedbackQuality)
    #: Sentence-level roll-up of the four-state tone diagnosis, plus the
    #: reason codes behind it. Diagnostic only: `controls_progression` is
    #: False and the lesson gate still runs on word_prosody[].passed.
    #: Per-syllable detail lives in word_prosody[].syllables[].
    tone_diagnostics: dict = Field(default_factory=dict)
    #: Backend-authoritative pronunciation gate used by the student UI. This
    #: is separate from the numeric tone score so a learner can see exactly
    #: whether every judged syllable cleared the current evidence threshold.
    pronunciation_mastery: dict = Field(default_factory=dict)
    #: Optional ACCEPT/UNCERTAIN/NEEDS_PRACTICE assistive layer (Candidate F1
    #: risk signal + Candidate E2 diagnostic, combined per the frozen
    #: `feedback_policy_protocol.json` rule). `None` unless
    #: `ENABLE_ASSISTIVE_FEEDBACK=1` is set AND the layer could compute a
    #: result for this utterance -- additive and diagnostic only, exactly
    #: like `tone_diagnostics`: does not touch `word_prosody[].passed` or
    #: any progression gate. See `assistive_feedback/pipeline.py`.
    assistive_feedback: Optional[List[dict]] = None
    processing_trace: ProcessingTrace = Field(default_factory=ProcessingTrace)


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


class VocabFromSentenceRequest(BaseModel):
    sentence: str


class VocabWordSuggestion(BaseModel):
    word: str
    pinyin: str
    pos: str
    translation: str


class VocabFromSentenceResponse(BaseModel):
    words: List[VocabWordSuggestion]


class PhraseFromSentenceRequest(BaseModel):
    sentence: str
    # How many phrases to request — the caller scales this with the story's
    # difficulty tier (e.g. 1 for easy, 2 for medium, 3 for hard) since a
    # longer/harder sentence naturally has more phrase-worthy chunks.
    count: int = 1


class PhraseSuggestion(BaseModel):
    phrase: str
    translation: str


class PhraseFromSentenceResponse(BaseModel):
    phrases: List[PhraseSuggestion]


class VocabDistractorWord(BaseModel):
    word: str
    translation: str
    context: Optional[str] = None
    # Distractors already shown to students for this word (from a prior
    # generation), so a regeneration call can top up the pool with genuinely
    # new options instead of the model re-suggesting the same ones.
    avoid: List[str] = []


class VocabDistractorRequest(BaseModel):
    words: List[VocabDistractorWord]
