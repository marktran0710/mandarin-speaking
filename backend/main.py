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
)
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

app = FastAPI(title="Speaking App Backend", version="1.0.0")
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "dist"
REMOTE_MEDIA_ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.getenv("REMOTE_MEDIA_ALLOWED_HOSTS", "").split(",")
    if host.strip()
}
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads"))
AUDIO_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "audio")
IMAGE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "images")
STORY_AUDIO_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "story_audio")
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)
os.makedirs(STORY_AUDIO_UPLOAD_DIR, exist_ok=True)
@app.get("/uploads/{relative_path:path}")
async def serve_upload(
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
OPENAI_API_KEY = clean_api_key(os.getenv("OPENAI_API_KEY") or os.getenv("VITE_OPENAI_API_KEY"))
GEMINI_API_KEY = clean_api_key(os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY"))
GROQ_API_KEY = clean_api_key(os.getenv("GROQ_API_KEY") or os.getenv("VITE_GROQ_API_KEY"))
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
# Groq's whisper-large-v3 leads: it's dramatically more accurate for
# Traditional Chinese than the local whisper-small, and the deployed backend
# (Render free tier, CPU-only) has a GROQ_API_KEY but no GPU. The auto chain
# already skips providers whose key is missing, so local-only setups still
# fall through to ctwhisper unchanged.
ASR_FALLBACK_ORDER = [
    model.strip()
    for model in os.getenv(
        "ASR_FALLBACK_ORDER",
        "groq,ctwhisper",
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


class VocabDistractorResult(BaseModel):
    word: str
    distractors: List[str]


class VocabDistractorResponse(BaseModel):
    results: List[VocabDistractorResult]


class VocabClozeWord(BaseModel):
    word: str
    translation: str
    context: Optional[str] = None
    # Sentences already generated for this word (from a prior generation),
    # so a regeneration call tops up the pool with a genuinely new sentence
    # instead of the model repeating itself.
    avoid: List[str] = []


class VocabClozeRequest(BaseModel):
    words: List[VocabClozeWord]


class VocabClozeResult(BaseModel):
    word: str
    # A natural sentence containing `word` verbatim (the blank is cut client
    # side by replacing that occurrence — the model isn't asked to place a
    # blank marker itself, which it does unreliably).
    sentence: str
    # Wrong-but-plausible Chinese words that could grammatically fill the
    # same blank — the cloze question's multiple-choice options.
    distractors: List[str]


class VocabClozeResponse(BaseModel):
    results: List[VocabClozeResult]


class VocabSynonymWord(BaseModel):
    word: str
    translation: str
    context: Optional[str] = None
    # Synonyms already generated for this word (from a prior generation), so
    # a regeneration call tops up the pool with a genuinely new synonym
    # instead of the model repeating itself.
    avoid: List[str] = []


class VocabSynonymRequest(BaseModel):
    words: List[VocabSynonymWord]


class VocabSynonymResult(BaseModel):
    word: str
    # A real Chinese word/phrase with (nearly) the same meaning as `word`.
    synonym: str
    # Wrong-but-plausible Chinese words — NOT synonyms of `word` — for the
    # "which word means the same?" multiple-choice options.
    distractors: List[str]


class VocabSynonymResponse(BaseModel):
    results: List[VocabSynonymResult]


class AudioRecordRequest(BaseModel):
    id: str
    timestamp: str
    duration: int
    transcription: str = ""
    model: str
    topicId: Optional[str] = None
    studentId: Optional[str] = None
    imageUrl: Optional[str] = None
    imageIndex: Optional[int] = None
    audioUrl: Optional[str] = None
    audioName: Optional[str] = None
    praatMetrics: Optional[dict] = None
    analysisVersion: Optional[str] = None
    analysisSchemaVersion: Optional[str] = None
    modelVersion: Optional[str] = None
    comparisonGroupId: Optional[str] = None
    sessionId: Optional[str] = None
    attemptId: Optional[str] = None
    attemptNumber: Optional[int] = None
    attemptType: Optional[str] = None


class SpeakingProgressRequest(BaseModel):
    studentId: str
    topicId: str
    sceneIndex: int
    attempts: int = 0
    bestTone: float = 0
    bestFluency: float = 0
    masteryPassed: bool = False
    contentPassed: bool = False
    clearedWords: List[str] = []
    # The latest accepted per-scene submission snapshot. Kept nullable so
    # rows written before this field was introduced remain fully compatible.
    latestResult: Optional[Dict[str, Any]] = None


class CustomStoryFrameRequest(BaseModel):
    imageUrl: str
    imageUrlMedium: Optional[str] = None
    imageUrlHard: Optional[str] = None
    prompt: str
    vocabulary: str = ""
    vocabularyGroups: Optional[List[dict]] = None
    grammarPattern: Optional[str] = None
    grammarExample: Optional[str] = None
    vocabularyPinyin: Optional[str] = None
    vocabularyPos: Optional[str] = None
    vocabularyTranslation: Optional[str] = None
    phrases: Optional[str] = None
    phrasesTranslation: Optional[str] = None
    suggestedAnswer: Optional[str] = None
    listenAudioUrl: Optional[str] = None
    listenAudioSource: Optional[str] = None
    listenScript: Optional[str] = None
    vocabularyAudioUrls: Optional[str] = None
    vocabularyReferenceCurves: Optional[str] = None
    sentenceReferenceCurves: Optional[str] = None
    vocabularyDistractors: Optional[str] = None
    # JSON-encoded array of arrays (one entry per word, aligned with the
    # comma-split `vocabulary` above) — each word's entry is a list of
    # AI-generated {sentence, distractors} cloze candidates, grown over time
    # the same way vocabularyDistractors is (see vocab_quiz_cloze / the
    # vocabulary-cloze PATCH endpoint).
    vocabularyCloze: Optional[str] = None
    # JSON-encoded array of arrays (one entry per word) — each word's entry
    # is a list of AI-generated {synonym, distractors} candidates, grown the
    # same way vocabularyCloze is.
    vocabularySynonym: Optional[str] = None
    # Medium/Hard tiers of the same scene — same plot, just progressively
    # more complex text (and optionally its own image via imageUrlMedium/
    # imageUrlHard above). Absent/blank means that tier hasn't been authored
    # yet; the student-facing conversion falls back to the base (Easy) field
    # above rather than showing blank content.
    promptMedium: Optional[str] = None
    promptHard: Optional[str] = None
    vocabularyMedium: Optional[str] = None
    vocabularyHard: Optional[str] = None
    vocabularyPinyinMedium: Optional[str] = None
    vocabularyPinyinHard: Optional[str] = None
    vocabularyPosMedium: Optional[str] = None
    vocabularyPosHard: Optional[str] = None
    vocabularyTranslationMedium: Optional[str] = None
    vocabularyTranslationHard: Optional[str] = None
    phrasesMedium: Optional[str] = None
    phrasesHard: Optional[str] = None
    phrasesTranslationMedium: Optional[str] = None
    phrasesTranslationHard: Optional[str] = None
    suggestedAnswerMedium: Optional[str] = None
    suggestedAnswerHard: Optional[str] = None
    listenAudioUrlMedium: Optional[str] = None
    listenAudioUrlHard: Optional[str] = None
    listenAudioSourceMedium: Optional[str] = None
    listenAudioSourceHard: Optional[str] = None
    listenScriptMedium: Optional[str] = None
    listenScriptHard: Optional[str] = None
    vocabularyAudioUrlsMedium: Optional[str] = None
    vocabularyAudioUrlsHard: Optional[str] = None
    vocabularyReferenceCurvesMedium: Optional[str] = None
    vocabularyReferenceCurvesHard: Optional[str] = None
    sentenceReferenceCurvesMedium: Optional[str] = None
    sentenceReferenceCurvesHard: Optional[str] = None


class CustomStoryRequest(BaseModel):
    id: str
    title: str
    learningGoal: str
    frames: List[CustomStoryFrameRequest]
    published: bool = False
    linear: bool = False
    firstFrameIsExample: bool = False
    lessonNumber: Optional[int] = None
    lessonSubOrder: Optional[int] = None
    narrativeMode: str = "story"
    rubricScores: Optional[Dict[str, Any]] = None


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
    # Praat pause-analysis data for this scene's recording — see
    # ai_feedback.generate_story_feedback for why this now feeds story-level
    # feedback directly (delivery matters more once scenes can hand the
    # student a suggestedAnswer to read, since vocab/grammar aren't a choice).
    pauseCount: float = 0
    longestPause: float = 0
    utteranceCount: float = 0
    # Judged pause placement + articulation rate — see caf_metrics.classify_pauses
    # and caf_metrics.speech_rate_verdict for how these are derived.
    choppyPauseCount: float = 0
    articulationRate: float = 0
    # The student's own self-rating for this scene's accepted attempt, taken
    # right after they listened back to it and before seeing the system's
    # verdict. Absent when the student skipped the prompt.
    selfEvalContent: Optional[Literal["good", "ok", "bad"]] = None
    selfEvalPronunciation: Optional[Literal["good", "ok", "bad"]] = None


class StorySubmissionRequest(BaseModel):
    id: str = Field(..., max_length=128)
    storyId: str = Field(..., max_length=128)
    storyTitle: str = Field(default="", max_length=200)
    studentName: str = Field(default="Student", max_length=100)
    studentId: Optional[str] = Field(default=None, max_length=128)
    submittedAt: str
    scenes: List[SceneSubmission] = []


class SubmissionReviewRequest(BaseModel):
    status: str
    note: Optional[str] = None


class VocabQuizQuestionResult(BaseModel):
    word: str = Field(..., max_length=200)
    correct: bool
    timeMs: int = Field(..., ge=0)


class VocabQuizAttemptRequest(BaseModel):
    id: str = Field(..., max_length=128)
    storyId: str = Field(..., max_length=128)
    studentName: str = Field(default="Student", max_length=100)
    studentId: Optional[str] = Field(default=None, max_length=128)
    mode: Optional[str] = None
    completedAt: str
    totalQuestions: int = Field(..., ge=1)
    correctCount: int = Field(..., ge=0)
    totalTimeMs: int = Field(..., ge=0)
    questionResults: List[VocabQuizQuestionResult] = []


class StudentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)


class StudentPasswordResetRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=100)


class QuizExclusion(BaseModel):
    """One piece of quiz material the teacher marked bad (see the teacher
    quiz-review page): a whole word ("word") or one candidate of a per-word
    AI pool ("cloze"/"synonym" with its pool index, or the whole
    "distractors" pool)."""
    word: str = Field(..., min_length=1, max_length=50)
    kind: str = Field(..., pattern="^(word|cloze|synonym|distractors)$")
    index: Optional[int] = Field(default=None, ge=0)


class QuizExclusionsUpdateRequest(BaseModel):
    exclusions: List[QuizExclusion]
    # The full per-word quiz material tree at save time, keyed by difficulty
    # tier (easy/medium/hard word text and pools can differ per tier), so
    # the Quiz Review page can diff live material against it next time
    # (new/changed/kept). Opaque here — the frontend owns the per-tier shape
    # and sends the whole map each time (merging in whichever tier changed),
    # so a save under one tier never clobbers another tier's baseline.
    materialSnapshot: Optional[Dict[str, List[dict]]] = None


class QuizClozeCandidateIn(BaseModel):
    sentence: str
    distractors: List[str] = []


class QuizSynonymCandidateIn(BaseModel):
    synonym: str
    distractors: List[str] = []


class QuizWordMaterialIn(BaseModel):
    """One word's current AI-generated quiz material, as the Quiz Review
    page already displays it (see storyToTopic/quizMaterialDiff) — the
    shape /quiz/validate and /quiz/approve both take, so the same JSON the
    frontend already builds for the diff snapshot can be sent as-is."""
    word: str
    translation: Optional[str] = None
    distractors: List[str] = []
    cloze: List[QuizClozeCandidateIn] = []
    synonym: List[QuizSynonymCandidateIn] = []


class QuizValidateRequest(BaseModel):
    words: List[QuizWordMaterialIn]
    exclusions: List[QuizExclusion] = []


class QuizValidateResultItem(BaseModel):
    word: str
    kind: str  # "translation" | "cloze" | "synonym" — matches the pools above
    poolIndex: Optional[int] = None
    status: str  # "clean" | "suspicious"
    reason: str = ""


class QuizValidateResponse(BaseModel):
    results: List[QuizValidateResultItem]


class QuizApproveRequest(BaseModel):
    level: str = Field(..., pattern="^(easy|medium|hard)$")
    # Selection-based, not exclusion-based: the caller builds this from only
    # the candidates a teacher explicitly checked in the opt-in review UI —
    # this becomes exactly what topicQuizEntries/storyToTopic serve students
    # for this tier once approved.
    material: List[QuizWordMaterialIn]


class QuizPendingApprovalsUpdateRequest(BaseModel):
    """The Quiz Review page's opt-in checkbox selections for one tier — not
    yet published (that's /quiz/approve), just surviving a page reload."""
    level: str = Field(..., pattern="^(easy|medium|hard)$")
    approvals: List[QuizExclusion]  # same {word, kind, index} shape, reused as-is


class QuizQuestionReplaceRequest(BaseModel):
    """Replaces one candidate's content in place — the existing vocabulary-*
    PATCH endpoints only merge new items into a pool, which can't fix an
    existing bad candidate's text. distractors has no poolIndex (editing it
    replaces the word's whole distractor list, matching how Quiz Review
    shows it as one row)."""
    frameIndex: int = Field(..., ge=0)
    wordIndex: int = Field(..., ge=0)
    kind: str = Field(..., pattern="^(translation|distractors|cloze|synonym)$")
    poolIndex: Optional[int] = Field(default=None, ge=0)
    # Translation edits change the teacher-authored correct answer.  The
    # field is explicit because Medium/Hard can own a separate translation
    # list; omitting it keeps the existing Easy/base behaviour.
    translationField: Optional[str] = Field(
        default=None,
        pattern="^(vocabularyTranslation|vocabularyTranslationMedium|vocabularyTranslationHard)$",
    )
    # distractors: List[str]; cloze: {sentence, distractors}; synonym: {synonym, distractors}
    # — a plain Any because the shape depends on `kind`; the handler validates it.
    value: Any


class StudentLoginRequest(BaseModel):
    # Either the roster id (preferred, stable) or the display name —
    # whichever the login form has in hand.
    studentId: Optional[str] = None
    name: Optional[str] = None
    password: str = Field(..., min_length=1, max_length=100)


class Student(BaseModel):
    id: str
    name: str
    createdAt: str

class TeacherCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6, max_length=100)

class TeacherLoginRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)

