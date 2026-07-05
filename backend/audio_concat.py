"""
Story-level audio concatenation.

Joins the per-scene WAV recordings of a story submission into a single WAV
file, in scene order, with a short silence gap between scenes. Every scene
clip is already canonical 16-bit PCM WAV (guaranteed client-side before
upload), so this only needs stdlib `wave` plus numpy/scipy — both already
hard dependencies of the backend — no ffmpeg/librosa/soundfile required.
"""
import logging
import os
import wave
from typing import List, Optional

import numpy as np
from scipy.signal import resample

logger = logging.getLogger(__name__)


def _resolve_upload_path(url: str, upload_dir: str) -> Optional[str]:
    if not url or not url.startswith("/uploads/"):
        return None
    relative_path = url.removeprefix("/uploads/").replace("/", os.sep)
    path = os.path.abspath(os.path.join(upload_dir, relative_path))
    upload_root = os.path.abspath(upload_dir)
    if not path.startswith(upload_root) or not os.path.exists(path):
        return None
    return path


def _read_wav_as_mono_pcm16(path: str, target_sample_rate: int) -> Optional[np.ndarray]:
    try:
        with wave.open(path, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
    except (wave.Error, EOFError, OSError) as exc:
        logger.warning("Could not read WAV %s for story concatenation: %s", path, exc)
        return None

    if sample_width != 2:
        logger.warning("Skipping non-16-bit WAV %s (sampwidth=%s)", path, sample_width)
        return None

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    if frame_rate != target_sample_rate and samples.size > 0:
        new_length = max(1, round(samples.size * target_sample_rate / frame_rate))
        samples = resample(samples, new_length)

    return np.clip(samples, -32768, 32767).astype(np.int16)


def concatenate_scene_audio(
    scene_audio_urls: List[str],
    upload_dir: str,
    output_path: str,
    target_sample_rate: int = 16000,
    gap_ms: int = 400,
) -> bool:
    """Concatenate scene WAV clips (already ordered by caller) into one WAV.

    Returns True and writes `output_path` if at least one scene clip could be
    read; returns False (and writes nothing) if none were usable.
    """
    gap_samples = int(target_sample_rate * gap_ms / 1000)
    silence = np.zeros(gap_samples, dtype=np.int16)

    chunks: List[np.ndarray] = []
    for url in scene_audio_urls:
        path = _resolve_upload_path(url, upload_dir)
        if not path:
            logger.warning("Skipping missing/unresolvable scene audio URL: %s", url)
            continue
        samples = _read_wav_as_mono_pcm16(path, target_sample_rate)
        if samples is None or samples.size == 0:
            continue
        if chunks:
            chunks.append(silence)
        chunks.append(samples)

    if not chunks:
        return False

    combined = np.concatenate(chunks)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with wave.open(output_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(target_sample_rate)
        wf.writeframes(combined.tobytes())

    return True
