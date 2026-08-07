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
from tone_scoring.features import (
    SEMITONES_PER_LOG,
    declination_slope_from_spans,
    regression_slope,
    trim_consonant_onset,
)

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "private-data" / "ompal"

# What each tone must look like for the measurement to be trustworthy.
EXPECTATION = {
    1: "~0 (level)",
    2: "clearly positive (rise)",
    3: "dip then rise",
    4: "clearly negative (fall)",
}
# Recalibrated 2026-08-06. The original gate required tone 2 to out-rise tone 1
# by 1.0 semitone on average, a number taken from citation-form expectations.
# Measured on correctly-produced tones that bar is actually met in
# utterance-final position (+1.04 st) -- while the measurement remains useless,
# because the pooled standard deviation is 5.57 st. A mean separation five
# times smaller than its own spread does not separate anything, so the old gate
# would have declared success on a broken measurement.
#
# The gate is therefore on *discriminability*, not on mean separation: how well
# the measured slope tells a level tone from a rising one, on speech where both
# were produced correctly. AUC is used because it is scale-free and needs no
# assumption about how large a "real" rise ought to be -- the assumption that
# made the first gate wrong.
#
# 0.70 corresponds to Cohen's d of roughly 0.74. It is a modest bar for
# distinguishing two tone categories on correct speech, and far above the 0.567
# currently measured.
MIN_T1_T2_AUC = 0.70


def _detrended(frames, drift: float, reference: float) -> np.ndarray:
    times = np.asarray([t for t, _ in frames], dtype=float)
    logs = np.log(np.asarray([f for _, f in frames], dtype=float))
    return logs - drift * (times - reference)


def _slope_semitones(frames, drift: float = 0.0, reference: float = 0.0) -> float | None:
    """Mean-of-first-quarter to mean-of-last-quarter, in semitones.

    Declination is removed first, so the gate measures what the model measures.
    """
    if len(frames) < 4:
        return None
    logs = _detrended(frames, drift, reference)
    # Same estimator the features use, or the gate would not be testing them.
    times = [t for t, _ in frames]
    return regression_slope(times, logs) * SEMITONES_PER_LOG


def _dip_semitones(frames, drift: float = 0.0, reference: float = 0.0) -> float | None:
    if len(frames) < 4:
        return None
    logs = _detrended(frames, drift, reference)
    quarter = max(1, len(logs) // 4)
    start = float(np.mean(logs[:quarter]))
    return (start - float(logs.min())) * SEMITONES_PER_LOG


def _auc(positive: List[float], negative: List[float]) -> float:
    """Probability a random tone-2 slope exceeds a random tone-1 slope."""
    merged = sorted([(v, 1) for v in positive] + [(v, 0) for v in negative])
    ranks = [0.0] * len(merged)
    index = 0
    while index < len(merged):
        end = index
        while end < len(merged) and merged[end][0] == merged[index][0]:
            end += 1
        for k in range(index, end):
            ranks[k] = (index + 1 + end) / 2.0
        index = end
    rank_sum = sum(ranks[k] for k in range(len(merged)) if merged[k][1] == 1)
    return (rank_sum - len(positive) * (len(positive) + 1) / 2) / (
        len(positive) * len(negative)
    )


def measure(aligner_name: str = "energy") -> Dict[int, Dict[str, float]]:
    from praat_analyzer import (
        _intensity_contour_from_sound,
        _load_sound,
        _pitch_contour_from_sound,
    )

    aligner = get_aligner(aligner_name)
    # Correctly-produced tones: natives, plus any learner syllable all three
    # raters marked right. Both are ground truth for the measurement, and the
    # learner ones multiply the sample size several-fold.
    natives = list(load_utterances(CORPUS_ROOT))
    slopes: Dict[int, List[float]] = {tone: [] for tone in (1, 2, 3, 4)}
    dips: Dict[int, List[float]] = {tone: [] for tone in (1, 2, 3, 4)}
    by_position: Dict[str, Dict[int, List[float]]] = {
        "non-final": {1: [], 2: []},
        "final": {1: [], 2: []},
    }
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
        drift, reference = declination_slope_from_spans(pitch_contour, spans)

        total = len(characters)
        position = 0
        for word in utterance.words:
            produced_correctly = utterance.is_native or (
                len(word.rater_tone_labels) > 0 and all(word.rater_tone_labels)
            )
            for offset, span in enumerate(spans[position : position + len(word.text)]):
                if offset >= len(word.expected_tones) or not produced_correctly:
                    continue
                tone = word.expected_tones[offset]
                if tone not in (1, 2, 3, 4):
                    continue
                frames = trim_consonant_onset(
                    [(t, f) for t, f in span.frames(pitch_contour) if f > 0]
                )
                slope = _slope_semitones(frames, drift, reference)
                dip = _dip_semitones(frames, drift, reference)
                if slope is not None:
                    slopes[tone].append(slope)
                    if tone in (1, 2):
                        bucket = "final" if position + offset == total - 1 else "non-final"
                        by_position[bucket][tone].append(slope)
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
    }, (float(np.mean(frames_per_syllable)) if frames_per_syllable else 0.0), by_position


def main() -> int:
    warnings.filterwarnings("ignore")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligner", default="energy")
    args = parser.parse_args()

    table, density, by_position = measure(args.aligner)

    print(f"NATIVE-SPEAKER TONE MEASUREMENT (aligner={args.aligner})")
    print("correctly-produced tones only: natives + syllables all 3 raters passed")
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

    # Discriminability, which is what actually matters. A mean separation says
    # nothing when it is far smaller than its own spread.
    print()
    print("Can the measurement tell a level tone from a rising one?")
    print(f"{'position':<12}{'sep':>8}{'pooled sd':>11}{'Cohen d':>9}{'AUC':>8}{'n':>12}")
    print("-" * 60)
    best_auc = 0.0
    for bucket in ("non-final", "final"):
        level = np.asarray(by_position[bucket][1], dtype=float)
        rising = np.asarray(by_position[bucket][2], dtype=float)
        if len(level) < 10 or len(rising) < 10:
            continue
        spread = float(
            np.sqrt(
                (level.var(ddof=1) * (len(level) - 1) + rising.var(ddof=1) * (len(rising) - 1))
                / (len(level) + len(rising) - 2)
            )
        )
        separation = float(rising.mean() - level.mean())
        effect = separation / spread if spread > 0 else 0.0
        auc = _auc(list(rising), list(level))
        best_auc = max(best_auc, auc)
        print(
            f"{bucket:<12}{separation:>+8.2f}{spread:>11.2f}{effect:>9.2f}"
            f"{auc:>8.3f}{f'{len(level)}/{len(rising)}':>12}"
        )

    print()
    print(f"best AUC: {best_auc:.3f}  (need >= {MIN_T1_T2_AUC:.2f})")
    if best_auc < MIN_T1_T2_AUC:
        print()
        print(
            "FAIL: on speech where both tones were produced correctly, the "
            "measured slope barely separates level from rising. The spread "
            "swamps the difference, so no threshold or classifier downstream "
            "can recover the distinction."
        )
        return 1
    print()
    print("PASS: level and rising tones are separable on correctly-produced speech.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
