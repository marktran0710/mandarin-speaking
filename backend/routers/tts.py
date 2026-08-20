from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from main import TTSRequest
from reference_voice import synthesize_best_reference_audio
from tts_service import synthesize_sentence_mp3
import auth

router = APIRouter(dependencies=[Depends(auth.get_current_identity)])


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
        if request.voice:
            mp3_bytes = await synthesize_sentence_mp3(text, voice=request.voice)
        else:
            # The default student-facing TTS now evaluates all configured
            # Taiwan voices and returns the candidate with the strongest
            # syllable coverage, so the audio heard during practice is the
            # best available model rather than an arbitrary first voice.
            best = await synthesize_best_reference_audio(text)
            mp3_bytes = best["mp3_bytes"]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=mp3_bytes, media_type="audio/mpeg")
