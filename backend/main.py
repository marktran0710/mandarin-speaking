from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Tuple
import base64
import io
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
)

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
    GROQ_FEEDBACK_MODEL,
)
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
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
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


class VocabLookalikeWord(BaseModel):
    word: str
    translation: str
    context: Optional[str] = None
    # Look-alikes already generated for this word (from a prior generation),
    # so a regeneration call tops up the pool with genuinely new characters
    # instead of the model repeating itself.
    avoid: List[str] = []


class VocabLookalikeRequest(BaseModel):
    words: List[VocabLookalikeWord]


class VocabLookalikeResult(BaseModel):
    word: str
    # Visually-confusable Traditional Chinese words (喝/渴, 買/賣) with a
    # clearly different meaning — the tier-3 quiz's face-confusion traps.
    lookalikes: List[str]


class VocabLookalikeResponse(BaseModel):
    results: List[VocabLookalikeResult]


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
    vocabularyPos: Optional[str] = None
    vocabularyTranslation: Optional[str] = None
    phrases: Optional[str] = None
    phrasesTranslation: Optional[str] = None
    suggestedAnswer: Optional[str] = None
    listenAudioUrl: Optional[str] = None
    listenScript: Optional[str] = None
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
    # JSON-encoded array of arrays (one entry per word) — each word's entry
    # is a list of AI-generated visually-confusable words (喝/渴), grown the
    # same way vocabularyDistractors is (see vocab_quiz_lookalike / the
    # vocabulary-lookalike PATCH endpoint).
    vocabularyLookalike: Optional[str] = None
    # Medium/Hard tiers of the same scene — same plot/scene/imageUrl, just
    # progressively more complex text. Absent/blank means that tier hasn't
    # been authored yet; the student-facing conversion falls back to the
    # base (Easy) field above rather than showing blank content.
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
    listenScriptMedium: Optional[str] = None
    listenScriptHard: Optional[str] = None


class CustomStoryRequest(BaseModel):
    id: str
    title: str
    learningGoal: str
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


class StorySubmissionRequest(BaseModel):
    id: str = Field(..., max_length=128)
    storyId: str = Field(..., max_length=128)
    storyTitle: str = Field(default="", max_length=200)
    studentName: str = Field(default="Student", max_length=100)
    submittedAt: str
    scenes: List[SceneSubmission] = []


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


class Student(BaseModel):
    id: str
    name: str
    createdAt: str


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


MAX_VOCAB_LOOKALIKE_PER_WORD = 6


class VocabularyLookalikeUpdate(BaseModel):
    frameIndex: int
    wordIndex: int
    lookalikes: List[str]