class TeacherUpdateRequest(BaseModel):
    password: Optional[str] = Field(default=None, min_length=6, max_length=100)
    status: Optional[str] = Field(default=None, pattern="^(active|inactive)$")


@app.get("/health")
async def health_check():
    """Liveness endpoint with explicit database and upload-storage status.

    Keep this endpoint HTTP-200 so dashboards can inspect a degraded service;
    deployment platforms should use ``/health/ready`` when they need a strict
    readiness signal.
    """
    db_ok = False
    try:
        with connect_db() as db:
            db.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB failure: %s", exc)
    storage_ok = False
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        probe_path = os.path.join(UPLOAD_DIR, f".write-probe-{os.getpid()}")
        with open(probe_path, "wb") as probe:
            probe.write(b"ok")
        os.unlink(probe_path)
        storage_ok = True
    except OSError as exc:
        logger.error("Health check upload-storage failure: %s", exc)
    return {
        "status": "ok" if db_ok and storage_ok else "degraded",
        "service": "Speaking App Backend",
        "database": "ok" if db_ok else "error",
        "storage": "ok" if storage_ok else "error",
    }


@app.get("/health/ready")
async def readiness_check():
    """Strict readiness probe used by deployment platforms."""
    result = await health_check()
    if result["status"] != "ok":
        raise HTTPException(status_code=503, detail=result)
    return result


def save_audio_record(record: AudioRecordRequest, owner_id: Optional[str] = None):
    metrics = dict(record.praatMetrics or {})
    if record.analysisVersion:
        metrics.setdefault("analysis_version", record.analysisVersion)
    if record.analysisSchemaVersion:
        metrics.setdefault("analysis_schema_version", record.analysisSchemaVersion)
    if record.modelVersion:
        metrics.setdefault("model_version", record.modelVersion)
    if record.comparisonGroupId:
        metrics.setdefault("comparison_group_id", record.comparisonGroupId)
    with connect_db() as db:
        if owner_id is not None:
            existing = db.execute(
                "SELECT student_id FROM audio_records WHERE id = %s",
                (record.id,),
            ).fetchone()
            if existing is not None and existing.get("student_id") != owner_id:
                raise HTTPException(status_code=409, detail="Audio record already belongs to another student.")
        db.execute(
            """
            INSERT INTO audio_records (
                id, timestamp, duration, transcription, model, topic_id, student_id,
                image_url, image_index, audio_url, audio_name, praat_metrics,
                session_id, attempt_id, attempt_number, attempt_type
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                timestamp = EXCLUDED.timestamp,
                duration = EXCLUDED.duration,
                transcription = EXCLUDED.transcription,
                model = EXCLUDED.model,
                topic_id = EXCLUDED.topic_id,
                student_id = EXCLUDED.student_id,
                image_url = EXCLUDED.image_url,
                image_index = EXCLUDED.image_index,
                audio_url = EXCLUDED.audio_url,
                audio_name = EXCLUDED.audio_name,
                praat_metrics = EXCLUDED.praat_metrics,
                session_id = EXCLUDED.session_id,
                attempt_id = EXCLUDED.attempt_id,
                attempt_number = EXCLUDED.attempt_number,
                attempt_type = EXCLUDED.attempt_type
            """,
            (
                record.id,
                record.timestamp,
                record.duration,
                record.transcription,
                record.model,
                record.topicId,
                record.studentId,
                record.imageUrl,
                record.imageIndex,
                record.audioUrl,
                record.audioName,
                Jsonb(metrics),
                record.sessionId,
                record.attemptId,
                record.attemptNumber,
                record.attemptType,
            ),
        )


MAX_VOCAB_DISTRACTORS_PER_WORD = 8


class VocabularyDistractorUpdate(BaseModel):
    frameIndex: int
    wordIndex: int
    distractors: List[str]


class VocabularyDistractorsUpdateRequest(BaseModel):
    updates: List[VocabularyDistractorUpdate]


# Lower than MAX_VOCAB_DISTRACTORS_PER_WORD: each cloze candidate bundles a
# whole sentence plus its own distractors, so a handful of varied sentences
# is plenty to avoid staleness without growing the pool unbounded.
MAX_VOCAB_CLOZE_PER_WORD = 4


class VocabularyClozeCandidate(BaseModel):
    sentence: str
    distractors: List[str]


class VocabularyClozeUpdate(BaseModel):
    frameIndex: int
    wordIndex: int
    candidates: List[VocabularyClozeCandidate]


class VocabularyClozeUpdateRequest(BaseModel):
    updates: List[VocabularyClozeUpdate]


MAX_VOCAB_SYNONYM_PER_WORD = 4


class VocabularySynonymCandidate(BaseModel):
    synonym: str
    distractors: List[str]


class VocabularySynonymUpdate(BaseModel):
    frameIndex: int
    wordIndex: int
    candidates: List[VocabularySynonymCandidate]


class VocabularySynonymUpdateRequest(BaseModel):
    updates: List[VocabularySynonymUpdate]


class GenerateModelVoiceRequest(BaseModel):
    frameIndex: int
    tier: str = "easy"


class GenerateModelVoiceBulkRequest(BaseModel):
    tiers: List[str] = ["easy", "medium", "hard"]


class TTSRequest(BaseModel):
    text: str
    voice: str = ""


async def save_uploaded_audio(file: UploadFile, record_id: str, owner_id: str = "") -> str:
    extension = extension_from_upload(file.filename, file.content_type, default=".wav")
    owner_stem = safe_file_stem(owner_id) if owner_id else "legacy"
    filename = f"{owner_stem}-{safe_file_stem(record_id)}{extension}"
    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
    content = await file.read()
    if len(content) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Maximum size is {_MAX_AUDIO_BYTES} bytes.",
        )
    # Write beside the target and replace atomically. A failed/interrupted
    # upload must never leave a truncated file under a URL already persisted
    # in audio_records.
    temp_path = f"{path}.tmp-{secrets.token_hex(8)}"
    with open(temp_path, "wb") as output:
        output.write(content)
    os.replace(temp_path, path)
    return f"/uploads/audio/{filename}"


def persist_story_frame_images(story_id: str, frames: list[dict]) -> list[dict]:
    # Load existing frames so we can delete replaced image files
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
        ).fetchone()
    old_frames = (row["frames"] or []) if row else []

    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        frame = dict(frame)
        # Easy/Medium/Hard each carry their own image now — every tier's
        # field is checked independently so replacing one tier's picture
        # doesn't touch the others' uploaded files.
        for field, suffix in (
            ("imageUrl", ""),
            ("imageUrlMedium", "-medium"),
            ("imageUrlHard", "-hard"),
        ):
            image_url = frame.get(field) or ""
            if image_url.startswith("data:image/"):
                new_url = save_data_url_image(image_url, story_id, f"{index}{suffix}")
                old_url = (
                    old_frames[index - 1].get(field, "")
                    if index - 1 < len(old_frames)
                    else ""
                )
                if old_url and old_url != new_url and old_url.startswith("/uploads/"):
                    remove_uploaded_file(old_url)
                frame[field] = new_url
        stored_frames.append(frame)
    return stored_frames


# Field-name suffix per difficulty tier, matching routers/stories.py's
# _TIER_SUFFIX convention (listenAudioUrl/listenAudioUrlMedium/listenAudioUrlHard).
_AUDIO_TIER_SUFFIXES = ("", "Medium", "Hard")


def persist_story_frame_audio(story_id: str, frames: list[dict]) -> list[dict]:
    # Load existing frames so we can delete replaced audio files
    with connect_db() as db:
        row = db.execute(
            "SELECT frames FROM custom_stories WHERE id = %s", (story_id,)
        ).fetchone()
    old_frames = (row["frames"] or []) if row else []

    stored_frames = []
    for index, frame in enumerate(frames, start=1):
        frame = dict(frame)
        old_frame = old_frames[index - 1] if index - 1 < len(old_frames) else {}
        for suffix in _AUDIO_TIER_SUFFIXES:
            field = f"listenAudioUrl{suffix}"
            audio_url = frame.get(field) or ""
            if not audio_url.startswith("data:audio/"):
                continue

            new_url = save_data_url_audio(audio_url, story_id, f"{index}{suffix.lower()}")
            old_url = old_frame.get(field, "") or ""
            if old_url and old_url != new_url and old_url.startswith("/uploads/"):
                remove_uploaded_file(old_url)
            frame[field] = new_url

            if new_url != old_url:
                _refresh_scene_reference_curves(
                    story_id, index - 1, frame, old_frame, suffix, new_url
                )
        stored_frames.append(frame)
    return stored_frames


