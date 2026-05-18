"""
Mock Praat analyzer for demonstration.
Replace this with the real praat_analyzer.py once Praat is properly installed.
"""
import numpy as np
from typing import List, Tuple, Dict


def extract_pitch(audio_path: str, time_step: float = 0.01) -> List[Tuple[float, float]]:
    """
    Mock pitch extraction - returns simulated pitch contour.
    """
    # Simulate a pitch contour (rising tone in this example)
    num_points = 150
    times = np.linspace(0, 1.5, num_points)

    # Simulate tone 2 (rising) pitch contour
    frequencies = 150 + 100 * (times ** 0.8)  # Rising curve
    frequencies = frequencies.tolist()

    return [(float(t), float(f)) for t, f in zip(times, frequencies)]


def extract_formants(audio_path: str, max_formant: float = 5000, num_formants: int = 3) -> Dict[str, float]:
    """
    Mock formant extraction.
    """
    return {
        "F1": 720.0,
        "F2": 1220.0,
        "F3": 2600.0
    }


def calculate_speech_rate(audio_path: str, transcription: str = "") -> float:
    """
    Mock speech rate calculation.
    """
    # Simulate 4.8 syllables per second (optimal range)
    return 4.8


def analyze_fluency(pitch_contour: List[Tuple[float, float]], speech_rate: float) -> float:
    """
    Mock fluency analysis.
    """
    # Simulate 85% fluency
    return 85.0


def get_pitch_statistics(pitch_contour: List[Tuple[float, float]]) -> Dict[str, float]:
    """
    Mock pitch statistics.
    """
    if not pitch_contour:
        return {
            "mean_frequency": 0.0,
            "min_frequency": 0.0,
            "max_frequency": 0.0,
            "frequency_range": 0.0
        }

    frequencies = np.array([p[1] for p in pitch_contour])

    return {
        "mean_frequency": float(np.mean(frequencies)),
        "min_frequency": float(np.min(frequencies)),
        "max_frequency": float(np.max(frequencies)),
        "frequency_range": float(np.max(frequencies) - np.min(frequencies))
    }