class VocabularyLookalikeUpdateRequest(BaseModel):
    updates: List[VocabularyLookalikeUpdate]


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
    scene_phrases: str = "",
    scene_suggested_answer: str = "",
    scene_attempt_number: int = 1,
    verify_word: str = "",
    pinyin_hint: str = "",
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
                        scene_phrases=scene_phrases, scene_suggested_answer=scene_suggested_answer,
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
            return analyze_all(path, tx, pinyin_hint=pinyin_hint)

        # Run Praat (CPU-bound, threadpool), AI feedback (I/O-bound), and the
        # optional word-content verification pass all in parallel so checking
        # "did they actually say this word" doesn't add extra latency on top
        # of the analysis that was already happening.
        feedback_coro = (
            asyncio.sleep(0)  # no-op placeholder when feedback already done
            if audio_assessed
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
        (praat_result, maybe_feedback, (recognized_text, content_match)) = await asyncio.gather(
            run_in_threadpool(_run_praat, tmp_path, transcription),
            feedback_coro,
            verify_coro,
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

        # Turn the raw pause/rate measurements into judged, story-aggregatable
        # signals: how many pauses landed at a natural clause/punctuation
        # boundary in the reference script vs. mid-phrase ("choppy"), and the
        # articulation rate (syllables/sec, pauses excluded) for speed
        # feedback. Merged into pause_analysis so the frontend can pick these
        # up the same way it already reads pause_count/longest_pause.
        character_count = sum(1 for ch in transcription if "一" <= ch <= "鿿")
        fluency_for_response = caf_metrics.fluency_metrics(
            speech_rate, pause_analysis, character_count
        )
        pause_judgment = caf_metrics.classify_pauses(
            scene_suggested_answer.strip() or transcription, pause_analysis, word_prosody
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
            scene_phrases=scene_phrases,
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
            recognized_text=recognized_text,
            content_match=content_match,
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


def _has_speech(audio_content: bytes) -> bool:
    """Two-stage speech check: overall RMS (rejects near-silence), then a
    frame-level voiced-duration estimate (rejects brief pops / steady hum
    that pass RMS). Fails open — any decode problem (non-WAV upload, odd
    encoding) assumes speech, so the gate can only ever *prevent* a
    hallucination, never block a real recording."""
    try:
        data, sample_rate = _decode_wav_mono(audio_content)
        if len(data) == 0:
            return False
        rms = float(np.sqrt(np.mean(data**2)))
        if rms < ASR_SILENCE_RMS:
            return False

        # Voiced frames = 25ms windows (10ms hop) within 30 dB of the loudest
        # frame — the same relative criterion as librosa.effects.split's
        # top_db=30, without needing librosa installed. Vectorized via a
        # strided window view: a Python per-frame loop costs milliseconds on
        # a long recording, and this gate runs before every ASR request.
        frame = max(1, int(sample_rate * 0.025))
        hop = max(1, int(sample_rate * 0.010))
        if len(data) < frame:
            return False
        windows = np.lib.stride_tricks.sliding_window_view(data, frame)[::hop]
        frame_rms = np.sqrt(np.mean(windows**2, axis=1))
        peak = float(frame_rms.max()) if len(frame_rms) else 0.0
        if peak <= 0.0:
            return False
        voiced = frame_rms > peak * 10 ** (-30 / 20)
        voiced_seconds = float(np.sum(voiced)) * hop / sample_rate
        return voiced_seconds >= ASR_MIN_SPEECH_SECONDS
    except Exception as exc:
        logger.debug("Silence gate could not decode audio, assuming speech: %s", exc)
        return True


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

    Prefers Groq (fast, cloud) over the "auto" chain's default of the local
    ctwhisper model, which is CPU-heavy and — running alongside the Praat
    analysis on every single word attempt — made word practice noticeably
    slower once this check was added.
    """
    model = "groq" if GROQ_API_KEY else "auto"
    try:
        result = await transcribe_audio_content(audio_content, model, vocab_hint=vocab_hint or word)
        recognized = convert_to_traditional_chinese(result.text).strip()
        match = bool(recognized) and word.strip() in recognized
        return recognized, match
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
        response = await client.post(
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
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
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
        response = await client.post(
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
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
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
        response = await client.post(
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
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
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
        response = await client.post(
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
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
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
        response = await client.post(
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
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_synonym(data, words)


def _vocab_lookalike_prompt(words: List[VocabLookalikeWord]) -> str:
    word_lines = "\n".join(
        f'{i + 1}. "{w.word}" -> "{w.translation}"'
        + (f' (used in: "{w.context}")' if w.context else "")
        + (f" (already used, do not repeat: {', '.join(w.avoid)})" if w.avoid else "")
        for i, w in enumerate(words)
    )
    return f"""
You are building look-alike character traps for an A1-A2 Mandarin vocabulary
quiz. For each Traditional Chinese word below, give 3 real Traditional
Chinese words or characters that LOOK visually similar on the page — shared
components, one different radical, easily-confused shapes (like 喝/渴 or
買/賣) — but have a clearly DIFFERENT meaning.

Words:
{word_lines}

Return only valid JSON shaped exactly like:
[
  {{"word": "喝", "lookalikes": ["渴", "喂", "揭"]}}
]

Rules:
- "word" must exactly match one of the words given above.
- Each look-alike must be a real Traditional Chinese word/character,
  different from "word" and from the other look-alikes for that word.
- A look-alike must NOT be a synonym or near-synonym of "word", and must
  not share its meaning — "word" must stay the ONLY correct option when
  these appear beside it in a quiz.
- Prefer look-alikes with a different pronunciation from "word".
- Return the JSON array only, no surrounding text.
"""


def _parse_vocab_lookalike(
    data: object, words: List[VocabLookalikeWord]
) -> List[VocabLookalikeResult]:
    if not isinstance(data, list):
        raise RuntimeError("Model did not return a JSON array of look-alike results")

    by_word = {w.word: w for w in words}
    results: List[VocabLookalikeResult] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        if word not in by_word:
            continue
        seen = {word}
        lookalikes: List[str] = []
        for raw in item.get("lookalikes", []):
            lookalike = convert_to_traditional_chinese(str(raw).strip())
            if not lookalike or lookalike in seen:
                continue
            seen.add(lookalike)
            lookalikes.append(lookalike)
        if lookalikes:
            results.append(VocabLookalikeResult(word=word, lookalikes=lookalikes[:3]))
    return results


async def generate_vocab_lookalike_with_groq(
    words: List[VocabLookalikeWord],
) -> List[VocabLookalikeResult]:
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
            {"role": "user", "content": _vocab_lookalike_prompt(words)},
        ],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    data = parsed.get("results") if isinstance(parsed, dict) else parsed
    return _parse_vocab_lookalike(data, words)


async def generate_vocab_lookalike_with_gemini(
    words: List[VocabLookalikeWord],
) -> List[VocabLookalikeResult]:
    payload = {"contents": [{"parts": [{"text": _vocab_lookalike_prompt(words)}]}]}

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )

    if response.status_code != 200:
        raise RuntimeError(response.text)

    content = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(strip_json_fence(content))
    return _parse_vocab_lookalike(data, words)


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
from routers.asr import router as asr_router  # noqa: E402
from routers.audio import router as audio_router  # noqa: E402
from routers.help_requests import router as help_requests_router  # noqa: E402
from routers.media import router as media_router  # noqa: E402
from routers.stories import router as stories_router  # noqa: E402
from routers.students import router as students_router  # noqa: E402
from routers.submissions import router as submissions_router  # noqa: E402
from routers.tones import router as tones_router  # noqa: E402
from routers.vocab_quiz import router as vocab_quiz_router  # noqa: E402
from routers.vocab_quiz_analytics import router as vocab_quiz_analytics_router  # noqa: E402
app.include_router(asr_router)
app.include_router(audio_router)
app.include_router(help_requests_router)
app.include_router(media_router)
app.include_router(stories_router)
app.include_router(students_router)
app.include_router(submissions_router)
app.include_router(tones_router)
app.include_router(vocab_quiz_router)
app.include_router(vocab_quiz_analytics_router)


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