def _refresh_scene_reference_curves(
    story_id: str, frame_index: int, frame: dict, old_frame: dict, suffix: str, audio_url: str
) -> None:
    """Re-derives a scene's per-word target pitch curves from its real model
    recording whenever a teacher uploads or re-records one, so the "target
    shape" a student practices against always reflects the actual final
    model audio (teacher voice or TTS) rather than going stale after a
    manual upload that bypasses the TTS generation endpoint.

    Best-effort: a scene with no suggested-answer/listen-script text, or an
    audio file the pitch tracker can't read, just keeps whatever reference
    curves (if any) it already had — it doesn't block saving the story.
    """
    sentence_text = (
        frame.get(f"listenScript{suffix}") or frame.get(f"suggestedAnswer{suffix}") or ""
    ).strip()
    if not sentence_text:
        return

    vocab_text = frame.get(f"vocabulary{suffix}") or ""
    words = [word.strip() for word in vocab_text.split(",") if word.strip()]

    relative_path = audio_url.removeprefix("/uploads/").replace("/", os.sep)
    audio_path = os.path.abspath(os.path.join(UPLOAD_DIR, relative_path))
    if not os.path.exists(audio_path):
        return

    try:
        word_results = (
            extract_scene_reference_from_audio(
                story_id=story_id,
                frame_index=frame_index,
                sentence_text=sentence_text,
                words=words,
                sentence_audio_path=audio_path,
                audio_dir=STORY_AUDIO_UPLOAD_DIR,
            )
            if words
            else []
        )
        sentence_curves = extract_scene_reference_curves(audio_path, sentence_text)
    except Exception:
        logger.warning(
            "Reference-curve extraction failed for story=%s frame=%s tier=%s",
            story_id, frame_index, suffix or "easy", exc_info=True,
        )
        return

    try:
        old_word_urls = json.loads(old_frame.get(f"vocabularyAudioUrls{suffix}") or "[]")
    except (json.JSONDecodeError, TypeError):
        old_word_urls = []
    for old_word_url in old_word_urls:
        if isinstance(old_word_url, str):
            remove_uploaded_file(old_word_url)

    frame[f"vocabularyAudioUrls{suffix}"] = json.dumps(
        [w["audio_url"] for w in word_results], ensure_ascii=False
    )
    frame[f"vocabularyReferenceCurves{suffix}"] = json.dumps([w["curve"] for w in word_results])
    frame[f"sentenceReferenceCurves{suffix}"] = json.dumps(
        sentence_curves, ensure_ascii=False
    )


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


def save_data_url_image(data_url: str, story_id: str, index) -> str:
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
    if not url or not url.startswith("/uploads/"):
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
        if len(data) > 7 * 1024 * 1024 or mime.lower() == "image/svg+xml":
            return None
        return data, mime

    if ref.startswith("/uploads/"):
        relative_path = ref.removeprefix("/uploads/").replace("/", os.sep)
        upload_root = Path(UPLOAD_DIR).resolve()
        path = (upload_root / relative_path).resolve()
        try:
            path.relative_to(upload_root)
        except ValueError:
            return None
        if not path.is_file():
            return None
        mime = (
            _IMAGE_MIME_BY_EXT.get(path.suffix.lower())
            or mimetypes.guess_type(str(path))[0]
            or "application/octet-stream"
        )
        if mime == "image/svg+xml":
            return None
        with path.open("rb") as fh:
            return base64.b64encode(fh.read()).decode(), mime

    if ref.startswith("http://") or ref.startswith("https://"):
        parsed = urlparse(ref)
        if not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.hostname.lower() not in REMOTE_MEDIA_ALLOWED_HOSTS:
            return None
        if parsed.port not in (None, 80, 443):
            return None
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
            if not addresses or any(
                not ipaddress.ip_address(address[4][0]).is_global
                for address in addresses
            ):
                return None
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                async with client.stream("GET", ref) as response:
                    if response.status_code != 200:
                        return None
                    content_length = int(response.headers.get("content-length", "0") or 0)
                    if content_length > 5 * 1024 * 1024:
                        return None
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > 5 * 1024 * 1024:
                            return None
                        chunks.append(chunk)
            mime = response.headers.get("content-type", "application/octet-stream").split(";")[0]
            return base64.b64encode(b"".join(chunks)).decode(), mime
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


ANALYZE_TIMEOUT_SECONDS = int(os.getenv("ANALYZE_TIMEOUT_SECONDS", "120"))

# Caps how many /api/analyze requests run their CPU-bound stages (Praat,
# local ASR) at once. run_in_threadpool offloads this work off the event
# loop, but the threadpool itself has no size limit tied to actual CPU
# capacity - a classroom of ~50 students recording around the same moment
# would otherwise spin up dozens of CPU-heavy analyses simultaneously and
# thrash every core, making every single one slower rather than a few
# finishing quickly in sequence. Extra requests simply queue for a slot
# instead of being rejected; ANALYZE_TIMEOUT_SECONDS still bounds how long
# any one request (including its queue wait) can take.
ANALYZE_CONCURRENCY_LIMIT = int(os.getenv("ANALYZE_CONCURRENCY_LIMIT", "4"))
analyze_semaphore = asyncio.Semaphore(ANALYZE_CONCURRENCY_LIMIT)
ANALYZE_QUEUE_LIMIT = int(os.getenv("ANALYZE_QUEUE_LIMIT", "16"))
_analysis_admission_lock = asyncio.Lock()
_analysis_waiters = 0


@asynccontextmanager
async def acquire_analysis_slot():
    """Admit a bounded number of CPU/ASR requests across all analysis routes."""
    global _analysis_waiters
    async with _analysis_admission_lock:
        if _analysis_waiters >= ANALYZE_QUEUE_LIMIT:
            raise HTTPException(
                status_code=503,
                detail="Analysis capacity is temporarily full. Please retry shortly.",
                headers={"Retry-After": "5"},
            )
        _analysis_waiters += 1

    counted_as_waiter = True
    try:
        async with analyze_semaphore:
            async with _analysis_admission_lock:
                _analysis_waiters -= 1
            counted_as_waiter = False
            yield
    finally:
        if counted_as_waiter:
            async with _analysis_admission_lock:
                _analysis_waiters -= 1


def apply_recording_qc_to_diagnostics(word_prosody: list, feedback_quality: dict) -> dict:
    """Gate every syllable diagnosis on recording quality, then summarize.

    QC answers "can this measurement be trusted?" and nothing else — it is
    never blended into a score. When the answer is no, each syllable's verdict
    is replaced by INVALID_AUDIO with the recording's own reason codes
    attached, because "record that again" is the honest response and "you said
    it wrong" is not.

    Mutates ``word_prosody`` in place (it is the same list going out on the
    response) and returns the sentence-level summary. The legacy ``passed``
    fields are left exactly as the analyzer produced them.
    """
    from tone_decision import DiagnosticStatus, QcEvidence, summarize_sentence

    quality = feedback_quality or {}
    evidence = QcEvidence(
        can_score_pronunciation=quality.get("can_score_pronunciation", True) is not False,
        reason_codes=tuple(quality.get("reason_codes") or ()),
    )
    recording_unusable = evidence.unusable_recording

    statuses = []
    for word in word_prosody or []:
        for syllable in word.get("syllables") or []:
            if "diagnostic_status" not in syllable:
                continue
            if recording_unusable:
                syllable["diagnostic_status"] = DiagnosticStatus.INVALID_AUDIO.value
                syllable["diagnostic_reason"] = "recording_quality_unusable"
                syllable["contour_match_score"] = None
            statuses.append(DiagnosticStatus(syllable["diagnostic_status"]))
        if recording_unusable and word.get("diagnostic_status"):
            word["diagnostic_status"] = DiagnosticStatus.INVALID_AUDIO.value

    summary = summarize_sentence(statuses)
    summary["recording_reason_codes"] = list(evidence.reason_codes)
    # Progression is untouched by any of the above and says so explicitly, so
    # nobody reading the payload has to infer which field drove the unlock.
    # TODO(calibration): whether UNCERTAIN should be allowed through the
    # progression gate must be decided from human-rater agreement data, not by
    # loosening it to raise pass rates.
    summary["controls_progression"] = False
    return summary


# Sentence-level gate: a recording passes when at least this fraction of
# its judged syllables passed. Engineering default, chosen to match the
# "students should be able to move on with occasional per-syllable
# imperfections" UX; not a calibrated cutoff.
SENTENCE_SYLLABLE_PASS_RATIO = float(
    os.getenv("SENTENCE_SYLLABLE_PASS_RATIO", "0.80")
)


def build_pronunciation_mastery(
    word_prosody: list,
    feedback_quality: dict,
    *,
    content_match: Optional[bool] = None,
    content_check_requested: bool = False,
    missing_target_units: Optional[list[str]] = None,
) -> dict:
    """Return one explicit, evidence-gated pronunciation verdict.

    The percentage is useful for progress history, but it cannot by itself
    answer the learner's practical question: "Did I pass this sentence?"
    This gate requires a passing verdict for every syllable that has enough
    pitch evidence to be judged. Short/unvoiced syllables are reported as
    unjudged instead of being turned into a false pronunciation fail, while a
    recording with no measurable syllables remains ``not_judged``.
    """
    quality = feedback_quality or {}
    missing_units = [unit for unit in (missing_target_units or []) if unit]
    # Keep missing content as one learner-facing phrase instead of exposing
    # every missing character as a separate practice item.
    missing_parts = ["".join(missing_units)] if missing_units else []
    if quality.get("can_score_pronunciation") is False:
        return {
            "passed": False,
            "status": "not_judged",
            "passed_syllables": 0,
            "total_syllables": 0,
            "failed_words": [],
            "practice_parts": missing_parts,
            "content_match": content_match,
            "missing_target_units": missing_units,
            "message": quality.get("student_message") or "Record again so the system can measure your tones.",
        }

    syllables = [
        syllable
        for word in word_prosody or []
        for syllable in word.get("syllables") or []
    ]
    judged_syllables = [
        syllable for syllable in syllables if syllable.get("passed") is not None
    ]
    failed_words = [
        word.get("token", "")
        for word in word_prosody or []
        if word.get("passed") is False
        or any(syllable.get("passed") is False for syllable in word.get("syllables") or [])
    ]
    failed_words = [word for word in failed_words if word]

    if not judged_syllables:
        return {
            "passed": False,
            "status": "not_judged",
            "passed_syllables": 0,
            "total_syllables": 0,
            "failed_words": failed_words,
            "practice_parts": list(dict.fromkeys([*failed_words, *missing_parts])),
            "content_match": content_match,
            "missing_target_units": missing_units,
            "message": "Not enough measured tone evidence yet. Record the whole sentence again.",
        }

    def _syllable_gate_passed(syllable: dict) -> bool:
        # The sentence gate counts UNCERTAIN ("not clear enough to judge")
        # as a pass — it is a measurement gap, not evidence of a mistake.
        # Only INCORRECT (a likely tone mismatch) or INVALID_AUDIO (an
        # unusable recording) should cost the student the sentence pass.
        # `syllable["passed"]` collapses UNCERTAIN and INCORRECT into the
        # same False, so this reads the diagnostic verdict directly where
        # it's present; payloads without one (legacy) fall back to the raw
        # pass flag.
        status = syllable.get("diagnostic_status")
        if status in ("INCORRECT", "INVALID_AUDIO"):
            return False
        if status is not None:
            return True
        return syllable.get("passed") is True

    passed_count = sum(_syllable_gate_passed(syllable) for syllable in judged_syllables)
    pronunciation_failed_words = list(failed_words)
    # Sentence-level pass rate: 80% of judged syllables suffices. Below that
    # the whole recording fails; above, the recording passes but the failed
    # words still surface in `failed_words` / `practice_parts` so a student
    # can optionally drill them without being forced to re-record the
    # entire sentence to move on.
    #
    # Kept as a named constant so a calibration pass can move it in one
    # place; matches the pattern used by SYLLABLE_PASS_THRESHOLD and the
    # word-level shape/direction thresholds in tone_decision.
    pass_rate = passed_count / len(judged_syllables)
    # content_match is not False (not "is True"): a null/unverified result
    # (the independent ASR check errored, timed out, or ran without a
    # configured model) fails open rather than blocking the pass — a
    # verification hiccup should never cost the student their pronunciation
    # pass. Only an explicit mismatch (False) blocks it. See the matching
    # fix in storyRecorderFeedback.ts's isContentAccepted/
    # sceneContentGatePassed — this function had the same bug.
    passed = pass_rate >= SENTENCE_SYLLABLE_PASS_RATIO and content_match is not False
    if content_match is False:
        missing_text = "".join(missing_units)
        content_message = "Say the complete target sentence before this attempt can pass."
        if missing_text:
            content_message += f" Missing: {missing_text}."
    elif content_check_requested and content_match is None:
        content_message = "We couldn't verify what was said. Record the target again."
    else:
        content_message = ""
    return {
        "passed": passed,
        "status": "passed" if passed else "needs_practice",
        "passed_syllables": passed_count,
        "total_syllables": len(judged_syllables),
        "failed_words": pronunciation_failed_words,
        "practice_parts": list(dict.fromkeys([*pronunciation_failed_words, *missing_parts])),
        "content_match": content_match,
        "missing_target_units": missing_units,
        "message": _mastery_message(
            passed=passed,
            passed_count=passed_count,
            total=len(judged_syllables),
            failed_words=pronunciation_failed_words,
            missing_parts=missing_parts,
            content_message=content_message,
        ),
    }


