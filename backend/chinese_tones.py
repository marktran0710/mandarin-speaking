import numpy as np
from typing import List, Tuple, Dict
from scipy.interpolate import interp1d
from scipy.spatial.distance import euclidean


# Reference tone patterns (normalized pitch contours for each Mandarin tone)
TONE_REFERENCES = {
    1: {  # High level tone 妈 (mā)
        "name": "High Level",
        "character": "妈",
        "pinyin": "mā",
        "description": "High and flat",
        "pitch_pattern": [0.8, 0.8, 0.8, 0.8, 0.8],  # Normalized 0-1
        "frequency_range": (200, 300),
        "expected_mean": 250,
    },
    2: {  # Rising tone 麻 (má)
        "name": "Rising",
        "character": "麻",
        "pinyin": "má",
        "description": "Rising from mid to high",
        "pitch_pattern": [0.5, 0.6, 0.7, 0.8, 0.85],
        "frequency_range": (200, 300),
        "expected_mean": 240,
    },
    3: {  # Falling-rising tone 马 (mǎ)
        "name": "Falling-Rising",
        "character": "马",
        "pinyin": "mǎ",
        "description": "Falls then rises (valley shape)",
        "pitch_pattern": [0.7, 0.5, 0.3, 0.5, 0.7],
        "frequency_range": (100, 250),
        "expected_mean": 200,
    },
    4: {  # Falling tone 骂 (mà)
        "name": "Falling",
        "character": "骂",
        "pinyin": "mà",
        "description": "High to low falling sharply",
        "pitch_pattern": [0.9, 0.75, 0.6, 0.4, 0.2],
        "frequency_range": (100, 300),
        "expected_mean": 200,
    },
}


def get_reference_tone_pattern(tone_number: int, num_points: int = 100) -> Dict:
    """
    Get reference pitch contour for a specific Mandarin tone.
    Returns normalized pattern interpolated to num_points.
    """
    if tone_number not in TONE_REFERENCES:
        return None

    ref = TONE_REFERENCES[tone_number]

    # Interpolate pattern to desired number of points
    x = np.linspace(0, 1, len(ref["pitch_pattern"]))
    x_new = np.linspace(0, 1, num_points)

    f = interp1d(x, ref["pitch_pattern"], kind="cubic", fill_value="extrapolate")
    interpolated = np.clip(f(x_new), 0, 1)

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
    """
    Normalize pitch contour to 0-1 range for comparison.
    Interpolates to standard number of points.
    """
    if not pitch_contour or len(pitch_contour) < 2:
        return np.array([])

    times = np.array([p[0] for p in pitch_contour])
    frequencies = np.array([p[1] for p in pitch_contour])

    # Normalize time to 0-1
    times_norm = (times - times[0]) / (times[-1] - times[0])

    # Normalize frequency to 0-1
    min_freq = np.min(frequencies)
    max_freq = np.max(frequencies)
    freq_range = max_freq - min_freq

    if freq_range == 0:
        frequencies_norm = np.ones_like(frequencies) * 0.5
    else:
        frequencies_norm = (frequencies - min_freq) / freq_range

    # Interpolate to standard 100 points
    x_new = np.linspace(0, 1, 100)
    f = interp1d(times_norm, frequencies_norm, kind="cubic", fill_value="extrapolate")
    interpolated = np.clip(f(x_new), 0, 1)

    return interpolated


def calculate_tone_accuracy(
    pitch_contour: List[Tuple[float, float]], tone_number: int
) -> float:
    """
    Calculate how well the pitch contour matches a reference tone.
    Returns accuracy score (0-100).
    """
    if not pitch_contour:
        return 0.0

    # Get normalized user pitch
    user_pitch = normalize_pitch_contour(pitch_contour)

    if len(user_pitch) == 0:
        return 0.0

    # Get reference tone
    ref = get_reference_tone_pattern(tone_number, num_points=len(user_pitch))
    ref_pitch = np.array(ref["pitch_pattern"])

    # Calculate similarity using DTW (Dynamic Time Warping) alternative
    # Simple approach: correlation-based similarity
    if len(user_pitch) != len(ref_pitch):
        # Interpolate to same length
        x = np.linspace(0, 1, len(user_pitch))
        x_ref = np.linspace(0, 1, len(ref_pitch))
        f = interp1d(x_ref, ref_pitch, kind="linear", fill_value="extrapolate")
        ref_pitch = np.clip(f(x), 0, 1)

    # Correlation similarity
    correlation = np.corrcoef(user_pitch, ref_pitch)[0, 1]
    if np.isnan(correlation):
        correlation = 0

    # Euclidean distance similarity
    distance = euclidean(user_pitch, ref_pitch)
    distance_score = max(0, 100 - (distance * 50))  # Normalize distance to 0-100

    # Combine metrics (correlation 60%, distance 40%)
    accuracy = correlation * 60 + (distance_score / 100) * 40
    accuracy = max(0, min(100, accuracy * 100))  # Convert to 0-100 range

    return float(accuracy)


