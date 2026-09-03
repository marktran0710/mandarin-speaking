

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
