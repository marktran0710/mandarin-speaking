"""Text-to-speech reference audio generation for the "model voice" feature.

Uses edge-tts (free, no API key) to synthesize a Mandarin sentence. Note:
edge-tts's WordBoundary timing events do not fire for any Mandarin voice
(verified against zh-TW/zh-CN voices) — only SentenceBoundary does — so
per-word audio is produced by approximately slicing the *sentence* audio
(see reference_audio.py), not from TTS word-boundary metadata.
"""
import io

import edge_tts
import numpy as np
import soundfile as sf

DEFAULT_ZH_VOICE = "zh-TW-HsiaoChenNeural"


async def synthesize_sentence_mp3(text: str, voice: str = DEFAULT_ZH_VOICE) -> bytes:
    """Synthesize `text` and return the raw MP3 bytes edge-tts streams back."""
    communicate = edge_tts.Communicate(text, voice=voice)
    audio_bytes = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])
    if not audio_bytes:
        raise RuntimeError("TTS produced no audio for this text.")
    return bytes(audio_bytes)


def decode_mp3_to_pcm(mp3_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode MP3 bytes to a mono float32 PCM array + sample rate.

    soundfile/libsndfile decodes this in-process (verified against edge-tts's
    output) — no ffmpeg binary needed.
    """
    data, sample_rate = sf.read(io.BytesIO(mp3_bytes), dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sample_rate


def write_wav(path: str, pcm: np.ndarray, sample_rate: int) -> None:
    sf.write(path, pcm, sample_rate, subtype="PCM_16")
