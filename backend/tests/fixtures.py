"""Shared test data (importable from test modules)."""
import io
import math
import struct
import wave


def make_wav_bytes(duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Return raw bytes of a minimal mono 16-bit PCM WAV file (all zeros)."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
    return buf.getvalue()


def make_tone_wav_bytes(
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    frequency_hz: float = 220.0,
    amplitude: float = 0.3,
) -> bytes:
    """A loud continuous tone — 'speech-like' enough to pass the silence gate
    (RMS + voiced-duration), for tests exercising the ASR paths behind it."""
    n_samples = int(duration_s * sample_rate)
    samples = [
        int(32767 * amplitude * math.sin(2 * math.pi * frequency_hz * i / sample_rate))
        for i in range(n_samples)
    ]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *samples))
    return buf.getvalue()


SILENT_WAV = make_wav_bytes(0.5)
SHORT_WAV  = make_wav_bytes(0.1)
LONG_WAV   = make_wav_bytes(5.0)
SPEECH_WAV = make_tone_wav_bytes(1.0)