def _mastery_message(
    *,
    passed: bool,
    passed_count: int,
    total: int,
    failed_words: list,
    missing_parts: list,
    content_message: str,
) -> str:
    """Sentence-level mastery message.

    The 80% sentence-pass rule means a recording can pass while still
    having failed words the student may want to drill. Say so explicitly —
    "you can continue, and here is what to practise if you want" — rather
    than the old strict "all measured tones passed" copy, which would read
    as false to a learner staring at ✗ chips beside their words."""
    if passed:
        if failed_words:
            return (
                f"Passed ({passed_count}/{total} syllables). "
                f"Practise {len(failed_words)} word(s) to sharpen your tones, "
                "or continue to the next scene."
            )
        return f"Passed ({passed_count}/{total} syllables). You can continue."
    if content_message:
        return content_message
    highlighted = len(failed_words) or len(missing_parts) or 1
    return (
        f"Practise {highlighted} highlighted part(s), then record the "
        "whole sentence again."
    )


VOWEL_ZONE_LABELS = {
    ("high", "front"): "High front vowel — mouth nearly closed, tongue forward (like 你 nǐ)",
    ("high", "back"): "High back vowel — mouth nearly closed, lips rounded (like 書 shū)",
    ("mid", "front"): "Mid front vowel — tongue mid-high, forward (like 姐 jiě)",
    ("mid", "central"): "Mid central vowel — tongue in centre (like 的 de)",
    ("mid", "back"): "Mid back vowel — tongue mid, lips rounded (like 我 wǒ)",
    ("low", "central"): "Open vowel — mouth wide open, jaw dropped (like 啊 ā / 媽 mā)",
}


