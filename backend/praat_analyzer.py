"""
Praat acoustic analysis helpers powered by Parselmouth.

Parselmouth embeds Praat's analysis routines in Python, so the API can extract
pitch and formant features without shelling out to the Praat desktop app.
"""
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
    sound = _load_sound(audio_path)
    duration = max(sound.get_total_duration(), 0.01)

    if transcription:
        syllable_count = sum(
            1 for char in transcription if "\u4e00" <= char <= "\u9fff"
        )
        if syllable_count > 0:
            return float(syllable_count / duration)

    voiced_points = extract_pitch(audio_path, time_step=0.02)
    estimated_syllables = max(1, round(len(voiced_points) / 9))
    return float(estimated_syllables / duration)


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
