"""ASR (speech-to-text): provider routing, fallback, and per-engine transcription.

Five engines behind one entry point, `transcribe_audio_content()`:
  - openai, gemini, groq: cloud Whisper-family APIs.
  - ctwhisper: a local Chinese/Taiwanese-tuned Whisper model (CPU-friendly,
    free, slower).
  - vibevoice: a local, experimental ASR model.

`transcribe_with_auto_fallback()` walks ASR_FALLBACK_ORDER (default:
groq, ctwhisper) so a missing API key or a transient provider failure
degrades to the next engine instead of failing the whole request.

Two heavy local models (ctwhisper, vibevoice) load lazily on first use unless
warmed up at server startup (see CT_WHISPER_WARM_ON_START /
VIBEVOICE_WARM_ON_START) - main.py's startup hooks call
ensure_ct_whisper_load_started() / ensure_vibevoice_load_started() directly
since only the composition root owns the FastAPI `app` object.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import threading
import time
from typing import Optional

import httpx
from fastapi import HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from services.ai_feedback import GEMINI_FEEDBACK_MODEL
from config import settings

logger = logging.getLogger("speaking_app")


# ── Response models ─────────────────────────────────────────────────────────

class TranscriptionResponse(BaseModel):
    text: str
    model: str


class AsrStatusResponse(BaseModel):
    provider: str
    status: str
    message: str


# ── Config ───────────────────────────────────────────────────────────────────
# OPENAI_API_KEY/GEMINI_API_KEY/GROQ_API_KEY are also read independently by
# main_parts (vocab extraction, quiz review chat, story images) - both sides
# read the same config.settings, so there is one source of truth even though
# each module caches its own copy.
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
CT_WHISPER_MODEL = settings.ct_whisper_model
CT_WHISPER_DEVICE = settings.ct_whisper_device
CT_WHISPER_LANGUAGE = settings.ct_whisper_language
CT_WHISPER_TASK = settings.ct_whisper_task
CT_WHISPER_CACHE_DIR = settings.ct_whisper_cache_dir
CT_WHISPER_WARM_ON_START = settings.ct_whisper_warm_on_start
VIBEVOICE_ASR_MODEL = settings.vibevoice_asr_model
VIBEVOICE_DEVICE = settings.vibevoice_device
VIBEVOICE_TORCH_DTYPE = settings.vibevoice_torch_dtype
VIBEVOICE_WARM_ON_START = settings.vibevoice_warm_on_start
VIBEVOICE_MAX_NEW_TOKENS = settings.vibevoice_max_new_tokens
VIBEVOICE_MAX_TIME_SECONDS = settings.vibevoice_max_time_seconds
VIBEVOICE_CACHE_DIR = settings.vibevoice_cache_dir

_ct_whisper_model = None
_ct_whisper_load_lock = threading.Lock()
_ct_whisper_load_thread = None
_ct_whisper_load_error = None
_vibevoice_asr_model = None
_vibevoice_load_lock = threading.Lock()
_vibevoice_load_thread = None
_vibevoice_load_error = None


# ── Silence gate ─────────────────────────────────────────────────────────────

def _has_speech(audio_content: bytes) -> bool:
    """Two-stage speech check: overall RMS (rejects near-silence), then a
    frame-level voiced-duration estimate (rejects brief pops / steady hum
    that pass RMS). Fails open - any decode problem (non-WAV upload, odd
    encoding) assumes speech, so the gate can only ever *prevent* a
    hallucination, never block a real recording."""
    # Deferred: assess_recording_quality lives in main (not yet migrated) and
    # main imports this module during its own startup, so importing it at
    # module scope here would be circular.
    from main import assess_recording_quality

    quality = assess_recording_quality(audio_content)
    # Keep the legacy fail-open behavior for formats this WAV-only preflight
    # cannot decode. Other failures are explicit evidence that ASR should
    # not be allowed to hallucinate a transcript.
    return quality["status"] != "retry"


# Stock phrases Whisper-family models emit for silence/noise - video-outro
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
    normalized = text.strip().strip("。.!!?？,， ").replace(" ", "").lower()
    if normalized in _ASR_PHANTOM_PHRASES:
        logger.info("ASR phantom phrase filtered: %r", text)
        return ""
    return text


def _to_traditional(text: str) -> str:
    # Deferred for the same reason as assess_recording_quality above.
    from main import convert_to_traditional_chinese

    return convert_to_traditional_chinese(text)


# ── Retry helper ─────────────────────────────────────────────────────────────

# A classroom of ~50 students hitting the same cloud ASR provider around the
# same moment makes a rate-limit blip (429) or a dropped connection common,
# not exceptional. A cheap retry here is much better than immediately
# burning that provider's slot in transcribe_with_auto_fallback's chain over
# one transient failure - not every caller even uses "auto" fallback.
_ASR_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_ASR_PROVIDER_MAX_ATTEMPTS = settings.asr_provider_max_attempts


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


# ── Cloud engines ────────────────────────────────────────────────────────────

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
        text = _to_traditional(result["text"])
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

        text = _filter_asr_phantoms(_to_traditional(response.text.strip()))
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
        text = _to_traditional(text)
        return TranscriptionResponse(text=text, model="gemini")


# ── Local engine: Chinese/Taiwanese Whisper (ctwhisper) ─────────────────────

def _get_ct_whisper_model():
    global _ct_whisper_model

    # Guards against a real request racing the background warm-up thread (or
    # two real requests racing each other) into loading the model twice.
    with _ct_whisper_load_lock:
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


def _load_ct_whisper_model_background() -> None:
    global _ct_whisper_model, _ct_whisper_load_error

    started_at = time.perf_counter()
    logger.info("ctwhisper: background warm-up starting")
    try:
        model_bundle = _get_ct_whisper_model()
        with _ct_whisper_load_lock:
            _ct_whisper_model = model_bundle
            _ct_whisper_load_error = None
        logger.info(f"ctwhisper: background warm-up finished in {time.perf_counter() - started_at:.1f}s")
    except Exception as exc:
        with _ct_whisper_load_lock:
            _ct_whisper_load_error = str(exc)
        logger.warning(f"ctwhisper: background warm-up failed after {time.perf_counter() - started_at:.1f}s: {exc}")


def ensure_ct_whisper_load_started() -> None:
    global _ct_whisper_load_thread

    with _ct_whisper_load_lock:
        if _ct_whisper_model is not None or _ct_whisper_load_error:
            return
        if _ct_whisper_load_thread is not None and _ct_whisper_load_thread.is_alive():
            return

        _ct_whisper_load_thread = threading.Thread(
            target=_load_ct_whisper_model_background,
            name="ctwhisper-loader",
            daemon=True,
        )
        _ct_whisper_load_thread.start()


def _transcribe_with_ct_whisper_sync(audio_content: bytes, vocab_hint: str = "") -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_content)
        tmp_path = tmp_file.name

    try:
        # librosa decodes the recording before it ever reaches the model, so
        # it must be checked here too - it's a direct dependency of this
        # function, not just a transitive one that happens to already be
        # installed on some dev machines for an unrelated reason.
        try:
            import librosa
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "Chinese/Taiwanese Whisper requires torch, transformers, and librosa."
            ) from exc

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
        text = _filter_asr_phantoms(_to_traditional(text))
        # Empty is a legitimate result (silence, filtered phantom) - not a
        # server error. Raising here used to turn a silent recording into a
        # 503 for the whole auto-fallback chain.
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_with_ct_whisper(audio_content: bytes, vocab_hint: str = "") -> TranscriptionResponse:
    """Transcribe using a Chinese/Taiwanese Whisper model."""
    text = await run_in_threadpool(_transcribe_with_ct_whisper_sync, audio_content, vocab_hint)
    return TranscriptionResponse(text=text, model="ctwhisper")


# ── Local engine: VibeVoice-ASR (experimental) ──────────────────────────────

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


def ensure_vibevoice_load_started() -> None:
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

    ensure_vibevoice_load_started()
    raise HTTPException(
        status_code=503,
        detail=(
            "VibeVoice-ASR is loading the local model weights. "
            "Please try again in a few minutes."
        ),
    )


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


# ── Routing + fallback ───────────────────────────────────────────────────────

async def transcribe_audio_content(
    audio_content: bytes,
    model: str,
    vocab_hint: str = "",
) -> TranscriptionResponse:
    # Gate before dispatching to ANY provider - cloud Whisper hallucinates
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

    if model in {"ctwhisper", "chinese_taiwanese_whisper"}:
        return await transcribe_with_ct_whisper(audio_content, vocab_hint=vocab_hint)

    if model == "vibevoice":
        return await transcribe_with_vibevoice(audio_content)

    raise HTTPException(
        status_code=400,
        detail="Invalid model. Use 'auto', 'ctwhisper', 'openai', 'gemini', 'groq', or 'vibevoice'"
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

    # Every provider ran but heard nothing - that's silence or unclear
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
