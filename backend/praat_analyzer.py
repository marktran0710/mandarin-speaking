"""
Praat acoustic analysis helpers powered by Parselmouth.

Parselmouth embeds Praat's analysis routines in Python, so the API can extract
pitch and formant features without shelling out to the Praat desktop app.
"""
import re
import wave
from typing import Dict, List, Tuple

import numpy as np

try:
    import parselmouth
except ImportError as exc:
    parselmouth = None
    PARSELMOUTH_IMPORT_ERROR = exc
else:
    PARSELMOUTH_IMPORT_ERROR = None


def _load_sound(audio_path: str):
    if parselmouth is None:
        raise RuntimeError(
            "Praat analysis requires the praat-parselmouth package. "
            "Install backend requirements with: pip install -r backend/requirements.txt"
        ) from PARSELMOUTH_IMPORT_ERROR

    try:
        return parselmouth.Sound(audio_path)
    except Exception as exc:
        raise RuntimeError(
            "Praat could not read this audio file. Send WAV audio for analysis."
        ) from exc


def extract_pitch(
    audio_path: str,
    time_step: float = 0.01,
    pitch_floor: float = 75,
    pitch_ceiling: float = 500,
) -> List[Tuple[float, float]]:
    """Extract voiced pitch samples as (time_seconds, frequency_hz)."""
    if parselmouth is None:
        return _extract_pitch_fallback(audio_path, time_step, pitch_floor, pitch_ceiling)

    sound = _load_sound(audio_path)
    pitch = sound.to_pitch(
        time_step=time_step,
        pitch_floor=pitch_floor,
        pitch_ceiling=pitch_ceiling,
    )

    contour: List[Tuple[float, float]] = []
    for index, frequency in enumerate(pitch.selected_array["frequency"]):
        if frequency > 0:
            time = pitch.xs()[index]
            contour.append((float(time), float(frequency)))

    return contour


def extract_formants(
    audio_path: str,
    max_formant: float = 5500,
    num_formants: int = 5,
) -> Dict[str, float]:
    """Return median F1-F3 values across voiced frames."""
    if parselmouth is None:
        return {"F1": 0.0, "F2": 0.0, "F3": 0.0}

    sound = _load_sound(audio_path)
    formant = sound.to_formant_burg(
        time_step=0.01,
        max_number_of_formants=num_formants,
        maximum_formant=max_formant,
    )

    values: Dict[str, List[float]] = {"F1": [], "F2": [], "F3": []}
    for time in np.linspace(sound.xmin, sound.xmax, 120):
        for formant_number, key in ((1, "F1"), (2, "F2"), (3, "F3")):
            value = formant.get_value_at_time(formant_number, float(time))
            if value and not np.isnan(value):
                values[key].append(float(value))

    return {
        key: float(np.median(items)) if items else 0.0
        for key, items in values.items()
    }


def calculate_speech_rate(audio_path: str, transcription: str = "") -> float:
    """
    Estimate syllables per second.

    If a transcription is available, Chinese characters are a good proxy for
    syllables. Otherwise, estimate from voiced pitch frames.
    """
    duration = _audio_duration(audio_path)

    if transcription:
        syllable_count = sum(
            1 for char in transcription if "\u4e00" <= char <= "\u9fff"
        )
        if syllable_count > 0:
            return float(syllable_count / duration)

    voiced_points = extract_pitch(audio_path, time_step=0.02)
    estimated_syllables = max(1, round(len(voiced_points) / 9))
    return float(estimated_syllables / duration)


