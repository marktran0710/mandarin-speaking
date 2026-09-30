"""Synthetic voiced audio with controlled tone shapes, for Praat-level tests.

A harmonic signal whose f0 follows a chosen contour is tracked reliably by
Praat, so extraction tests can assert on pitch direction without real speech.
"""

from __future__ import annotations

import math
import struct
import wave
from typing import Optional, Sequence

SAMPLE_RATE = 16000


def _semitones(shape: str, x: float) -> float:
    if shape == "fall":
        return 4.0 - 8.0 * x
    if shape == "rise":
        return -3.0 + 6.0 * x
    if shape == "dip":
        return -4.0 * math.sin(math.pi * x)
    if shape == "flat":
        return 0.0
    raise ValueError(shape)


def synth_wav(
    path,
    shapes: Sequence[str],
    *,
    base_hz: float = 150.0,
    syllable_ms: int = 300,
    gaps_ms: Optional[Sequence[int]] = None,
    edge_silence_ms: int = 200,
) -> str:
    gaps = list(gaps_ms) if gaps_ms is not None else [120] * (len(shapes) - 1)
    samples: list[float] = [0.0] * int(SAMPLE_RATE * edge_silence_ms / 1000)
    phase = 0.0
    for index, shape in enumerate(shapes):
        count = int(SAMPLE_RATE * syllable_ms / 1000)
        ramp = int(SAMPLE_RATE * 0.025)
        for i in range(count):
            f0 = base_hz * 2.0 ** (_semitones(shape, i / (count - 1)) / 12.0)
            phase += 2.0 * math.pi * f0 / SAMPLE_RATE
            value = sum(math.sin(k * phase) / k for k in range(1, 7))
            envelope = min(1.0, i / ramp, (count - 1 - i) / ramp)
            samples.append(value * math.sin(math.pi / 2 * max(envelope, 0.0)) ** 2)
        if index < len(gaps):
            samples.extend([0.0] * int(SAMPLE_RATE * gaps[index] / 1000))
    samples.extend([0.0] * int(SAMPLE_RATE * edge_silence_ms / 1000))

    peak = max(abs(v) for v in samples) or 1.0
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"".join(struct.pack("<h", int(v / peak * 0.6 * 32767)) for v in samples))
    return str(path)


def silent_wav(path, seconds: float = 1.0) -> str:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(b"\x00\x00" * int(SAMPLE_RATE * seconds))
    return str(path)
