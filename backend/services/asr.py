"""ASR provider implementations and auto-fallback chain."""
import asyncio
import os
import tempfile
import threading

import httpx
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from config import (
    ASR_FALLBACK_ORDER,
    CT_WHISPER_CACHE_DIR,
    CT_WHISPER_DEVICE,
    CT_WHISPER_LANGUAGE,
    CT_WHISPER_TASK,
    CT_WHISPER_MODEL,
    FUNASR_MODEL,
    FUNASR_PUNC_MODEL,
    FUNASR_VAD_MODEL,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    VIBEVOICE_ASR_MODEL,
    VIBEVOICE_CACHE_DIR,
    VIBEVOICE_DEVICE,
    VIBEVOICE_MAX_NEW_TOKENS,
    VIBEVOICE_MAX_TIME_SECONDS,
    VIBEVOICE_TORCH_DTYPE,
    logger,
)
from models import TranscriptionResponse

# ── Lazy-loaded model globals ──────────────────────────────────────────────
_funasr_model = None
_ct_whisper_model = None
_vibevoice_asr_model = None
_vibevoice_load_lock = threading.Lock()
_vibevoice_load_thread = None
_vibevoice_load_error = None


# ── Routing ────────────────────────────────────────────────────────────────

async def transcribe_audio_content(
    audio_content: bytes,
    model: str,
) -> TranscriptionResponse:
    if model == "auto":
        return await transcribe_with_auto_fallback(audio_content)
    if model == "openai":
        if not OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")
        return await transcribe_with_openai(audio_content)
    if model == "gemini":
        if not GEMINI_API_KEY:
            raise HTTPException(status_code=500, detail="Gemini API key not configured")
        return await transcribe_with_gemini(audio_content)
    if model == "funasr":
        return await transcribe_with_funasr(audio_content)
    if model in {"ctwhisper", "chinese_taiwanese_whisper"}:
        return await transcribe_with_ct_whisper(audio_content)
    if model == "vibevoice":
        return await transcribe_with_vibevoice(audio_content)
    raise HTTPException(
        status_code=400,
        detail="Invalid model. Use 'auto', 'ctwhisper', 'openai', 'gemini', 'funasr', or 'vibevoice'",
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
                return TranscriptionResponse(text=result.text, model=f"auto:{result.model}")
            errors.append(f"{provider}: empty transcription")
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    detail = (
        "No local ASR model produced a transcript. Make sure the Chinese/Taiwanese "
        "Whisper model is installed on the backend. Tried: " + "; ".join(errors)
    )
    logger.error("Auto ASR failed. Errors: %s", errors)
    raise HTTPException(status_code=503, detail=detail)


# ── OpenAI ─────────────────────────────────────────────────────────────────

async def transcribe_with_openai(audio_content: bytes) -> TranscriptionResponse:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": ("audio.wav", audio_content, "audio/wav")},
            data={"model": "whisper-1", "language": "zh"},
        )
    if response.status_code != 200:
        raise Exception(f"OpenAI API error: {response.text}")
    return TranscriptionResponse(text=response.json()["text"], model="openai")


# ── Gemini ─────────────────────────────────────────────────────────────────

async def transcribe_with_gemini(audio_content: bytes) -> TranscriptionResponse:
    import base64
    audio_b64 = base64.b64encode(audio_content).decode()
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
                {"text": "Please transcribe this audio to text. Only provide the transcription without any additional explanation."},
            ]
        }]
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            json=payload,
        )
    if response.status_code != 200:
        raise Exception(f"Gemini API error: {response.text}")
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    return TranscriptionResponse(text=text, model="gemini")


# ── FunASR ─────────────────────────────────────────────────────────────────

def _get_funasr_model():
    global _funasr_model
    if _funasr_model is None:
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "FunASR is not installed. Install backend requirements or run "
                "`pip install funasr modelscope`."
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
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_content)
        tmp_path = f.name
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
    text = await run_in_threadpool(_transcribe_with_funasr_sync, audio_content)
    return TranscriptionResponse(text=text, model="funasr")


