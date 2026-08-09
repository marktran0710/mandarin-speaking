"""STUDY_PCM16K_v1 -- the one sample-rate conversion used by the study path.

The frozen model was fitted only on natively-16 kHz audio, and TV2 measured
that resampling can move a short-token score across t_pass. The study path
therefore performs sample-rate conversion exactly ONCE, in the browser, with
this algorithm, and the backend performs none.

This module is the Python mirror of src/study/pcm16k.ts. Both implement the
same spec below; verify_human_exposure_path.py asserts they agree to 1e-12 on
shared vectors, so "one deterministic implementation" is a checked property and
not a claim.

    STUDY_PCM16K_v1
      target rate      16000 Hz, mono, 16-bit signed PCM in a WAV container
      identity rule    source rate == 16000 -> samples pass through untouched
      ratio            L/M reduced by gcd(16000, source_rate)
      filter           Blackman-windowed sinc, linear phase
      cutoff           0.5 / max(L, M)   (normalised to the upsampled rate)
      taps             2 * (16 * max(L, M)) + 1
      gain             L
      evaluation       polyphase; only non-zero upsampled taps are touched
      edges            source index clamped to [0, n-1] (constant extension)

Blackman rather than Kaiser deliberately: it needs no modified Bessel function,
so the TS and Python versions cannot drift through a different I0 approximation.
"""

from __future__ import annotations

import io
import math
import struct
from math import gcd

import numpy as np

STUDY_PCM_SPEC_VERSION = "STUDY_PCM16K_v1"
TARGET_SAMPLE_RATE = 16000
HALF_TAPS_PER_PHASE = 16
PCM_FULL_SCALE = 32767


def design_filter(up: int, down: int) -> np.ndarray:
    """Blackman-windowed sinc low-pass, scaled by the upsampling factor."""
    max_rate = max(up, down)
    half = HALF_TAPS_PER_PHASE * max_rate
    taps = 2 * half + 1
    cutoff = 0.5 / max_rate
    coefficients = np.empty(taps, dtype=np.float64)
    for index in range(taps):
        position = index - half
        if position == 0:
            value = 2.0 * cutoff
        else:
            angle = math.pi * position
            value = math.sin(2.0 * cutoff * angle) / angle
        # Blackman window, exact coefficients.
        ratio = index / (taps - 1)
        window = (0.42
                  - 0.5 * math.cos(2.0 * math.pi * ratio)
                  + 0.08 * math.cos(4.0 * math.pi * ratio))
        coefficients[index] = value * window
    return coefficients * float(up)


def resample_to_16k(samples, source_rate: int) -> np.ndarray:
    """Convert float samples at `source_rate` to 16 kHz using STUDY_PCM16K_v1."""
    data = np.asarray(samples, dtype=np.float64).reshape(-1)
    if source_rate == TARGET_SAMPLE_RATE:
        # Identity rule: never filter audio that is already on contract.
        return data.copy()
    if source_rate <= 0:
        raise ValueError(f"invalid source rate {source_rate}")

    divisor = gcd(TARGET_SAMPLE_RATE, int(source_rate))
    up = TARGET_SAMPLE_RATE // divisor
    down = int(source_rate) // divisor
    coefficients = design_filter(up, down)
    half = (len(coefficients) - 1) // 2

    n_in = len(data)
    if n_in == 0:
        return np.zeros(0, dtype=np.float64)
    n_out = int(math.ceil(n_in * up / down))
    output = np.zeros(n_out, dtype=np.float64)

    for n in range(n_out):
        centre = n * down + half
        # Only source samples whose upsampled position carries a tap matter.
        first = int(math.ceil((centre - (len(coefficients) - 1)) / up))
        last = centre // up
        total = 0.0
        for j in range(first, last + 1):
            tap = centre - j * up
            if tap < 0 or tap >= len(coefficients):
                continue
            source_index = min(max(j, 0), n_in - 1)   # constant edge extension
            total += data[source_index] * coefficients[tap]
        output[n] = total
    return output


def to_pcm16(samples) -> np.ndarray:
    """Clamp to [-1, 1] and quantise to signed 16-bit, round-half-away-from-zero."""
    data = np.asarray(samples, dtype=np.float64).reshape(-1)
    clipped = np.clip(data, -1.0, 1.0)
    scaled = clipped * PCM_FULL_SCALE
    rounded = np.where(scaled >= 0, np.floor(scaled + 0.5), np.ceil(scaled - 0.5))
    return rounded.astype(np.int16)


def encode_wav(pcm16, sample_rate: int = TARGET_SAMPLE_RATE) -> bytes:
    """Minimal canonical 16-bit mono WAV, byte-for-byte reproducible."""
    data = np.asarray(pcm16, dtype=np.int16).reshape(-1)
    payload = data.tobytes()
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(payload), b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b"data", len(payload))
    return header + payload


def build_study_wav(samples, source_rate: int) -> tuple[bytes, dict]:
    """The complete study conversion, with the metadata the contract requires."""
    converted = resample_to_16k(samples, source_rate)
    pcm = to_pcm16(converted)
    blob = encode_wav(pcm)
    return blob, {
        "pcm_spec_version": STUDY_PCM_SPEC_VERSION,
        "capture_sample_rate": int(source_rate),
        "output_sample_rate": TARGET_SAMPLE_RATE,
        "conversion": ("identity" if source_rate == TARGET_SAMPLE_RATE
                       else "blackman_sinc_polyphase"),
        "input_frames": int(len(np.asarray(samples).reshape(-1))),
        "output_frames": int(len(pcm)),
        "input_duration_ms": len(np.asarray(samples).reshape(-1)) / source_rate * 1000.0,
        "output_duration_ms": len(pcm) / TARGET_SAMPLE_RATE * 1000.0,
    }


def decode_wav(blob: bytes) -> tuple[np.ndarray, int]:
    """Read back a study WAV as float64 in [-1, 1]."""
    import soundfile as sf

    data, rate = sf.read(io.BytesIO(blob), dtype="float64")
    return np.asarray(data, dtype=np.float64).reshape(-1), int(rate)