def _audio_duration(audio_path: str) -> float:
    if parselmouth is not None:
        sound = _load_sound(audio_path)
        return max(sound.get_total_duration(), 0.01)

    try:
        with wave.open(audio_path, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            return max(frames / float(rate), 0.01)
    except Exception:
        return 1.0


def _extract_pitch_fallback(
    audio_path: str,
    time_step: float,
    pitch_floor: float,
    pitch_ceiling: float,
) -> List[Tuple[float, float]]:
    """
    Lightweight fallback for local development when Parselmouth is unavailable.

    This estimates voiced pitch from zero crossings in short WAV windows. It is
    not a replacement for Praat, but it keeps the speech-analysis API usable
    until the Docker/Praat backend is available again.
    """
    try:
        with wave.open(audio_path, "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            frames = wav_file.readframes(wav_file.getnframes())
    except Exception as exc:
        raise RuntimeError("Could not read WAV audio for fallback analysis.") from exc

    if sample_width != 2:
        return []

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)

    window_size = max(int(frame_rate * 0.04), 1)
    hop_size = max(int(frame_rate * time_step), 1)
    contour: List[Tuple[float, float]] = []

    for start in range(0, max(len(audio) - window_size, 0), hop_size):
        window = audio[start : start + window_size].astype(float)
        if window.size < 4 or float(np.sqrt(np.mean(window**2))) < 120:
            continue

        centered = window - float(np.mean(window))
        crossings = np.where(np.diff(np.signbit(centered)))[0]
        frequency = (len(crossings) * frame_rate) / (2.0 * window.size)
        if pitch_floor <= frequency <= pitch_ceiling:
            contour.append((float(start / frame_rate), float(frequency)))

    return contour


def analyze_fluency(
    pitch_contour: List[Tuple[float, float]],
    speech_rate: float,
) -> float:
    """Score pitch continuity and speaking-rate comfort on a 0-100 scale."""
    if len(pitch_contour) < 3:
        return 0.0

    frequencies = np.array([point[1] for point in pitch_contour])
    times = np.array([point[0] for point in pitch_contour])

    pitch_jumps = np.abs(np.diff(frequencies))
    jump_penalty = min(45.0, float(np.mean(pitch_jumps) / 2.5))

    gaps = np.diff(times)
    pause_penalty = min(35.0, float(np.sum(gaps > 0.18) * 7))

    rate_penalty = 0.0
    if speech_rate < 2.5:
        rate_penalty = min(20.0, (2.5 - speech_rate) * 8)
    elif speech_rate > 6.5:
        rate_penalty = min(20.0, (speech_rate - 6.5) * 8)

    return float(max(0.0, min(100.0, 100.0 - jump_penalty - pause_penalty - rate_penalty)))


def get_pitch_statistics(
    pitch_contour: List[Tuple[float, float]]
) -> Dict[str, float]:
    """Summarize the extracted pitch contour."""
    if not pitch_contour:
        return {
            "mean_frequency": 0.0,
            "min_frequency": 0.0,
            "max_frequency": 0.0,
            "frequency_range": 0.0,
        }

    frequencies = np.array([point[1] for point in pitch_contour])
    return {
        "mean_frequency": float(np.mean(frequencies)),
        "min_frequency": float(np.min(frequencies)),
        "max_frequency": float(np.max(frequencies)),
        "frequency_range": float(np.max(frequencies) - np.min(frequencies)),
    }


def estimate_word_prosody(
    pitch_contour: List[Tuple[float, float]],
    transcription: str = "",
) -> List[Dict]:
    """
    Estimate per-character/word prosody from the global pitch contour.

    This is a lightweight alignment approximation: Mandarin characters are used
    as syllable-like units, and their time spans are distributed across the
    voiced pitch duration. It is useful for student feedback, but it is not a
    replacement for forced alignment.
    """
    tokens = _prosody_tokens(transcription)
    if not tokens or len(pitch_contour) < 2:
        return []

    start_time = float(pitch_contour[0][0])
    end_time = float(pitch_contour[-1][0])
    duration = max(end_time - start_time, 0.01)
    segment_duration = duration / len(tokens)
    segments: List[Dict] = []

    for index, token in enumerate(tokens):
        segment_start = start_time + index * segment_duration
        segment_end = (
            end_time if index == len(tokens) - 1 else segment_start + segment_duration
        )
        points = [
            (float(time), float(freq))
            for time, freq in pitch_contour
            if segment_start <= float(time) <= segment_end
        ]

        if not points:
            nearest = min(
                pitch_contour,
                key=lambda point: abs(float(point[0]) - segment_start),
            )
            points = [(float(nearest[0]), float(nearest[1]))]

        frequencies = np.array([point[1] for point in points], dtype=float)
        start_pitch = float(frequencies[0])
        end_pitch = float(frequencies[-1])
        mean_pitch = float(np.mean(frequencies))
        pitch_range = float(np.max(frequencies) - np.min(frequencies))
        slope = end_pitch - start_pitch
        contour_shape = _contour_shape(frequencies, slope, pitch_range)

        segments.append(
            {
                "token": token,
                "index": index,
                "start_time": round(segment_start, 3),
                "end_time": round(segment_end, 3),
                "pitch_contour": points,
                "mean_pitch": round(mean_pitch, 2),
                "pitch_range": round(pitch_range, 2),
                "start_pitch": round(start_pitch, 2),
                "end_pitch": round(end_pitch, 2),
                "contour_shape": contour_shape,
                "feedback": _word_prosody_feedback(contour_shape, pitch_range),
            }
        )

    return segments


def _prosody_tokens(transcription: str) -> List[str]:
    text = transcription.strip()
    if not text:
        return []

    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if chinese_chars:
        return chinese_chars[:80]

    return re.findall(r"[A-Za-z0-9']+", text)[:40]


def _contour_shape(frequencies: np.ndarray, slope: float, pitch_range: float) -> str:
    if len(frequencies) >= 3:
        middle = float(frequencies[len(frequencies) // 2])
        if middle < float(frequencies[0]) and middle < float(frequencies[-1]):
            return "dip"

    if pitch_range < 18:
        return "level"
    if slope > 12:
        return "rising"
    if slope < -12:
        return "falling"
    return "variable"


def _word_prosody_feedback(contour_shape: str, pitch_range: float) -> str:
    if contour_shape == "level":
        return "Stable pitch. Good for level or unstressed syllables."
    if contour_shape == "rising":
        return "Pitch rises clearly."
    if contour_shape == "falling":
        return "Pitch falls clearly."
    if contour_shape == "dip":
        return "Pitch dips in the middle."
    if pitch_range > 80:
        return "Large pitch movement; check whether it matches the intended tone."
    return "Some pitch movement is present; try making the tone shape clearer."