def classify_vowel_quality(formants: dict) -> str:
    """Translate the utterance's median F1/F2 into a plain-language label.

    Delegates the actual F1/F2 → articulatory-zone decision to
    ``vowel_analysis.vowel_zone``, which is the same function the per-syllable
    vowel readout uses. Sharing it is the point: a sentence-level label that
    disagreed with the per-character readout sitting right below it would be a
    bug the student can see.

    Note this is the *whole recording's* median, so it describes an average
    mouth position across every vowel said — useful as one line of context for
    the AI feedback, and no substitute for the per-syllable readout.
    """
    from vowel_analysis import vowel_zone

    zone = vowel_zone(formants.get("F1", 0), formants.get("F2", 0))
    if not zone:
        return ""
    return VOWEL_ZONE_LABELS.get((zone["height"], zone["backness"]), "")


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
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
    verify_word: str = "",
    pinyin_hint: str = "",
    reference_word_curves: Optional[Dict[str, list]] = None,
    scene_target_text: str = "",
    on_stage: Optional[Callable[[dict], None]] = None,
    # Pre-pilot research-logging identity (all optional, all additive --
    # see `benchmarking/results/pilot_readiness.md`). Reuses the caller's
    # OWN existing identifiers (student id, (topic, scene) composite item
    # key); this function never derives or validates them, it only relays
    # them to the assistive-feedback layer.
    participant_id: str = "",
    item_id: str = "",
    session_id: str = "",
    attempt_id: str = "",
    attempt_number: int = 1,
    attempt_type: str = "WHOLE_SENTENCE_INITIAL",
    study_phase: str = "",
) -> AnalysisResponse:
    tmp_path = None
    trace_started_at = time.perf_counter()
    trace_entries: list[dict[str, Any]] = []

    def add_trace_stage(
        stage: str,
        status: str,
        started_at: float,
        *,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        detail: Optional[str] = None,
        reason_codes: Optional[list[str]] = None,
        input: Optional[Dict[str, Any]] = None,
        output: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry = {
            "stage": stage,
            "status": status,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
            "model": model,
            "provider": provider,
            "detail": detail,
            "reason_codes": reason_codes or [],
            "input": input,
            "output": output,
        }
        trace_entries.append(entry)
        if on_stage is not None:
            on_stage(entry)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        preflight_started_at = time.perf_counter()
        recording_preflight = assess_recording_quality(content)
        add_trace_stage(
            "preflight",
            recording_preflight.get("status", "review"),
            preflight_started_at,
            detail=recording_preflight.get("student_message") or recording_preflight.get("reason"),
            reason_codes=recording_preflight.get("reason_codes"),
            input={"audio_bytes": len(content)},
            output=recording_preflight,
        )
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
        asr_started_at = time.perf_counter()
        if (
            recording_preflight["status"] != "retry"
            and not transcription.strip()
            and chosen_provider in _audio_assessors
        ):
            api_key, module, fn_name, tag = _audio_assessors[chosen_provider]
            if api_key:
                try:
                    import importlib
                    mod = importlib.import_module(module)
                    audio_result = await getattr(mod, fn_name)(
                        content, scene_prompt, scene_vocabulary,
                        image_b64=image_b64, image_mime=image_mime,
                        scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
                        scene_attempt_number=scene_attempt_number,
                    )
                    transcription = convert_to_traditional_chinese(audio_result["transcription"])
                    transcription_model = tag
                    ai_feedback = audio_result["feedback"]
                    audio_assessed = True
                    add_trace_stage(
                        "asr",
                        "integrated",
                        asr_started_at,
                        model=transcription_model,
                        provider=chosen_provider,
                        detail="Transcript and language feedback came from the audio provider.",
                        input={"audio_provider": chosen_provider, "scene_vocabulary": scene_vocabulary},
                        output={"transcription": transcription, "model": transcription_model},
                    )
                except Exception as exc:
                    logger.warning(f"{chosen_provider} audio assessment failed, falling back: {exc}")

        if not transcription.strip() and asr_model.strip():
            try:
                transcription_result = await transcribe_audio_content(
                    content, asr_model.strip(), vocab_hint=scene_vocabulary
                )
                transcription = transcription_result.text
                transcription_model = transcription_result.model
                add_trace_stage(
                    "asr",
                    "passed" if transcription.strip() else "review",
                    asr_started_at,
                    model=transcription_model,
                    detail="Backend transcription completed." if transcription.strip() else "ASR returned no transcript.",
                    input={"asr_model": asr_model.strip(), "scene_vocabulary": scene_vocabulary},
                    output={"transcription": transcription, "model": transcription_model},
                )
            except Exception as exc:
                add_trace_stage(
                    "asr", "failed", asr_started_at, model=asr_model.strip(), detail=str(exc),
                    input={"asr_model": asr_model.strip(), "scene_vocabulary": scene_vocabulary},
                )
                raise
        elif not trace_entries or trace_entries[-1]["stage"] != "asr":
            add_trace_stage(
                "asr",
                "skipped",
                asr_started_at,
                model=transcription_model or None,
                detail="Transcript was supplied by the caller.",
                input={"note": "Transcript was supplied by the caller, not transcribed."},
                output={"transcription": transcription, "model": transcription_model or None},
            )

        sentence_target = scene_target_text.strip() or scene_suggested_answer.strip()
        sentence_content_verified = bool(asr_model.strip() or transcription_model.strip())
        scene_content_match = None
        if (
            sentence_target
            and not verify_word.strip()
            and transcription.strip()
            and sentence_content_verified
        ):
            scene_content_match = _scene_content_match(sentence_target, transcription)

        # Use the known scene sentence for acoustic scoring unless the ASR
        # content check came back with a confirmed mismatch. See
        # _acoustic_scoring_source's docstring for why an unverified (None)
        # result must not fall back to the raw ASR transcript the same way a
        # real mismatch does — that used to silently cut the measured
        # syllable count for a correctly-spoken attempt.
        scoring_source = _acoustic_scoring_source(sentence_target, scene_content_match)
        if scoring_source == "scene_target":
            scoring_transcription = sentence_target
            scoring_pinyin_hint = pinyin_hint.strip() or canonical_pinyin(sentence_target)
        else:
            scoring_transcription = transcription
            scoring_pinyin_hint = (
                pinyin_hint.strip()
                if pinyin_hint.strip() and not sentence_target
                else canonical_pinyin(transcription)
            )

        # Scene vocabulary phrases arrive "; "-joined (see StoryRecorder.tsx)
        # since a scene can teach more than one multi-word phrase (e.g.
        # "這個週末; 做什麼"); split back out for the phrase-context rescue.
        target_phrases = [p.strip() for p in scene_phrases.split(";") if p.strip()]

        def _run_praat(path: str, tx: str):
            return analyze_all(
                path, tx, pinyin_hint=scoring_pinyin_hint,
                reference_word_curves=reference_word_curves,
                target_phrases=target_phrases,
            )

        # Run Praat (CPU-bound, threadpool), AI feedback (I/O-bound), and the
        # optional word-content verification pass all in parallel so checking
        # "did they actually say this word" doesn't add extra latency on top
        # of the analysis that was already happening.
        feedback_coro = (
            asyncio.sleep(0)  # no-op placeholder when feedback already done
            if audio_assessed or recording_preflight["status"] == "retry"
            else generate_language_feedback(
                transcription, scene_prompt, scene_vocabulary, provider=ai_provider or None,
                image_b64=image_b64, image_mime=image_mime,
                scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
                scene_attempt_number=scene_attempt_number,
            )
        )
        verify_coro = (
            _verify_word_transcription(content, verify_word, vocab_hint=scene_vocabulary)
            if verify_word.strip()
            else asyncio.sleep(0, result=(None, None))
        )
        praat_input = {
            "pinyin_hint": scoring_pinyin_hint or None,
            "scoring_text": scoring_transcription,
            "scoring_source": scoring_source,
            "reference_word_curves_provided": bool(reference_word_curves),
            "target_phrases": target_phrases or None,
        }

        async def run_praat_stage():
            started_at = time.perf_counter()
            try:
                result = await run_in_threadpool(_run_praat, tmp_path, scoring_transcription)
            except Exception as exc:
                add_trace_stage("praat", "failed", started_at, detail=str(exc), input=praat_input)
                raise
            (r_pitch_contour, r_formants, r_speech_rate, r_fluency_score, r_pitch_stats,
             r_word_prosody, r_detected_tone, r_tone_accuracy, _r_feedback,
             r_pause_analysis) = result
            add_trace_stage(
                "praat", "passed", started_at, detail="Acoustic analysis completed.",
                input=praat_input,
                output={
                    "pitch_contour": r_pitch_contour,
                    "formants": r_formants,
                    "speech_rate": r_speech_rate,
                    "fluency_score": r_fluency_score,
                    "pitch_statistics": r_pitch_stats,
                    "word_prosody": r_word_prosody,
                    "detected_tone": r_detected_tone,
                    "tone_accuracy": r_tone_accuracy,
                    "pause_analysis": r_pause_analysis,
                },
            )
            return result

        feedback_input = {
            "scene_prompt": scene_prompt or None,
            "scene_vocabulary": scene_vocabulary or None,
            "scene_phrases": scene_phrases or None,
            "scene_suggested_answer": scene_suggested_answer or None,
            "scene_attempt_number": scene_attempt_number,
            "image_provided": bool(image_b64),
        }

        async def run_feedback_stage():
            started_at = time.perf_counter()
            result = await feedback_coro
            output = result if isinstance(result, dict) else (ai_feedback if isinstance(ai_feedback, dict) else None)
            add_trace_stage(
                "feedback",
                "skipped" if audio_assessed or recording_preflight["status"] == "retry" else "passed",
                started_at,
                provider=(result.get("provider") if isinstance(result, dict) else None)
                or ai_provider
                or "backend-default",
                detail="Provider feedback completed." if not audio_assessed else "Audio provider feedback already included.",
                input=feedback_input,
                output=output,
            )
            return result

        async def run_verify_stage():
            started_at = time.perf_counter()
            result = await verify_coro
            if verify_word.strip():
                add_trace_stage(
                    "content_verification", "passed", started_at,
                    detail="Independent word verification completed.",
                    input={"verify_word": verify_word},
                    output={"recognized_text": result[0], "content_match": result[1]},
                )
            return result

        (praat_result, maybe_feedback, (recognized_text, content_match)) = await asyncio.gather(
            run_praat_stage(),
            run_feedback_stage(),
            run_verify_stage(),
        )
        if not audio_assessed:
            ai_feedback = maybe_feedback
        if sentence_target and not verify_word.strip():
            content_match = scene_content_match
            recognized_text = (transcription or None) if sentence_content_verified else None
            verification_started_at = time.perf_counter()
            add_trace_stage(
                "content_verification",
                "passed" if content_match is True else "review",
                verification_started_at,
                detail="Independent sentence ASR was compared with the scene target.",
                input={"target_text": sentence_target},
                output={
                    "recognized_text": recognized_text,
                    "content_match": content_match,
                    "asr_model": transcription_model or asr_model or None,
                },
            )
        content_target = verify_word.strip() or sentence_target
        recognized_for_diff = (
            recognized_text
            if verify_word.strip()
            else (transcription if sentence_content_verified else "")
        )
        content_diff = _scene_content_diff(content_target, recognized_for_diff or "")
        (pitch_contour, formants, speech_rate, fluency_score, pitch_stats,
         word_prosody, detected_tone, tone_accuracy, feedback,
         pause_analysis) = praat_result

        # No speech → noise from the mic can spuriously match a tone reference
        quality_started_at = time.perf_counter()
        feedback_quality = finalize_feedback_quality(
            recording_preflight,
            pitch_contour,
            transcription,
            content_match=content_match,
            content_was_verified=bool(verify_word.strip()) or sentence_content_verified,
        )
        add_trace_stage(
            "quality_gate",
            "passed" if feedback_quality["can_score_pronunciation"] else "retry",
            quality_started_at,
            detail=feedback_quality.get("student_message") or "Quality gate evaluated.",
            reason_codes=feedback_quality.get("reason_codes"),
            input={
                "preflight_status": recording_preflight.get("status"),
                "content_was_verified": bool(verify_word.strip()) or sentence_content_verified,
            },
            output=feedback_quality,
        )

        if not feedback_quality["can_score_pronunciation"]:
            tone_accuracy = 0
            detected_tone = 0
            fluency_score = 0.0
            feedback = feedback_quality["student_message"]
            for word in word_prosody:
                word["judged"] = False
                word["tone_accuracy"] = 0.0
                word["shape_accuracy"] = 0.0
                word["passed"] = None
                word["feedback"] = feedback_quality["student_message"]
                for syllable in word.get("syllables") or []:
                    syllable["score"] = 0.0
                    syllable["passed"] = None

        vowel_quality = classify_vowel_quality(formants)
        tone_direction = build_tone_direction(pitch_contour, detected_tone, tone_accuracy)

        # Turn the raw pause/rate measurements into judged, story-aggregatable
        # signals: how many pauses landed at a natural clause/punctuation
        # boundary in the reference script vs. mid-phrase ("choppy"), and the
        # articulation rate (syllables/sec, pauses excluded) for speed
        # feedback. Merged into pause_analysis so the frontend can pick these
        # up the same way it already reads pause_count/longest_pause.
        character_count = sum(1 for ch in scoring_transcription if "一" <= ch <= "鿿")
        fluency_for_response = caf_metrics.fluency_metrics(
            speech_rate, pause_analysis, character_count
        )
        # The teacher's listen script is the authoritative phrase-break source;
        # fall back to the suggested answer only for older scenes that have no
        # dedicated listen script.
        pause_reference_text = (
            scene_target_text.strip()
            or scene_suggested_answer.strip()
            or transcription
        )
        pause_judgment = caf_metrics.classify_pauses(
            pause_reference_text, pause_analysis, word_prosody
        )
        pause_analysis = {
            **pause_analysis,
            "articulation_rate": fluency_for_response["articulation_rate"],
            "choppy_pause_count": len(pause_judgment["choppy"]) if pause_judgment["judged"] else 0,
            "natural_pause_count": len(pause_judgment["natural"]) if pause_judgment["judged"] else 0,
        }

        # The parallel feedback call ran before Praat finished. Recompute the
        # local CAF feedback now that we have the acoustic numbers: when the
        # provider is local, swap in the full grounded result; for an external
        # provider, only patch its pronunciation_note with the real Praat data.
        from ai_feedback import (
            apply_feedback_quality_gate as _apply_feedback_quality_gate,
            fallback_language_feedback as _local_fb,
        )
        local_fb = _local_fb(
            transcription, scene_prompt, scene_vocabulary,
            praat_tone_accuracy=float(tone_accuracy),
            praat_fluency_score=float(fluency_score),
            praat_vowel_quality=vowel_quality or "",
            praat_pause_analysis=pause_analysis,
            praat_speech_rate=float(speech_rate),
            word_prosody=word_prosody,
            image_b64=image_b64,
            scene_phrases=scene_phrases,
            scene_suggested_answer=scene_suggested_answer,
            scene_attempt_number=scene_attempt_number,
        )
        if isinstance(ai_feedback, dict):
            if ai_feedback.get("provider") == "local":
                ai_feedback = local_fb
            else:
                ai_feedback["pronunciation_note"] = local_fb["pronunciation_note"]
        else:
            ai_feedback = local_fb
        ai_feedback = _apply_feedback_quality_gate(
            ai_feedback,
            feedback_quality,
            transcription=transcription,
            scene_vocabulary=scene_vocabulary,
        )
        description = build_analysis_description(scoring_transcription, transcription_model, word_prosody)

        # Recording-level QC is a gate on the *diagnostic* layer: when the
        # recording itself cannot support a judgement, no per-syllable verdict
        # may stand, however the contour happened to score. This deliberately
        # does not touch word_prosody[].passed — progression keeps running on
        # the legacy path exactly as before this patch.
        tone_diagnostics = apply_recording_qc_to_diagnostics(
            word_prosody, feedback_quality
        )
        pronunciation_mastery = build_pronunciation_mastery(
            word_prosody,
            feedback_quality,
            content_match=content_match,
            content_check_requested=bool(content_target),
            missing_target_units=(
                _missing_scene_content_units(content_target, recognized_for_diff or "")
                if content_match is False
                else []
            ),
        )

        # Additive assistive-feedback layer (Candidate F1 + Candidate E2,
        # frozen). Isolated behind its own try/except and its own env-var
        # gate (default off) for the same reason `_contextual_tone_plan` is:
        # a failure here must degrade to `None`, never break the response
        # or touch word_prosody[].passed.
        try:
            from assistive_feedback.pipeline import RequestIdentity, compute_assistive_feedback

            assistive_feedback_result = compute_assistive_feedback(
                pitch_contour, scoring_transcription, scoring_pinyin_hint, tmp_path,
                identity=RequestIdentity(
                    participant_id=participant_id, item_id=item_id, session_id=session_id,
                    attempt_id=attempt_id, attempt_number=attempt_number,
                    attempt_type=attempt_type, study_phase=study_phase,
                ) if participant_id else None,
            )
        except Exception:  # pragma: no cover - defensive, diagnostics are optional
            assistive_feedback_result = None

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
            recognized_text=recognized_text,
            content_match=content_match,
            content_diff=content_diff,
            feedback_quality=feedback_quality,
            tone_diagnostics=tone_diagnostics,
            pronunciation_mastery=pronunciation_mastery,
            assistive_feedback=assistive_feedback_result,
            processing_trace=ProcessingTrace(
                stages=[ProcessingTraceStage(**entry) for entry in trace_entries],
                total_duration_ms=round((time.perf_counter() - trace_started_at) * 1000, 1),
            ),
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


_MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(10 * 1024 * 1024)))  # 10 MB

# Silence gate: audio with less energy/voiced speech than this never reaches
# an ASR model at all. Whisper-family models hallucinate on silence — worst
# of all by echoing the vocab-hint prompt back as the "transcript", which
# scores a student who said nothing as if they'd said the target words.
# Thresholds match the earlier prod-hardening tuning: 0.005 RMS let fan/room
# hum through, 0.02 doesn't; 0.4s of voiced audio rejects pops and hum that
# still pass RMS.
ASR_SILENCE_RMS = float(os.getenv("ASR_SILENCE_RMS", "0.02"))
ASR_MIN_SPEECH_SECONDS = float(os.getenv("ASR_MIN_SPEECH_SECONDS", "0.4"))
FEEDBACK_MIN_DURATION_SECONDS = float(os.getenv("FEEDBACK_MIN_DURATION_SECONDS", "0.45"))
FEEDBACK_MAX_CLIPPING_RATIO = float(os.getenv("FEEDBACK_MAX_CLIPPING_RATIO", "0.08"))
FEEDBACK_MIN_PITCH_POINTS = int(os.getenv("FEEDBACK_MIN_PITCH_POINTS", "8"))


def _decode_wav_mono(audio_content: bytes) -> Tuple[np.ndarray, int]:
    """Decode PCM WAV bytes to mono float32 in [-1, 1] using only the stdlib
    — librosa/soundfile are optional deps that may not exist on the deployed
    backend, and every in-app recording path already produces WAV."""
    import wave

    with wave.open(io.BytesIO(audio_content)) as wav_file:
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        raw = wav_file.readframes(wav_file.getnframes())

    dtype = {1: np.int8, 2: np.int16, 4: np.int32}.get(sample_width)
    if dtype is None:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")
    data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    data /= float(2 ** (8 * sample_width - 1))
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sample_rate


