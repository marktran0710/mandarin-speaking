"""Small WAV read/write helpers shared by real-audio processing paths."""

from __future__ import annotations

import numpy as np
import soundfile as sf


def write_wav(path: str, pcm: np.ndarray, sample_rate: int) -> None:
    sf.write(path, pcm, sample_rate, subtype="PCM_16")


def read_wav(path: str) -> tuple[np.ndarray, int]:
    """Read a WAV file into mono float32 PCM plus its sample rate."""
    data, sample_rate = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sample_rate
