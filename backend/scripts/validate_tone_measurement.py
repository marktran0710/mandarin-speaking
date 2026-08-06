"""Check that the tone measurement itself works, using native speakers.

Native speakers of the OMPAL corpus pronounce correctly by definition, so
their measured pitch shapes are ground truth for the *measurement* -- entirely
independent of any learner, any label, and any model. If a native speaker's
tone 2 does not measure as a rise, the fault is ours, and no amount of
modelling downstream can recover from it.

This check is what exposed the fault that three rounds of modelling work had
been building on top of: tone 2 measured +0.11 semitones, statistically
indistinguishable from level tone 1 at +0.02, when a rise should be roughly
+3 to +5 semitones.

Run it after any change to pitch extraction, alignment, or feature windows:

    python -m scripts.validate_tone_measurement
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarking.ompal_corpus import load_utterances
from tone_scoring.alignment import get_aligner
from tone_scoring.features import SEMITONES_PER_LOG

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "private-data" / "ompal"

# What each tone must look like for the measurement to be trustworthy.
EXPECTATION = {
    1: "~0 (level)",
    2: "clearly positive (rise)",
    3: "dip then rise",
    4: "clearly negative (fall)",
}
# Tone 2 must out-rise tone 1 by at least this much for the measurement to be
# considered working. Well below a citation-form rise (+3 to +5 st), because
# connected speech reduces tone 2 -- but far above the +0.09 st that exposed
# the fault.
MIN_T2_T1_SEPARATION = 1.0


def _slope_semitones(frames) -> float | None:
    """Mean-of-first-quarter to mean-of-last-quarter, in semitones."""
    if len(frames) < 4:
        return None
    logs = np.log(np.asarray([f for _, f in frames], dtype=float))
    quarter = max(1, len(logs) // 4)
    start = float(np.mean(logs[:quarter]))
    end = float(np.mean(logs[-quarter:]))
    return (end - start) * SEMITONES_PER_LOG


def _dip_semitones(frames) -> float | None:
    if len(frames) < 4:
        return None
    logs = np.log(np.asarray([f for _, f in frames], dtype=float))
    quarter = max(1, len(logs) // 4)
    start = float(np.mean(logs[:quarter]))
    return (start - float(logs.min())) * SEMITONES_PER_LOG


def measure(aligner_name: str = "energy") -> Dict[int, Dict[str, float]]:
    from praat_analyzer import (
        _intensity_contour_from_sound,
        _load_sound,
        _pitch_contour_from_sound,
    )

    aligner = get_aligner(aligner_name)
    natives = [u for u in load_utterances(CORPUS_ROOT) if u.is_native]
    slopes: Dict[int, List[float]] = {tone: [] for tone in (1, 2, 3, 4)}
    dips: Dict[int, List[float]] = {tone: [] for tone in (1, 2, 3, 4)}
    frames_per_syllable: List[float] = []

    for utterance in natives:
        try:
            sound = _load_sound(str(utterance.wav_path))
            pitch_contour = _pitch_contour_from_sound(sound)
            intensity = _intensity_contour_from_sound(sound)
        except Exception:
            continue
        if len(pitch_contour) < 2:
            continue

        characters = "".join(word.text for word in utterance.words)
        spans = aligner.align(pitch_contour, len(characters), intensity)
        if len(spans) != len(characters):
            continue
        frames_per_syllable.append(len(pitch_contour) / max(len(characters), 1))

        position = 0
        for word in utterance.words:
            for offset, span in enumerate(spans[position : position + len(word.text)]):
                if offset >= len(word.expected_tones):
                    continue
                tone = word.expected_tones[offset]
                if tone not in (1, 2, 3, 4):
                    continue
                frames = [(t, f) for t, f in span.frames(pitch_contour) if f > 0]
                slope = _slope_semitones(frames)
                dip = _dip_semitones(frames)
                if slope is not None:
                    slopes[tone].append(slope)
                if dip is not None:
                    dips[tone].append(dip)
            position += len(word.text)

    return {
        tone: {
            "n": len(slopes[tone]),
            "slope": float(np.mean(slopes[tone])) if slopes[tone] else float("nan"),
            "dip": float(np.mean(dips[tone])) if dips[tone] else float("nan"),
        }
        for tone in (1, 2, 3, 4)
    }, (float(np.mean(frames_per_syllable)) if frames_per_syllable else 0.0)


def main() -> int:
    warnings.filterwarnings("ignore")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligner", default="energy")
    args = parser.parse_args()

    table, density = measure(args.aligner)

    print(f"NATIVE-SPEAKER TONE MEASUREMENT (aligner={args.aligner})")
    print(f"voiced pitch frames per syllable: {density:.1f}")
    print()
    print(f"{'tone':<6}{'n':>6}{'mean slope':>13}{'mean dip':>11}   expected")
    print("-" * 64)
    for tone in (1, 2, 3, 4):
        row = table[tone]
        print(
            f"T{tone:<5}{row['n']:>6}{row['slope']:>+11.2f} st"
            f"{row['dip']:>+9.2f} st   {EXPECTATION[tone]}"
        )

    separation = table[2]["slope"] - table[1]["slope"]
    print()
    print(f"T2 - T1 separation: {separation:+.2f} st  (need >= {MIN_T2_T1_SEPARATION:+.2f})")

    if not np.isfinite(separation) or separation < MIN_T2_T1_SEPARATION:
        print(
            "\nFAIL: a rising tone does not measure as a rise on speakers who "
            "produce it correctly.\nThe measurement is not usable, and no "
            "downstream scoring change can compensate."
        )
        return 1
    print("\nPASS: tone 2 measures as a rise, separated from level tone 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
