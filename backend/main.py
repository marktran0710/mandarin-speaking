from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Tuple
import os
import tempfile
import httpx
from dotenv import load_dotenv
import json

from praat_analyzer import (
    extract_pitch,
    extract_formants,
    calculate_speech_rate,
    analyze_fluency,
    get_pitch_statistics,
)
from chinese_tones import (
    detect_tone,
    calculate_tone_accuracy,
    get_reference_tone_pattern,
    generate_comprehensive_feedback,
)
from ai_feedback import generate_language_feedback

# Load environment variables
load_dotenv()

app = FastAPI(title="Speaking App Backend", version="1.0.0")

# Enable CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Keys from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


# Pydantic models
class AnalysisResponse(BaseModel):
    pitch_contour: List[Tuple[float, float]]
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


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "Speaking App Backend"}


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_speech(
    file: UploadFile = File(...),
    transcription: str = Form(""),
):
    """
    Analyze Chinese speech for tone, pitch, formants, speech rate, and fluency.
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

        # Extract audio analysis
        pitch_contour = extract_pitch(tmp_path)
        formants = extract_formants(tmp_path)
        speech_rate = calculate_speech_rate(tmp_path, transcription)
        fluency_score = analyze_fluency(pitch_contour, speech_rate)
        pitch_stats = get_pitch_statistics(pitch_contour)

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

        return AnalysisResponse(
            pitch_contour=pitch_contour,
            detected_tone=detected_tone,
            tone_accuracy=tone_accuracy,
            formants=formants,
            speech_rate=speech_rate,
            fluency_score=fluency_score,
            pitch_statistics=pitch_stats,
            feedback=feedback,
            ai_feedback=ai_feedback,
        )

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
async def transcribe_speech(file: UploadFile = File(...), model: str = "openai"):
    """
    Transcribe audio to text using OpenAI Whisper or Google Gemini.
    API keys are secured on the backend.
    """
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    try:
        content = await file.read()

        if model == "openai":
            if not OPENAI_API_KEY:
                raise HTTPException(
                    status_code=500,
                    detail="OpenAI API key not configured"
                )
            return await transcribe_with_openai(content)

        elif model == "gemini":
            if not GEMINI_API_KEY:
                raise HTTPException(
                    status_code=500,
                    detail="Gemini API key not configured"
                )
            return await transcribe_with_gemini(content)

        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid model. Use 'openai' or 'gemini'"
            )

    except Exception as e:
        print(f"Error in transcribe_speech: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error transcribing speech: {str(e)}"
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