def assess_recording_quality(audio_content: bytes) -> Dict[str, Any]:
    """Measure whether a recording contains enough evidence for feedback.

    This is deliberately deterministic and provider-independent.  It runs
    before cloud AI so silence/noise cannot be turned into a confident
    transcript by a generative model.  Decode failures require ``review`` rather
    than rejected because non-WAV uploads may still be valid audio that the
    provider can decode.
    """
    try:
        data, sample_rate = _decode_wav_mono(audio_content)
    except Exception as exc:
        logger.info("Recording-quality preflight could not decode WAV: %s", exc)
        return {
            "status": "review",
            "confidence": 0.25,
            "can_score_pronunciation": False,
            "can_score_content": False,
            "reason_codes": ["audio_format_unverified"],
            "student_message": (
                "We could not verify this recording's sound quality. Please record again "
                "as WAV before using the result for practice decisions."
            ),
            "metrics": {},
        }

    duration = len(data) / sample_rate if sample_rate > 0 else 0.0
    rms = float(np.sqrt(np.mean(data**2))) if len(data) else 0.0
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    clipping_ratio = float(np.mean(np.abs(data) >= 0.99)) if len(data) else 0.0

    frame = max(1, int(sample_rate * 0.025))
    hop = max(1, int(sample_rate * 0.010))
    voiced_seconds = 0.0
    voiced_ratio = 0.0
    energy_variation = 0.0
    if len(data) >= frame and peak > 0:
        windows = np.lib.stride_tricks.sliding_window_view(data, frame)[::hop]
        frame_rms = np.sqrt(np.mean(windows**2, axis=1))
        frame_peak = float(frame_rms.max()) if len(frame_rms) else 0.0
        if frame_peak > 0:
            mean_frame_rms = float(np.mean(frame_rms))
            if mean_frame_rms > 0:
                energy_variation = float(np.std(frame_rms) / mean_frame_rms)
            # Require both an absolute speech floor and proximity to the
            # recording's loudest frame.  The absolute floor stops steady
            # room hum from declaring its entire duration "voiced".
            voiced = (
                (frame_rms >= ASR_SILENCE_RMS * 0.5)
                & (frame_rms > frame_peak * 10 ** (-30 / 20))
            )
            voiced_seconds = float(np.sum(voiced)) * hop / sample_rate
            voiced_ratio = min(1.0, voiced_seconds / max(duration, 0.001))

    metrics = {
        "duration_seconds": round(duration, 3),
        "rms": round(rms, 5),
        "peak": round(peak, 5),
        "clipping_ratio": round(clipping_ratio, 5),
        "voiced_seconds": round(voiced_seconds, 3),
        "voiced_ratio": round(voiced_ratio, 3),
        "energy_variation": round(energy_variation, 3),
        "pitch_points": 0,
    }
    reasons: List[str] = []
    if duration < FEEDBACK_MIN_DURATION_SECONDS:
        reasons.append("recording_too_short")
    if rms < ASR_SILENCE_RMS:
        reasons.append("signal_too_quiet")
    if voiced_seconds < ASR_MIN_SPEECH_SECONDS:
        reasons.append("insufficient_speech")
    if clipping_ratio > FEEDBACK_MAX_CLIPPING_RATIO:
        reasons.append("audio_clipping")

    if reasons:
        return {
            "status": "retry",
            "confidence": 0.0,
            "can_score_pronunciation": False,
            "can_score_content": False,
            "reason_codes": reasons,
            "student_message": (
                "This recording is not clear enough to score safely. Move closer to the "
                "microphone, speak one complete phrase, and record again."
            ),
            "metrics": metrics,
        }

    # Preflight proves that audible signal exists, not yet that Praat found
    # enough voiced pitch or that ASR recognized the intended content.
    signal_confidence = min(
        0.8,
        0.35
        + min(0.25, voiced_seconds / max(ASR_MIN_SPEECH_SECONDS, 0.01) * 0.1)
        + min(0.2, voiced_ratio * 0.25),
    )
    review_reasons = ["awaiting_acoustic_analysis"]
    # A nearly constant, fully voiced signal is often a calibration tone,
    # electrical hum, or held vowel rather than a complete practice attempt.
    # Do not reject it as silence, but never let it become mastery evidence.
    if voiced_ratio >= 0.85 and energy_variation < 0.03:
        review_reasons.append("low_signal_variation")

    return {
        "status": "review",
        "confidence": round(signal_confidence, 2),
        "can_score_pronunciation": False,
        "can_score_content": False,
        "reason_codes": review_reasons,
        "student_message": "The recording passed the sound check; analyzing speech evidence now.",
        "metrics": metrics,
    }


def finalize_feedback_quality(
    preflight: Dict[str, Any],
    pitch_contour: List[Tuple[float, float]],
    transcription: str,
    *,
    content_match: Optional[bool] = None,
    content_was_verified: bool = False,
) -> Dict[str, Any]:
    """Combine signal, pitch and transcript evidence into the API quality gate."""
    quality = {
        **preflight,
        "metrics": dict(preflight.get("metrics") or {}),
        "reason_codes": list(preflight.get("reason_codes") or []),
    }
    quality["metrics"]["pitch_points"] = len(pitch_contour)

    if quality.get("status") == "retry":
        return quality

    reasons = [r for r in quality["reason_codes"] if r != "awaiting_acoustic_analysis"]
    pitch_ok = len(pitch_contour) >= FEEDBACK_MIN_PITCH_POINTS
    transcript_ok = bool(transcription.strip())
    if not pitch_ok:
        reasons.append("insufficient_voiced_pitch")
    if not transcript_ok:
        reasons.append("transcription_unavailable")
    if content_match is False:
        reasons.append("target_content_mismatch")

    # A content mismatch must block the content pass, but it should not erase
    # useful acoustic feedback for the words that were actually spoken. An
    # unknown verification result still blocks pronunciation scoring because
    # there is no safe target-to-audio mapping yet.
    target_available_for_pronunciation = (
        not content_was_verified or content_match is not None
    )
    if content_was_verified and content_match is None:
        reasons.append("target_content_unverified")
    can_score_pronunciation = (
        pitch_ok and transcript_ok and target_available_for_pronunciation
    )
    can_score_content = (
        transcript_ok
        and content_was_verified
        and content_match is True
    )
    if transcript_ok and not content_was_verified:
        reasons.append("content_not_independently_verified")
    signal_review_required = any(
        reason in {"audio_format_unverified", "low_signal_variation"}
        for reason in reasons
    )
    if signal_review_required:
        can_score_content = False

    if not can_score_pronunciation:
        status = "retry" if not pitch_ok or not transcript_ok else "review"
        confidence = 0.0 if status == "retry" else 0.4
        message = (
            "We could not collect enough clear speech and pitch evidence to score this "
            "attempt safely. Please record it once more."
        )
    else:
        status = (
            "reliable"
            if can_score_content and not signal_review_required
            else "review"
        )
        pitch_confidence = min(1.0, len(pitch_contour) / max(FEEDBACK_MIN_PITCH_POINTS * 4, 1))
        confidence = round(min(0.95, 0.55 + pitch_confidence * 0.4), 2)
        message = (
            "This recording has enough evidence for pronunciation feedback."
            if status == "reliable"
            else "Pronunciation can be scored, but the spoken content could not be confirmed."
        )

    return {
        **quality,
        "status": status,
        "confidence": confidence,
        "can_score_pronunciation": can_score_pronunciation,
        "can_score_content": can_score_content,
        "reason_codes": reasons,
        "student_message": message,
    }


def _has_speech(audio_content: bytes) -> bool:
    """Two-stage speech check: overall RMS (rejects near-silence), then a
    frame-level voiced-duration estimate (rejects brief pops / steady hum
    that pass RMS). Fails open — any decode problem (non-WAV upload, odd
    encoding) assumes speech, so the gate can only ever *prevent* a
    hallucination, never block a real recording."""
    quality = assess_recording_quality(audio_content)
    # Keep the legacy fail-open behavior for formats this WAV-only preflight
    # cannot decode.  Other failures are explicit evidence that ASR should
    # not be allowed to hallucinate a transcript.
    return quality["status"] != "retry"


# Stock phrases Whisper-family models emit for silence/noise — video-outro
# boilerplate from the training data, never something an A1-A2 student
# recording a story scene actually said. Entries are pre-normalized the
# same way _filter_asr_phantoms normalizes its input: lowercased, spaces
# and trailing punctuation removed.
_ASR_PHANTOM_PHRASES = {
    "謝謝", "謝謝觀看", "謝謝收看", "謝謝收聽", "感謝收聽", "感謝觀看",
    "謝謝大家", "請訂閱", "字幕由amara.org社群提供",
    "thankyou", "thankyouforwatching", "thankyouforlistening", "you",
}


def _filter_asr_phantoms(text: str) -> str:
    normalized = text.strip().strip("。.!！?？,， ").replace(" ", "").lower()
    if normalized in _ASR_PHANTOM_PHRASES:
        logger.info("ASR phantom phrase filtered: %r", text)
        return ""
    return text


async def transcribe_audio_content(
    audio_content: bytes,
    model: str,
    vocab_hint: str = "",
) -> TranscriptionResponse:
    # Gate before dispatching to ANY provider — cloud Whisper hallucinates
    # on silence exactly like the local model, and with a vocab-hint prompt
    # attached it echoes the hint itself back as the transcript.
    if not _has_speech(audio_content):
        logger.info("Silence gate: no speech detected, skipping ASR (model=%s)", model)
        return TranscriptionResponse(text="", model="silence-gate")

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



def _normalized_scene_content_units(value: str) -> list[str]:
    """Return comparable sentence units while ignoring script/punctuation noise."""
    normalized = convert_to_traditional_chinese(value or "")
    return [char for char in normalized if char.isalnum()]


def _content_unit_key(unit: str) -> str:
    """Return a tone-insensitive key for one ASR-comparable character."""
    if not unit:
        return ""
    if unit.isascii():
        return unit.casefold()
    try:
        reading = canonical_pinyin_tone3(unit).strip().split()
        if reading:
            syllable = reading[0]
            return syllable[:-1] if syllable[-1:] in "12345" else syllable
    except Exception:
        pass
    return unit


def _content_units_equivalent(target: str, recognized: str) -> bool:
    return bool(target) and _content_unit_key(target) == _content_unit_key(recognized)


def _missing_scene_content_units(target: str, recognized: str) -> list[str]:
    """List target units in missing/replaced alignment spans, in target order."""
    return [
        segment["target"]
        for segment in _align_scene_content(target, recognized)
        if segment["type"] in {"missing", "replace"} and segment["target"]
    ]


def _align_scene_content(target: str, recognized: str) -> list[dict[str, str]]:
    """Align target and ASR units while treating pinyin homophones as matches."""
    target_units = _normalized_scene_content_units(target)
    recognized_units = _normalized_scene_content_units(recognized)
    rows = len(target_units)
    cols = len(recognized_units)
    if not target_units or not recognized_units:
        return []

    costs = [[0] * (cols + 1) for _ in range(rows + 1)]
    for row in range(1, rows + 1):
        costs[row][0] = row
    for col in range(1, cols + 1):
        costs[0][col] = col
    for row in range(1, rows + 1):
        for col in range(1, cols + 1):
            diagonal = costs[row - 1][col - 1] + (
                0 if _content_units_equivalent(target_units[row - 1], recognized_units[col - 1]) else 1
            )
            costs[row][col] = min(diagonal, costs[row - 1][col] + 1, costs[row][col - 1] + 1)

    operations: list[dict[str, str]] = []
    row, col = rows, cols
    while row or col:
        if row and col:
            equivalent = _content_units_equivalent(target_units[row - 1], recognized_units[col - 1])
            diagonal = costs[row - 1][col - 1] + (0 if equivalent else 1)
            if costs[row][col] == diagonal:
                operations.append({
                    "type": "match" if equivalent else "replace",
                    "target": target_units[row - 1],
                    "heard": recognized_units[col - 1],
                })
                row -= 1
                col -= 1
                continue
        if row and costs[row][col] == costs[row - 1][col] + 1:
            operations.append({"type": "missing", "target": target_units[row - 1], "heard": ""})
            row -= 1
            continue
        operations.append({"type": "extra", "target": "", "heard": recognized_units[col - 1]})
        col -= 1

    operations.reverse()
    grouped: list[dict[str, str]] = []
    for operation in operations:
        if grouped and grouped[-1]["type"] == operation["type"]:
            grouped[-1]["target"] += operation["target"]
            grouped[-1]["heard"] += operation["heard"]
        else:
            grouped.append(dict(operation))
    return grouped


