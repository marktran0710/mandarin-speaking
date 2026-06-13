"""Shared test data (importable from test modules)."""
import io
import struct
import wave


def make_wav_bytes(duration_s: float = 0.5, sample_rate: int = 16000) -> bytes:
    """Return raw bytes of a minimal mono 16-bit PCM WAV file."""
    n_samples = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))
    return buf.getvalue()


SILENT_WAV = make_wav_bytes(0.5)
SHORT_WAV  = make_wav_bytes(0.1)
LONG_WAV   = make_wav_bytes(5.0)