# ── CT-Whisper ─────────────────────────────────────────────────────────────

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
            CT_WHISPER_MODEL, cache_dir=CT_WHISPER_CACHE_DIR
        )
        model = WhisperForConditionalGeneration.from_pretrained(
            CT_WHISPER_MODEL, cache_dir=CT_WHISPER_CACHE_DIR, low_cpu_mem_usage=True
        )
        device = CT_WHISPER_DEVICE
        if device != "auto":
            model = model.to(device)
        model.eval()
        _ct_whisper_model = (processor, model, device)
    return _ct_whisper_model


def convert_to_traditional_chinese(text: str) -> str:
    try:
        from opencc import OpenCC
        return OpenCC("s2twp").convert(text)
    except Exception:
        return text


def _transcribe_with_ct_whisper_sync(audio_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_content)
        tmp_path = f.name
    try:
        import librosa
        import torch

        processor, model, device = _get_ct_whisper_model()
        audio, _ = librosa.load(tmp_path, sr=16000, mono=True)
        inputs = processor(audio, sampling_rate=16000, return_tensors="pt")
        input_features = inputs.input_features.to(device)
        forced_decoder_ids = processor.get_decoder_prompt_ids(
            language=CT_WHISPER_LANGUAGE, task=CT_WHISPER_TASK
        )
        with torch.no_grad():
            predicted_ids = model.generate(
                input_features,
                forced_decoder_ids=forced_decoder_ids,
                max_new_tokens=128,
            )
        text = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0].strip()
        text = convert_to_traditional_chinese(text)
        if not text:
            raise RuntimeError("Chinese/Taiwanese Whisper returned an empty transcript.")
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_with_ct_whisper(audio_content: bytes) -> TranscriptionResponse:
    text = await run_in_threadpool(_transcribe_with_ct_whisper_sync, audio_content)
    return TranscriptionResponse(text=text, model="ctwhisper")


# ── VibeVoice ──────────────────────────────────────────────────────────────

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

        from vibevoice.modular.modeling_vibevoice_asr import VibeVoiceASRForConditionalGeneration
        from vibevoice.processor.vibevoice_asr_processor import VibeVoiceASRProcessor
    except ImportError as exc:
        raise RuntimeError(
            "VibeVoice-ASR library is not installed. Install it and its torch/transformers dependencies."
        ) from exc

    device = VIBEVOICE_DEVICE
    dtype_map = {"float32": "torch.float32", "float16": "torch.float16", "bfloat16": "torch.bfloat16"}
    import torch as _torch
    dtype = getattr(_torch, VIBEVOICE_TORCH_DTYPE.lower(), _torch.bfloat16)
    os.makedirs(VIBEVOICE_CACHE_DIR, exist_ok=True)
    processor = VibeVoiceASRProcessor.from_pretrained(
        VIBEVOICE_ASR_MODEL, cache_dir=VIBEVOICE_CACHE_DIR, local_files_only=True
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
        bundle = _load_vibevoice_asr_model()
        with _vibevoice_load_lock:
            _vibevoice_asr_model = bundle
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
        detail="VibeVoice-ASR is loading the local model weights. Please try again in a few minutes.",
    )


def _extract_vibevoice_text(result: dict) -> str:
    segments = result.get("segments") if isinstance(result, dict) else None
    if isinstance(segments, list) and segments:
        return " ".join(
            str(seg.get("text", "")).strip()
            for seg in segments
            if isinstance(seg, dict) and seg.get("text")
        ).strip()
    return str(result.get("raw_text", "") if isinstance(result, dict) else "").strip()


def _transcribe_with_vibevoice_sync(audio_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(audio_content)
        tmp_path = f.name
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
            k: v.to(device) if isinstance(v, torch.Tensor) else v
            for k, v in inputs.items()
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
        text = _extract_vibevoice_text({"raw_text": generated_text, "segments": segments})
        if not text:
            raise RuntimeError("VibeVoice-ASR did not return transcription text.")
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_with_vibevoice(audio_content: bytes) -> TranscriptionResponse:
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
