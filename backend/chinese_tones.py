from typing import Dict, List, Tuple

import numpy as np
from scipy.interpolate import interp1d
from scipy.spatial.distance import euclidean


TONE_REFERENCES = {
    1: {
        "name": "High Level",
        "character": "媽",
        "pinyin": "ma1",
        "description": "High and flat",
        "pitch_pattern": [0.8, 0.8, 0.8, 0.8, 0.8],
        "frequency_range": (200, 300),
        "expected_mean": 250,
    },
    2: {
        "name": "Rising",
        "character": "麻",
        "pinyin": "ma2",
        "description": "Rising from mid to high",
        "pitch_pattern": [0.5, 0.6, 0.7, 0.8, 0.85],
        "frequency_range": (200, 300),
        "expected_mean": 240,
    },
    3: {
        "name": "Falling-Rising",
        "character": "馬",
        "pinyin": "ma3",
        "description": "Falls then rises",
        "pitch_pattern": [0.7, 0.5, 0.3, 0.5, 0.7],
        "frequency_range": (100, 250),
        "expected_mean": 200,
    },
    4: {
        "name": "Falling",
        "character": "罵",
        "pinyin": "ma4",
        "description": "High to low falling sharply",
        "pitch_pattern": [0.9, 0.75, 0.6, 0.4, 0.2],
        "frequency_range": (100, 300),
        "expected_mean": 200,
    },
}


def get_reference_tone_pattern(tone_number: int, num_points: int = 100) -> Dict:
    if tone_number not in TONE_REFERENCES:
        return None

    ref = TONE_REFERENCES[tone_number]
    x = np.linspace(0, 1, len(ref["pitch_pattern"]))
    x_new = np.linspace(0, 1, num_points)
    interpolator = interp1d(x, ref["pitch_pattern"], kind="cubic", fill_value="extrapolate")
    interpolated = np.clip(interpolator(x_new), 0, 1)

    return {
        "tone": tone_number,
        "name": ref["name"],
        "character": ref["character"],
        "pinyin": ref["pinyin"],
        "description": ref["description"],
        "pitch_pattern": interpolated.tolist(),
        "frequency_range": ref["frequency_range"],
        "expected_mean": ref["expected_mean"],
    }


def normalize_pitch_contour(pitch_contour: List[Tuple[float, float]]) -> np.ndarray:
    if not pitch_contour or len(pitch_contour) < 2:
        return np.array([])

    times = np.array([point[0] for point in pitch_contour])
    frequencies = np.array([point[1] for point in pitch_contour])

    duration = times[-1] - times[0]
    if duration <= 0:
        return np.array([])

    times_norm = (times - times[0]) / duration
    freq_range = np.max(frequencies) - np.min(frequencies)
    if freq_range == 0:
        frequencies_norm = np.ones_like(frequencies) * 0.5
    else:
        frequencies_norm = (frequencies - np.min(frequencies)) / freq_range

    x_new = np.linspace(0, 1, 100)
    interpolator = interp1d(times_norm, frequencies_norm, kind="linear", fill_value="extrapolate")
    return np.clip(interpolator(x_new), 0, 1)


def calculate_tone_accuracy(
    pitch_contour: List[Tuple[float, float]], tone_number: int
) -> float:
    user_pitch = normalize_pitch_contour(pitch_contour)
    if len(user_pitch) == 0:
        return 0.0

    ref = get_reference_tone_pattern(tone_number, num_points=len(user_pitch))
    ref_pitch = np.array(ref["pitch_pattern"])

    correlation = np.corrcoef(user_pitch, ref_pitch)[0, 1]
    if np.isnan(correlation):
        correlation = 0.0

    distance = euclidean(user_pitch, ref_pitch)
    distance_score = max(0.0, 1.0 - distance / len(user_pitch))
    correlation_score = (correlation + 1.0) / 2.0
    accuracy = (correlation_score * 0.65 + distance_score * 0.35) * 100.0
    return float(max(0.0, min(100.0, accuracy)))


