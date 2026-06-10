from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Tuple
import os
import tempfile
import httpx
from dotenv import load_dotenv
import json
from urllib.parse import quote
from starlette.concurrency import run_in_threadpool

from praat_analyzer import (
    extract_pitch,
    extract_formants,
    calculate_speech_rate,
    analyze_fluency,
    get_pitch_statistics,
    estimate_word_prosody,
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
        "vibevoice,gemini,openai",
    ).split(",")
    if model.strip()
]
FUNASR_MODEL = os.getenv("FUNASR_MODEL", "paraformer-zh")
FUNASR_VAD_MODEL = os.getenv("FUNASR_VAD_MODEL", "fsmn-vad")
FUNASR_PUNC_MODEL = os.getenv("FUNASR_PUNC_MODEL", "ct-punc")
VIBEVOICE_ASR_MODEL = os.getenv("VIBEVOICE_ASR_MODEL", "microsoft/VibeVoice-ASR-HF")
VIBEVOICE_DEVICE = int(os.getenv("VIBEVOICE_DEVICE", "-1"))
_funasr_model = None
_vibevoice_asr_pipeline = None


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
    speech_rate: float
    fluency_score: float
    pitch_statistics: dict
    feedback: str
    ai_feedback: dict


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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Speaking App Backend"}


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

    return build_story_image_fallback(request, provider="local")


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_speech(
    file: UploadFile = File(...),
    transcription: str = Form(""),
    asr_model: str = Form(""),
):
    """
    Analyze Chinese speech for tone, pitch, formants, speech rate, and fluency.
    If transcription is empty and asr_model is provided, transcribe first, then
    run Praat against the same audio.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    tmp_path = None
    try:
        # Save uploaded file to temporary location
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".wav"
        ) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        transcription_model = ""
        if not transcription.strip() and asr_model.strip():
            transcription_result = await transcribe_audio_content(
                content,
                asr_model.strip(),
            )
            transcription = transcription_result.text
            transcription_model = transcription_result.model

        # Extract audio analysis
        pitch_contour = extract_pitch(tmp_path)
        formants = extract_formants(tmp_path)
        speech_rate = calculate_speech_rate(tmp_path, transcription)
        fluency_score = analyze_fluency(pitch_contour, speech_rate)
        pitch_stats = get_pitch_statistics(pitch_contour)
        word_prosody = estimate_word_prosody(pitch_contour, transcription)

        # Detect tone
        tone_detection = detect_tone(pitch_contour)
        detected_tone = tone_detection["detected_tone"]
        tone_accuracy = tone_detection["scores"].get(detected_tone, 0)

        # Generate comprehensive feedback
        feedback = generate_comprehensive_feedback(
            detected_tone,
            tone_accuracy,
            speech_rate,
            fluency_score,
            pitch_contour,
        )
        ai_feedback = await generate_language_feedback(transcription)
        description = build_analysis_description(
            transcription,
            transcription_model,
            word_prosody,
        )

        return AnalysisResponse(
            description=description,
            transcription=transcription,
            transcription_model=transcription_model,
            pitch_contour=pitch_contour,
            word_prosody=word_prosody,
            detected_tone=detected_tone,
            tone_accuracy=tone_accuracy,
            formants=formants,
            speech_rate=speech_rate,
            fluency_score=fluency_score,
            pitch_statistics=pitch_stats,
            feedback=feedback,
            ai_feedback=ai_feedback,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in analyze_speech: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error analyzing speech: {str(e)}"
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_speech(
    file: UploadFile = File(...),
    model: str = Form("openai"),
):
    """
    Transcribe audio to text using OpenAI Whisper, Google Gemini, FunASR, or VibeVoice-ASR.
    API keys are secured on the backend. Local ASR models run on the backend.
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

    if model == "vibevoice":
        return await transcribe_with_vibevoice(audio_content)

    raise HTTPException(
        status_code=400,
        detail="Invalid model. Use 'auto', 'openai', 'gemini', 'funasr', or 'vibevoice'"
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

    print(f"Auto ASR failed; continuing with audio-only Praat. Errors: {errors}")
    return TranscriptionResponse(text="", model="auto:none")


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
- The 6 frames must tell one connected real-life story.
- Each frame should show a visible event, not only a place.
- Use safe classroom content.
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
    return normalize_story_image_response(
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


def normalize_story_image_response(
    data: dict,
    request: StoryImageGenerationRequest,
    provider: str,
) -> StoryImageGenerationResponse:
    fallback = build_story_image_fallback(request, provider=provider)
    raw_frames = data.get("frames", [])
    frames = []

    for index in range(6):
        fallback_frame = fallback.frames[index]
        raw_frame = raw_frames[index] if index < len(raw_frames) and isinstance(raw_frames[index], dict) else {}
        title = str(raw_frame.get("title") or fallback_frame.title).strip()
        student_prompt = str(
            raw_frame.get("student_prompt") or fallback_frame.student_prompt
        ).strip()
        vocabulary = raw_frame.get("vocabulary") or fallback_frame.vocabulary
        if not isinstance(vocabulary, list):
            vocabulary = fallback_frame.vocabulary
        image_prompt = str(raw_frame.get("image_prompt") or fallback_frame.image_prompt).strip()

        frames.append(
            StoryImageFrame(
                index=index + 1,
                title=title,
                student_prompt=student_prompt,
                vocabulary=[str(word) for word in vocabulary[:5]],
                image_prompt=image_prompt,
                image_url=build_scene_svg_data_url(index + 1, title, request.situation),
            )
        )

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


def _get_vibevoice_asr_pipeline():
    global _vibevoice_asr_pipeline

    if _vibevoice_asr_pipeline is None:
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError(
                "VibeVoice-ASR requires Hugging Face Transformers on the backend. "
                "Install backend requirements or run `pip install transformers torch`."
            ) from exc

        _vibevoice_asr_pipeline = pipeline(
            "automatic-speech-recognition",
            model=VIBEVOICE_ASR_MODEL,
            device=VIBEVOICE_DEVICE,
            trust_remote_code=True,
        )

    return _vibevoice_asr_pipeline


def _extract_vibevoice_text(result) -> str:
    if isinstance(result, dict):
        if "text" in result:
            return str(result["text"]).strip()
        if "chunks" in result and isinstance(result["chunks"], list):
            return " ".join(
                str(chunk.get("text", "")).strip()
                for chunk in result["chunks"]
                if isinstance(chunk, dict) and chunk.get("text")
            ).strip()

    if isinstance(result, list):
        return " ".join(_extract_vibevoice_text(item) for item in result).strip()

    return str(result or "").strip()


def _transcribe_with_vibevoice_sync(audio_content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
        tmp_file.write(audio_content)
        tmp_path = tmp_file.name

    try:
        asr_pipeline = _get_vibevoice_asr_pipeline()
        result = asr_pipeline(tmp_path)
        text = _extract_vibevoice_text(result)
        if not text:
            raise RuntimeError("VibeVoice-ASR did not return transcription text.")
        return text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_with_vibevoice(audio_content: bytes) -> TranscriptionResponse:
    """Transcribe using local VibeVoice-ASR through Transformers on the backend."""
    text = await run_in_threadpool(_transcribe_with_vibevoice_sync, audio_content)
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
