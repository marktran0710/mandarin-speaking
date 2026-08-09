from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from main import TTSRequest
from tts_service import DEFAULT_ZH_VOICE, synthesize_sentence_mp3

router = APIRouter()


@router.post("/api/tts")
async def synthesize_tts(request: TTSRequest):
    """Synthesize a Mandarin sentence to MP3 for student-facing playback.

    Used when a scene has a teacher-authored sentence but no recorded model
    voice yet — the frontend plays this back through a normal <audio> tag
    instead of the browser's (voice-inconsistent, unrecordable) built-in
    speech synthesis.
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    try:
        mp3_bytes = await synthesize_sentence_mp3(text, voice=request.voice or DEFAULT_ZH_VOICE)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=mp3_bytes, media_type="audio/mpeg")