def detect_tone(pitch_contour: List[Tuple[float, float]]) -> Dict:
    """
    Detect which Mandarin tone was spoken based on pitch contour.
    Returns dict with detected_tone, confidence, and analysis.
    """
    if not pitch_contour or len(pitch_contour) < 2:
        return {
            "detected_tone": 0,
            "confidence": 0.0,
            "scores": {1: 0, 2: 0, 3: 0, 4: 0},
            "feedback": "Unable to detect tone. Audio too short or unclear."
        }

    # Calculate accuracy for each tone
    scores = {}
    for tone_num in [1, 2, 3, 4]:
        accuracy = calculate_tone_accuracy(pitch_contour, tone_num)
        scores[tone_num] = accuracy

    # Find best match
    detected_tone = max(scores, key=scores.get)
    confidence = scores[detected_tone] / 100.0

    # Generate feedback
    ref = TONE_REFERENCES[detected_tone]
    feedback = f"Detected: {ref['name']} tone ({ref['character']}, {ref['pinyin']})"

    if confidence > 0.85:
        feedback += " - Excellent!"
    elif confidence > 0.70:
        feedback += " - Good"
    elif confidence > 0.55:
        feedback += " - Acceptable"
    else:
        feedback += " - Could be clearer"

    return {
        "detected_tone": detected_tone,
        "confidence": float(confidence),
        "scores": {k: float(v) for k, v in scores.items()},
        "feedback": feedback,
        "reference": ref
    }


def get_tone_feedback(
    detected_tone: int, accuracy: float, pitch_contour: List[Tuple[float, float]]
) -> str:
    """
    Generate helpful feedback based on detected tone and accuracy.
    """
    if not pitch_contour:
        return "No audio detected."

    ref = TONE_REFERENCES[detected_tone]
    feedback_parts = []

    if accuracy > 85:
        feedback_parts.append(f"🌟 Excellent {ref['name']} tone!")
    elif accuracy > 70:
        feedback_parts.append(f"👍 Good {ref['name']} tone")
    elif accuracy > 55:
        feedback_parts.append(f"📈 {ref['name']} tone is acceptable")
    else:
        feedback_parts.append(f"⚠️ {ref['name']} tone needs work")

    # Extract pitch statistics
    frequencies = np.array([p[1] for p in pitch_contour])
    mean_freq = np.mean(frequencies)
    freq_range = TONE_REFERENCES[detected_tone]["frequency_range"]

    # Frequency feedback
    if freq_range[0] <= mean_freq <= freq_range[1]:
        feedback_parts.append(f"Pitch range is good ({mean_freq:.0f} Hz)")
    elif mean_freq < freq_range[0]:
        feedback_parts.append(f"Pitch is too low. Target: {freq_range[0]}-{freq_range[1]} Hz")
    else:
        feedback_parts.append(f"Pitch is too high. Target: {freq_range[0]}-{freq_range[1]} Hz")

    # Pattern-specific feedback
    if detected_tone == 1:
        variance = np.std(np.diff(frequencies))
        if variance < 20:
            feedback_parts.append("Keep the pitch steady!")
        else:
            feedback_parts.append("Tone 1 should be flatter - avoid pitch variation")

    elif detected_tone == 2:
        if frequencies[-1] > frequencies[0]:
            feedback_parts.append("Good upward slope!")
        else:
            feedback_parts.append("Tone 2 should rise - start lower and rise to higher pitch")

    elif detected_tone == 3:
        if len(frequencies) >= 3:
            mid_idx = len(frequencies) // 2
            if frequencies[mid_idx] < frequencies[0] and frequencies[mid_idx] < frequencies[-1]:
                feedback_parts.append("Good valley pattern!")
            else:
                feedback_parts.append("Tone 3 needs a dip in the middle")

    elif detected_tone == 4:
        if frequencies[-1] < frequencies[0]:
            feedback_parts.append("Good downward slope!")
        else:
            feedback_parts.append("Tone 4 should fall - start high and drop to lower pitch")

    return " ".join(feedback_parts)


def generate_comprehensive_feedback(
    detected_tone: int,
    tone_accuracy: float,
    speech_rate: float,
    fluency: float,
    pitch_contour: List[Tuple[float, float]]
) -> str:
    """
    Generate comprehensive feedback combining all metrics.
    """
    tone_feedback = get_tone_feedback(detected_tone, tone_accuracy, pitch_contour)

    feedback_parts = [tone_feedback]

    # Speech rate feedback
    if speech_rate > 0:
        if 3.5 <= speech_rate <= 5.5:
            feedback_parts.append(f"Speech rate is good ({speech_rate:.1f} syllables/sec)")
        elif speech_rate < 3.5:
            feedback_parts.append(f"Speak faster ({speech_rate:.1f} vs 4-5 syllables/sec)")
        else:
            feedback_parts.append(f"Slow down ({speech_rate:.1f} vs 4-5 syllables/sec)")

    # Fluency feedback
    if fluency > 80:
        feedback_parts.append("Fluency is excellent!")
    elif fluency > 60:
        feedback_parts.append("Work on smoother pitch transitions")
    else:
        feedback_parts.append("Practice for better fluency")

    return " | ".join(feedback_parts)
