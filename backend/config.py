"""Backend runtime configuration.

Environment parsing lives here so application modules consume one immutable
settings snapshot instead of each route reading environment variables ad hoc.
The defaults intentionally match the legacy backend values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _clean_api_key(value: str | None) -> str | None:
    key = (value or "").strip()
    if not key or "your_" in key.lower() or key.lower().endswith("_here"):
        return None
    return key


@dataclass(frozen=True)
class Settings:
    app_env: str
    frontend_dist: Path
    remote_media_allowed_hosts: frozenset[str]
    upload_dir: str
    audio_upload_dir: str
    image_upload_dir: str
    story_audio_upload_dir: str
    openai_api_key: str | None
    gemini_api_key: str | None
    groq_api_key: str | None
    groq_whisper_model: str
    asr_fallback_order: tuple[str, ...]
    funasr_model: str
    funasr_vad_model: str
    funasr_punc_model: str
    ct_whisper_model: str
    ct_whisper_device: str
    ct_whisper_language: str
    ct_whisper_task: str
    ct_whisper_cache_dir: str
    vibevoice_asr_model: str
    vibevoice_device: str
    vibevoice_torch_dtype: str
    vibevoice_warm_on_start: bool
    vibevoice_max_new_tokens: int
    vibevoice_max_time_seconds: float
    vibevoice_cache_dir: str
    max_audio_bytes: int
    analyze_timeout_seconds: int
    analyze_concurrency_limit: int
    analyze_queue_limit: int
    asr_silence_rms: float
    asr_min_speech_seconds: float
    feedback_min_duration_seconds: float
    feedback_max_clipping_ratio: float
    feedback_min_pitch_points: int
    asr_provider_max_attempts: int

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")
        backend_dir = Path(__file__).resolve().parent
        upload_dir = os.getenv("UPLOAD_DIR", str(backend_dir / "uploads"))
        model_cache = os.getenv(
            "CT_WHISPER_CACHE_DIR",
            str(backend_dir.parent / ".models" / "huggingface"),
        )
        return cls(
            app_env=os.getenv("APP_ENV", "development"),
            frontend_dist=Path(
                os.getenv("FRONTEND_DIST", str(backend_dir.parent / "frontend" / "dist"))
            ),
            remote_media_allowed_hosts=frozenset(
                host.strip().lower()
                for host in os.getenv("REMOTE_MEDIA_ALLOWED_HOSTS", "").split(",")
                if host.strip()
            ),
            upload_dir=upload_dir,
            audio_upload_dir=os.path.join(upload_dir, "audio"),
            image_upload_dir=os.path.join(upload_dir, "images"),
            story_audio_upload_dir=os.path.join(upload_dir, "story_audio"),
            openai_api_key=_clean_api_key(os.getenv("OPENAI_API_KEY") or os.getenv("VITE_OPENAI_API_KEY")),
            gemini_api_key=_clean_api_key(os.getenv("GEMINI_API_KEY") or os.getenv("VITE_GEMINI_API_KEY")),
            groq_api_key=_clean_api_key(os.getenv("GROQ_API_KEY") or os.getenv("VITE_GROQ_API_KEY")),
            groq_whisper_model=os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3"),
            asr_fallback_order=tuple(
                model.strip()
                for model in os.getenv("ASR_FALLBACK_ORDER", "groq,ctwhisper").split(",")
                if model.strip()
            ),
            funasr_model=os.getenv("FUNASR_MODEL", "paraformer-zh"),
            funasr_vad_model=os.getenv("FUNASR_VAD_MODEL", "fsmn-vad"),
            funasr_punc_model=os.getenv("FUNASR_PUNC_MODEL", "ct-punc"),
            ct_whisper_model=os.getenv("CT_WHISPER_MODEL", "openai/whisper-small"),
            ct_whisper_device=os.getenv("CT_WHISPER_DEVICE", "cpu"),
            ct_whisper_language=os.getenv("CT_WHISPER_LANGUAGE", "chinese"),
            ct_whisper_task=os.getenv("CT_WHISPER_TASK", "transcribe"),
            ct_whisper_cache_dir=model_cache,
            vibevoice_asr_model=os.getenv("VIBEVOICE_ASR_MODEL", "microsoft/VibeVoice-ASR"),
            vibevoice_device=os.getenv("VIBEVOICE_DEVICE", "cpu"),
            vibevoice_torch_dtype=os.getenv("VIBEVOICE_TORCH_DTYPE", "bfloat16"),
            vibevoice_warm_on_start=os.getenv("VIBEVOICE_WARM_ON_START", "false").lower() == "true",
            vibevoice_max_new_tokens=int(os.getenv("VIBEVOICE_MAX_NEW_TOKENS", "64")),
            vibevoice_max_time_seconds=float(os.getenv("VIBEVOICE_MAX_TIME_SECONDS", "45")),
            vibevoice_cache_dir=os.getenv("VIBEVOICE_CACHE_DIR", model_cache),
            max_audio_bytes=int(os.getenv("MAX_AUDIO_BYTES", "10485760")),
            analyze_timeout_seconds=int(os.getenv("ANALYZE_TIMEOUT_SECONDS", "120")),
            analyze_concurrency_limit=int(os.getenv("ANALYZE_CONCURRENCY_LIMIT", "4")),
            analyze_queue_limit=int(os.getenv("ANALYZE_QUEUE_LIMIT", "16")),
            asr_silence_rms=float(os.getenv("ASR_SILENCE_RMS", "0.02")),
            asr_min_speech_seconds=float(os.getenv("ASR_MIN_SPEECH_SECONDS", "0.4")),
            feedback_min_duration_seconds=float(os.getenv("FEEDBACK_MIN_DURATION_SECONDS", "0.45")),
            feedback_max_clipping_ratio=float(os.getenv("FEEDBACK_MAX_CLIPPING_RATIO", "0.08")),
            feedback_min_pitch_points=int(os.getenv("FEEDBACK_MIN_PITCH_POINTS", "8")),
            asr_provider_max_attempts=int(os.getenv("ASR_PROVIDER_MAX_ATTEMPTS", "3")),
        )


settings = Settings.from_environment()