def _scene_content_diff(target: str, recognized: str) -> list[dict[str, str]]:
    """Return display-ready contiguous spans, or no fake diff for empty ASR."""
    if not _normalized_scene_content_units(target) or not _normalized_scene_content_units(recognized):
        return []
    return _align_scene_content(target, recognized)


def _scene_content_match(target: str, recognized: str) -> Optional[bool]:
    """Verify a sentence while tolerating homophone ASR substitutions.

    Matching is positional and length-preserving. This prevents an omitted
    name or phrase from passing merely because most of the remaining sentence
    overlaps, while still allowing substitutions such as 友/遊 and 妳/你.
    """
    target_units = _normalized_scene_content_units(target)
    recognized_units = _normalized_scene_content_units(recognized)
    if not target_units or not recognized_units:
        return None

    return all(segment["type"] == "match" for segment in _align_scene_content(target, recognized))


def _acoustic_scoring_source(
    sentence_target: str, scene_content_match: Optional[bool]
) -> str:
    """Which transcript to run pitch/tone scoring against for this sentence.

    ``scene_content_match is False`` is real negative evidence (the ASR
    content check actually disagreed with the target) — scoring against the
    known-correct sentence in that case would fabricate a score for words the
    learner may not have said, so the raw ASR transcript is used instead.
    ``None`` is not that: it means the check never ran or couldn't confirm
    anything (verify_word drill in progress, empty transcript, ASR/model
    hiccup) — an unrelated verification gap, not evidence the learner got it
    wrong. Falling back to the ASR transcript in that case silently truncates
    scoring to whatever (possibly partial or mis-heard) text the ASR
    produced, which can measure far fewer syllables than the sentence
    actually has. Only a confirmed mismatch should give up the known-correct
    target; an unverified result fails open, same as the content_match gates
    in storyRecorderFeedback.ts and build_pronunciation_mastery.
    """
    if sentence_target and scene_content_match is not False:
        return "scene_target"
    return "asr_transcript"