def detect_tone(pitch_contour: List[Tuple[float, float]]) -> Dict:
    if not pitch_contour or len(pitch_contour) < 2:
        return {
            "detected_tone": 0,
            "confidence": 0.0,
            "scores": {1: 0, 2: 0, 3: 0, 4: 0},
            "feedback": "Unable to detect tone. Audio too short or unclear.",
        }

    scores = {
        tone_num: calculate_tone_accuracy(pitch_contour, tone_num)
        for tone_num in [1, 2, 3, 4]
    }
    detected_tone = max(scores, key=scores.get)
    confidence = scores[detected_tone] / 100.0
    ref = TONE_REFERENCES[detected_tone]

    return {
        "detected_tone": detected_tone,
        "confidence": float(confidence),
        "scores": {key: float(value) for key, value in scores.items()},
        "feedback": f"Detected: {ref['name']} tone ({ref['character']}, {ref['pinyin']})",
        "reference": ref,
    }


def get_tone_feedback(
    detected_tone: int, accuracy: float, pitch_contour: List[Tuple[float, float]]
) -> str:
    if not pitch_contour or detected_tone not in TONE_REFERENCES:
        return "No clear tone detected yet. Try recording a slightly longer phrase."

    ref = TONE_REFERENCES[detected_tone]
    feedback_parts = []

    if accuracy > 85:
        feedback_parts.append(f"Excellent {ref['name']} tone.")
    elif accuracy > 70:
        feedback_parts.append(f"Good {ref['name']} tone.")
    elif accuracy > 55:
        feedback_parts.append(f"The {ref['name']} tone is recognizable.")
    else:
        feedback_parts.append(f"The {ref['name']} tone needs more contrast.")

    frequencies = np.array([point[1] for point in pitch_contour])
    mean_freq = np.mean(frequencies)
    freq_range = TONE_REFERENCES[detected_tone]["frequency_range"]

    if freq_range[0] <= mean_freq <= freq_range[1]:
        feedback_parts.append(f"Pitch range is on target at about {mean_freq:.0f} Hz.")
    elif mean_freq < freq_range[0]:
        feedback_parts.append(f"Pitch is low; aim closer to {freq_range[0]}-{freq_range[1]} Hz.")
    else:
        feedback_parts.append(f"Pitch is high; aim closer to {freq_range[0]}-{freq_range[1]} Hz.")

    if detected_tone == 1:
        if np.std(np.diff(frequencies)) < 20:
            feedback_parts.append("Keep that steady, level pitch.")
        else:
            feedback_parts.append("Tone 1 should stay flatter.")
    elif detected_tone == 2:
        feedback_parts.append(
            "Good upward slope." if frequencies[-1] > frequencies[0]
            else "Tone 2 should rise from lower to higher pitch."
        )
    elif detected_tone == 3 and len(frequencies) >= 3:
        mid_idx = len(frequencies) // 2
        feedback_parts.append(
            "Good dip in the middle."
            if frequencies[mid_idx] < frequencies[0] and frequencies[mid_idx] < frequencies[-1]
            else "Tone 3 needs a clearer dip in the middle."
        )
    elif detected_tone == 4:
        feedback_parts.append(
            "Good falling slope." if frequencies[-1] < frequencies[0]
            else "Tone 4 should fall from high to low."
        )

    return " ".join(feedback_parts)


def generate_comprehensive_feedback(
    detected_tone: int,
    tone_accuracy: float,
    speech_rate: float,
    fluency: float,
    pitch_contour: List[Tuple[float, float]],
) -> str:
    feedback_parts = [
        get_tone_feedback(detected_tone, tone_accuracy, pitch_contour)
    ]

    if speech_rate > 0:
        if 3.5 <= speech_rate <= 5.5:
            feedback_parts.append(f"Speech rate is comfortable at {speech_rate:.1f} syllables/sec.")
        elif speech_rate < 3.5:
            feedback_parts.append(f"Try a little faster; current rate is {speech_rate:.1f} syllables/sec.")
        else:
            feedback_parts.append(f"Slow down slightly; current rate is {speech_rate:.1f} syllables/sec.")

    if fluency > 80:
        feedback_parts.append("Fluency is smooth.")
    elif fluency > 60:
        feedback_parts.append("Work on smoother pitch transitions.")
    else:
        feedback_parts.append("Try one shorter phrase and keep the tone movement clear.")

    return " ".join(feedback_parts)
