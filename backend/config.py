"""Centralised configuration: env vars, logging, rate limiter, CORS origins."""
import collections
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import HTTPException

# Load backend/.env first, then root .env.local for local full-stack runs.
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.local"))

# ── Structured logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("speaking_app")


def clean_api_key(value: Optional[str]) -> Optional[str]:
    key = (value or "").strip()
    if not key or "your_" in key.lower() or key.lower().endswith("_here"):
        return None
    return key


# ── API keys & ASR config ──────────────────────────────────────────────────
OPENAI_API_KEY = clean_api_key(os.getenv("OPENAI_API_KEY") or os.getenv("VITE_OPENAI_API_KEY"))
GEMINI_API_KEY = clean_api_key(os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY"))
ASR_FALLBACK_ORDER = [
    model.strip()
    for model in os.getenv("ASR_FALLBACK_ORDER", "ctwhisper").split(",")
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

# ── File storage ───────────────────────────────────────────────────────────
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "dist"
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "uploads"))
AUDIO_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "audio")
IMAGE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "images")
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
os.makedirs(IMAGE_UPLOAD_DIR, exist_ok=True)

# ── Endpoint limits ────────────────────────────────────────────────────────
ANALYZE_TIMEOUT_SECONDS = int(os.getenv("ANALYZE_TIMEOUT_SECONDS", "120"))
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(10 * 1024 * 1024)))

# ── CORS ───────────────────────────────────────────────────────────────────
def get_cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS")
    if configured:
        return [o.strip() for o in configured.split(",") if o.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:9000",
        "http://127.0.0.1:9000",
        "http://localhost:3000",
    ]


# ── In-memory rate limiter ─────────────────────────────────────────────────
_rate_limits: dict[str, collections.deque] = {}
_rate_limit_lock = threading.Lock()


def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    now = time.monotonic()
    with _rate_limit_lock:
        dq = _rate_limits.setdefault(key, collections.deque())
        while dq and now - dq[0] > window_seconds:
            dq.popleft()
        if len(dq) >= max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {max_requests} requests per {window_seconds}s.",
            )
        dq.append(now)