async def _verify_word_transcription(
    audio_content: bytes, word: str, vocab_hint: str = ""
) -> Tuple[Optional[str], Optional[bool]]:
    """Runs an independent ASR pass to check whether `word` was actually spoken.

    Word-practice callers pass the target word as the `transcription` so Praat
    scores tone against a known reference instead of a possibly-wrong ASR guess.
    That means tone scoring never actually confirms the student said the right
    word. This runs ASR for real, on the side, purely to catch that mismatch.
    Fails open (None, None) on ASR error so a transcription hiccup never blocks
    the pitch/tone feedback the student came for.

    `word` may be a single vocabulary word/character or, for phrase-practice
    callers, an entire multi-character phrase — requiring the whole string to
    appear verbatim was fine for short targets but made phrase verification
    fail outright whenever the independent ASR pass misheard a single
    syllable anywhere in a longer phrase (common, not rare). Longer targets
    use the same tolerant character-overlap ratio the frontend already
    applies for its own pass/fail verdict, so the two no longer disagree.

    Prefers Groq (fast, cloud) over the "auto" chain's default of the local
    ctwhisper model, which is CPU-heavy and — running alongside the Praat
    analysis on every single word attempt — made word practice noticeably
    slower once this check was added.
    """
    model = "groq" if GROQ_API_KEY else "auto"
    try:
        result = await transcribe_audio_content(audio_content, model, vocab_hint=vocab_hint or word)
        recognized = convert_to_traditional_chinese(result.text).strip()
        if not recognized:
            # ASR heard nothing — on a 1-2s single-syllable drill clip
            # that's an ASR limitation, not evidence the wrong word was
            # spoken. Unverifiable (None), the same fail-open contract as
            # an ASR error; a hard False here silently blocked passing
            # drills from ever clearing their mastery chip.
            return recognized, None
        return recognized, _scene_content_match(word, recognized)
    except Exception as exc:
        logger.warning("Word content verification failed: %s", exc)
        return None, None


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

    # Every provider ran but heard nothing — that's silence or unclear
    # speech, not a server failure. Return empty so Praat still analyzes
    # the audio and the student gets an honest "no speech detected" rather
    # than a 503 error page.
    if errors and all(e.endswith(": empty transcription") for e in errors):
        logger.info("Auto ASR: every provider returned empty — silent or unclear audio")
        return TranscriptionResponse(text="", model="auto:silent")

    detail = (
        "No ASR provider produced a transcript. Tried: " + "; ".join(errors)
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


VOCAB_POS_CODES = ["N", "V", "Adj", "Adv", "MW", "Particle", "Phrase", "Other"]


def _vocab_from_sentence_prompt(sentence: str) -> str:
    return f"""
You are helping a Taiwan Mandarin (國語/臺灣華語) teacher build a vocabulary table
for one sentence from a students' story.

Sentence:
{sentence}

Segment this sentence into its key vocabulary words (skip purely grammatical
particles that aren't useful vocabulary to study, but include meaningful
multi-character words as single words rather than splitting them into
individual characters). Return only valid JSON shaped exactly like:
[
  {{"word": "餐廳", "pinyin": "cāntīng", "pos": "N", "translation": "restaurant"}}
]

Rules:
- Every "word" must be an exact substring of the sentence, in Traditional Chinese.
- Do not repeat the same word twice.
- "pinyin" must use Taiwan Mandarin (國語) tone-marked pronunciation, e.g. "cāntīng".
- "pos" must be exactly one of: {", ".join(VOCAB_POS_CODES)}.
- "translation" is a short English translation (a few words at most).
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_words(data: object, sentence: str) -> List[VocabWordSuggestion]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of words")

    seen: set[str] = set()
    words: List[VocabWordSuggestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if not word or word in seen or word not in sentence:
            continue
        seen.add(word)
        pos = str(item.get("pos", "")).strip()
        words.append(
            VocabWordSuggestion(
                word=word,
                pinyin=str(item.get("pinyin", "")).strip(),
                pos=pos if pos in VOCAB_POS_CODES else "",
                translation=str(item.get("translation", "")).strip(),
            )
        )
    return words


async def extract_vocab_from_sentence_with_groq(sentence: str) -> List[VocabWordSuggestion]:
    # Groq's JSON mode (like OpenAI's) only guarantees a top-level JSON
    # *object*, not a bare array, so the model is asked to wrap the array in
    # {"words": [...]}. This sidesteps the markdown-fence/stray-prose
    # failure mode entirely, unlike the Gemini path below.
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Taiwan Mandarin vocabulary-extraction assistant. "
                    "Always respond in valid JSON only — no markdown fences, no prose "
                    'outside the JSON. Wrap the array in a top-level object: {"words": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_from_sentence_prompt(sentence)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("words") if isinstance(parsed, dict) else parsed
    return _parse_vocab_words(data, sentence)


async def extract_vocab_from_sentence_with_gemini(sentence: str) -> List[VocabWordSuggestion]:
    payload = {"contents": [{"parts": [{"text": _vocab_from_sentence_prompt(sentence)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_words(data, sentence)


def _phrases_from_sentence_prompt(sentence: str, count: int) -> str:
    return f"""
You are helping a Taiwan Mandarin (國語/臺灣華語) teacher build a "handy phrases"
table for one sentence from a students' story — reusable multi-word
expressions or sentence patterns (not single vocabulary words, not the
whole sentence itself) that a student could reuse in other sentences.

Sentence:
{sentence}

Pick up to {count} of the most reusable phrase-level chunks from this
sentence. Return only valid JSON shaped exactly like:
[
  {{"phrase": "想要", "translation": "want to"}}
]

Rules:
- Every "phrase" must be an exact substring of the sentence, in Traditional
  Chinese, and at least two characters long.
- Do not repeat the same phrase twice.
- "translation" is a short English translation (a few words at most).
- Return the JSON array only, no surrounding text.
"""


def _parse_phrases(data: object, sentence: str) -> List[PhraseSuggestion]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of phrases")

    seen: set[str] = set()
    phrases: List[PhraseSuggestion] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase", "")).strip()
        if not phrase or phrase in seen or phrase not in sentence:
            continue
        seen.add(phrase)
        phrases.append(
            PhraseSuggestion(
                phrase=phrase,
                translation=str(item.get("translation", "")).strip(),
            )
        )
    return phrases


async def extract_phrases_from_sentence_with_groq(
    sentence: str, count: int
) -> List[PhraseSuggestion]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Taiwan Mandarin phrase-extraction assistant. "
                    "Always respond in valid JSON only — no markdown fences, no prose "
                    'outside the JSON. Wrap the array in a top-level object: {"phrases": [...]}.'
                ),
            },
            {"role": "user", "content": _phrases_from_sentence_prompt(sentence, count)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("phrases") if isinstance(parsed, dict) else parsed
    return _parse_phrases(data, sentence)


async def extract_phrases_from_sentence_with_gemini(
    sentence: str, count: int
) -> List[PhraseSuggestion]:
    payload = {"contents": [{"parts": [{"text": _phrases_from_sentence_prompt(sentence, count)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_phrases(data, sentence)


def _vocab_distractors_prompt(words: List[VocabDistractorWord]) -> str:
    word_lines = "\n".join(
        f'{i + 1}. "{w.word}" -> "{w.translation}"'
        + (f' (used in: "{w.context}")' if w.context else "")
        + (f" (already used, do not repeat: {', '.join(w.avoid)})" if w.avoid else "")
        for i, w in enumerate(words)
    )
    return f"""
You are building multiple-choice distractors for a Mandarin vocabulary quiz.
For each word below, its correct English translation is already given.
Generate 3 WRONG but PLAUSIBLE English translations for each word — answers a
real student might mistakenly pick because they're close in meaning, the same
part of speech, or a common confusion (not random unrelated words).

Words:
{word_lines}

Return only valid JSON shaped exactly like:
[
  {{"word": "餐廳", "distractors": ["kitchen", "hotel", "cafeteria"]}}
]

Rules:
- "word" must exactly match one of the words given above.
- Each distractor must be different from that word's correct translation and
  from the other distractors for that word.
- A distractor must NOT be another acceptable translation of the word — the
  given correct translation must stay the ONLY correct option. If a
  candidate distractor could also be defended as a correct answer, replace
  it with a clearly wrong one.
- Distractors are short English translations (a few words at most), matching
  the style of the correct translation.
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_distractors(
    data: object, words: List[VocabDistractorWord]
) -> List[VocabDistractorResult]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of distractors")

    by_word = {w.word: w for w in words}
    results: List[VocabDistractorResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        source = by_word.get(word)
        if not source:
            continue
        correct = source.translation.strip().lower()
        seen = {correct}
        distractors: List[str] = []
        for raw in item.get("distractors", []):
            distractor = str(raw).strip()
            key = distractor.lower()
            if not distractor or key in seen:
                continue
            seen.add(key)
            distractors.append(distractor)
        if distractors:
            results.append(VocabDistractorResult(word=word, distractors=distractors[:3]))
    return results


async def generate_vocab_distractors_with_groq(
    words: List[VocabDistractorWord],
) -> List[VocabDistractorResult]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin vocabulary-quiz assistant. Always respond in "
                    "valid JSON only — no markdown fences, no prose outside the JSON. "
                    'Wrap the array in a top-level object: {"results": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_distractors_prompt(words)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("results") if isinstance(parsed, dict) else parsed
    return _parse_vocab_distractors(data, words)


async def generate_vocab_distractors_with_gemini(
    words: List[VocabDistractorWord],
) -> List[VocabDistractorResult]:
    payload = {"contents": [{"parts": [{"text": _vocab_distractors_prompt(words)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_distractors(data, words)


def _vocab_cloze_prompt(words: List[VocabClozeWord]) -> str:
    word_lines = "\n".join(
        f'{i + 1}. "{w.word}" -> "{w.translation}"'
        + (f' (style/level reference: "{w.context}")' if w.context else "")
        + (f" (already used, write a different sentence: {' / '.join(w.avoid)})" if w.avoid else "")
        for i, w in enumerate(words)
    )
    return f"""
You are building fill-in-the-blank (cloze) questions for an A1-A2 Mandarin
vocabulary quiz. For each word below, write ONE short, natural Traditional
Chinese sentence that uses that word — simple enough for a beginner, and
matching the style/vocabulary level of the reference sentence when one is
given. Also give 3 WRONG but PLAUSIBLE Chinese words that could grammatically
fill the same blank in that sentence (same part of speech, a real point of
confusion for a learner) — not random unrelated words.

Words:
{word_lines}

Return only valid JSON shaped exactly like:
[
  {{"word": "餐廳", "sentence": "我們今天要去餐廳吃飯。", "distractors": ["教室", "公園", "醫院"]}}
]

Rules:
- "word" must exactly match one of the words given above.
- "sentence" must contain that exact word, written naturally (not blanked out).
- Each distractor must be a different Chinese word from "word" and from the
  other distractors for that word, and must not itself appear in "sentence".
- Only "word" may correctly fill the blank: each distractor, placed in the
  blank, must make the sentence clearly wrong or unnatural. Never use a
  synonym of "word" or any word that would also produce a correct sentence.
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_cloze(
    data: object, words: List[VocabClozeWord]
) -> List[VocabClozeResult]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of cloze results")

    by_word = {w.word: w for w in words}
    results: List[VocabClozeResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        source = by_word.get(word)
        if not source:
            continue
        # The model sometimes ignores the Traditional-Chinese instruction and
        # writes Simplified — convert before the containment check below,
        # since a Simplified sentence otherwise silently fails to contain a
        # Traditional-only word (e.g. "廳" not found in "厅") and the whole
        # candidate gets dropped.
        sentence = convert_to_traditional_chinese(str(item.get("sentence", "")).strip())
        if not sentence or word not in sentence:
            continue
        seen = {word}
        distractors: List[str] = []
        for raw in item.get("distractors", []):
            distractor = convert_to_traditional_chinese(str(raw).strip())
            if not distractor or distractor in seen or distractor in sentence:
                continue
            seen.add(distractor)
            distractors.append(distractor)
        if distractors:
            results.append(
                VocabClozeResult(word=word, sentence=sentence, distractors=distractors[:3])
            )
    return results


async def generate_vocab_cloze_with_groq(
    words: List[VocabClozeWord],
) -> List[VocabClozeResult]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.6,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin vocabulary-quiz assistant. Always respond in "
                    "valid JSON only — no markdown fences, no prose outside the JSON. "
                    'Wrap the array in a top-level object: {"results": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_cloze_prompt(words)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("results") if isinstance(parsed, dict) else parsed
    return _parse_vocab_cloze(data, words)


async def generate_vocab_cloze_with_gemini(
    words: List[VocabClozeWord],
) -> List[VocabClozeResult]:
    payload = {"contents": [{"parts": [{"text": _vocab_cloze_prompt(words)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_cloze(data, words)


def _vocab_synonym_prompt(words: List[VocabSynonymWord]) -> str:
    word_lines = "\n".join(
        f'{i + 1}. "{w.word}" -> "{w.translation}"'
        + (f' (used in: "{w.context}")' if w.context else "")
        + (f" (already used, give a different synonym: {' / '.join(w.avoid)})" if w.avoid else "")
        for i, w in enumerate(words)
    )
    return f"""
You are building "which word means the same?" questions for an A1-A2
Mandarin vocabulary quiz. For each word below, give ONE real Traditional
Chinese word or short phrase that is a close synonym — a beginner-level word
a student would recognize as meaning (nearly) the same thing. Also give 3
WRONG but PLAUSIBLE Chinese words that are NOT synonyms of the original word
(different meaning) but could look tempting — e.g. same topic/category or
same part of speech, a real point of confusion for a learner.

Words:
{word_lines}

Return only valid JSON shaped exactly like:
[
  {{"word": "高興", "synonym": "開心", "distractors": ["生氣", "累", "餓"]}}
]

Rules:
- "word" must exactly match one of the words given above.
- "synonym" must be a real word genuinely close in meaning to "word", and
  different from "word" itself.
- Each distractor must be a different Chinese word from "word", from
  "synonym", and from the other distractors for that word.
- Distractors must NOT be synonyms or near-synonyms of "word" — "synonym"
  must stay the ONLY option that means the same. If a candidate distractor
  is close enough in meaning to defend as correct, replace it with a
  clearly different one.
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_synonym(
    data: object, words: List[VocabSynonymWord]
) -> List[VocabSynonymResult]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of synonym results")

    by_word = {w.word: w for w in words}
    results: List[VocabSynonymResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        source = by_word.get(word)
        if not source:
            continue
        synonym = convert_to_traditional_chinese(str(item.get("synonym", "")).strip())
        if not synonym or synonym == word:
            continue
        seen = {word, synonym}
        distractors: List[str] = []
        for raw in item.get("distractors", []):
            distractor = convert_to_traditional_chinese(str(raw).strip())
            if not distractor or distractor in seen:
                continue
            seen.add(distractor)
            distractors.append(distractor)
        if distractors:
            results.append(
                VocabSynonymResult(word=word, synonym=synonym, distractors=distractors[:3])
            )
    return results


async def generate_vocab_synonym_with_groq(
    words: List[VocabSynonymWord],
) -> List[VocabSynonymResult]:
    payload = {
        "model": GROQ_FEEDBACK_MODEL,
        "response_format": {"type": "json_object"},
        "temperature": 0.6,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Mandarin vocabulary-quiz assistant. Always respond in "
                    "valid JSON only — no markdown fences, no prose outside the JSON. "
                    'Wrap the array in a top-level object: {"results": [...]}.'
                ),
            },
            {"role": "user", "content": _vocab_synonym_prompt(words)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await _post_with_retry(client,
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("results") if isinstance(parsed, dict) else parsed
    return _parse_vocab_synonym(data, words)


async def generate_vocab_synonym_with_gemini(
    words: List[VocabSynonymWord],
) -> List[VocabSynonymResult]:
    payload = {"contents": [{"parts": [{"text": _vocab_synonym_prompt(words)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_synonym(data, words)


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
        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return await normalize_story_image_response(
        data,
        request,
        provider=GEMINI_FEEDBACK_MODEL,
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
                resp = await _post_with_retry(
                    client,
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
        py = canonical_pinyin_tone3(word)
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
            py = canonical_pinyin_tone3(segment)
            if py in pinyin_to_vocab and segment != pinyin_to_vocab[py]:
                result.append(pinyin_to_vocab[py])
                i += length
                replaced = True
                break
        if not replaced:
            result.append(chars[i])
            i += 1
    return "".join(result)


# A classroom of ~50 students hitting the same cloud ASR provider around the
# same moment makes a rate-limit blip (429) or a dropped connection common,
# not exceptional. A cheap retry here is much better than immediately
# burning that provider's slot in transcribe_with_auto_fallback's chain over
# one transient failure - not every caller even uses "auto" fallback.
_ASR_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_ASR_PROVIDER_MAX_ATTEMPTS = int(os.getenv("ASR_PROVIDER_MAX_ATTEMPTS", "3"))


async def _post_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """POST with short exponential backoff on timeouts/network errors and
    on retryable (429/5xx) status codes. Non-retryable status codes (4xx
    other than 429) are returned immediately on the first attempt, same as
    a plain `await client.post(...)` - callers keep their existing
    `if response.status_code != 200: raise ...` handling unchanged."""
    response: Optional[httpx.Response] = None
    for attempt in range(1, _ASR_PROVIDER_MAX_ATTEMPTS + 1):
        try:
            response = await client.post(url, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == _ASR_PROVIDER_MAX_ATTEMPTS:
                raise
        else:
            if response.status_code not in _ASR_RETRY_STATUSES or attempt == _ASR_PROVIDER_MAX_ATTEMPTS:
                return response
        await asyncio.sleep(0.5 * 2 ** (attempt - 1))
    return response


async def transcribe_with_openai(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    """Transcribe using OpenAI Whisper API."""
    async with httpx.AsyncClient() as client:
        files = {"file": ("audio.wav", audio_content, "audio/wav")}
        data = {"model": "whisper-1", "language": "zh"}
        if vocab_hint.strip():
            # Whisper uses the prompt to bias recognition toward these words/phrases.
            data["prompt"] = vocab_hint.strip()

        response = await _post_with_retry(
            client,
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

        response = await _post_with_retry(
            client,
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files=files,
            data=data,
        )

        if response.status_code != 200:
            raise Exception(f"Groq API error: {response.text}")

        text = _filter_asr_phantoms(convert_to_traditional_chinese(response.text.strip()))
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

        response = await _post_with_retry(client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FEEDBACK_MODEL}:generateContent?key={GEMINI_API_KEY}",
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
        text = _filter_asr_phantoms(convert_to_traditional_chinese(text))
        # Empty is a legitimate result (silence, filtered phantom) — not a
        # server error. Raising here used to turn a silent recording into a
        # 503 for the whole auto-fallback chain.
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


# ── Routers (imported here, after all shared models/helpers above are
# defined, since each router imports names back from this module) ─────────
from routers.admin import router as admin_router  # noqa: E402
from routers.asr import router as asr_router  # noqa: E402
from routers.analysis_v2 import router as analysis_v2_router  # noqa: E402
from routers.audio import router as audio_router  # noqa: E402
from routers.benchmark import router as benchmark_router  # noqa: E402
from routers.help_requests import router as help_requests_router  # noqa: E402
from routers.media import router as media_router  # noqa: E402
from routers.measurement import router as measurement_router  # noqa: E402
from routers.pilot import router as pilot_router  # noqa: E402
from routers.pinyin import router as pinyin_router  # noqa: E402
from routers.quiz_review import router as quiz_review_router  # noqa: E402
from routers.speaking_progress import router as speaking_progress_router  # noqa: E402
from routers.stories import router as stories_router  # noqa: E402
from routers.students import router as students_router  # noqa: E402
from routers.teachers import router as teachers_router  # noqa: E402
from routers.submissions import router as submissions_router  # noqa: E402
from routers.teacher_review import router as teacher_review_router  # noqa: E402
from routers.tones import router as tones_router  # noqa: E402
from routers.tts import router as tts_router  # noqa: E402
from routers.vocab_quiz import router as vocab_quiz_router  # noqa: E402
app.include_router(admin_router)
app.include_router(asr_router)
app.include_router(analysis_v2_router)
app.include_router(audio_router)
app.include_router(benchmark_router)
app.include_router(help_requests_router)
app.include_router(media_router)
app.include_router(measurement_router)
app.include_router(pilot_router)
app.include_router(pinyin_router)
app.include_router(quiz_review_router)
app.include_router(speaking_progress_router)
app.include_router(stories_router)
app.include_router(students_router)
app.include_router(teachers_router)
app.include_router(submissions_router)
app.include_router(teacher_review_router)
app.include_router(tts_router)
app.include_router(tones_router)
app.include_router(vocab_quiz_router)

# Study mode (OMPAL_STUDY_MODE=1) leaves exactly one pronunciation engine
# reachable: it blocks the legacy /api/analyze judgement routes and mounts the
# frozen tone-confirmation route. Unset, this only registers a middleware that
# never fires, so ordinary application behaviour is unchanged.
import study_mode  # noqa: E402

STUDY_MODE_ACTIVE = study_mode.install(app)
if STUDY_MODE_ACTIVE:
    logger.warning(
        "OMPAL study mode ACTIVE: legacy pronunciation routes disabled; "
        "canonical route mounted at /api/pronunciation/tone-attempt")


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
