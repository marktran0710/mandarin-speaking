"""Can our features identify which tone was spoken, at all?

The scorer currently reduces a syllable to a single slope and compares it to a
template. Measured on speech both raters and natives produced correctly, that
slope separates a level tone from a rising one at AUC 0.567 -- barely above
chance.

But Mandarin tone recognition is a long-solved problem: published systems
identify the four tones on native speech well above 90% accuracy. So the
information is in the signal, and the question is whether *our* feature
extraction destroys it.

This probe answers that directly. It trains a 4-way tone classifier on
syllables known to be correctly produced, using the same features the scorer
uses, and reports how well it recovers the tone that was actually spoken.

    high accuracy  -> the features are fine; the single-slope comparison was
                      the bottleneck, and a posterior-based score (GOP-style)
                      is the way forward
    low accuracy   -> the features themselves lose the tone, and no scoring
                      rule built on them can work

The expected-tone one-hot columns are removed before training. They encode the
answer, so leaving them in would produce a meaningless perfect score.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarking.ompal_corpus import load_utterances
from tone_scoring.features import FEATURE_NAMES
from tone_scoring.training import build_samples, load_fold_map

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "private-data" / "ompal"

# These columns are the label. Training on them would score ~100% and mean
# nothing.
LABEL_COLUMNS = {f"expected_tone_{tone}" for tone in (1, 2, 3, 4)}
KEEP_INDICES = [
    index for index, name in enumerate(FEATURE_NAMES) if name not in LABEL_COLUMNS
]


def analyzer_bundle(path: str):
    from praat_analyzer import (
        _intensity_contour_from_sound,
        _load_sound,
        _pitch_contour_from_sound,
    )

    sound = _load_sound(path)
    return _pitch_contour_from_sound(sound), _intensity_contour_from_sound(sound)


def main() -> None:
    warnings.filterwarnings("ignore")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aligner", default="energy")
    args = parser.parse_args()

    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    print("loading corpus and featurizing…")
    utterances = load_utterances(CORPUS_ROOT)
    samples, _ = build_samples(
        utterances, analyzer_bundle, load_fold_map(CORPUS_ROOT),
        aligner_name=args.aligner,
    )

    # Only syllables every rater judged correct: those are the ones whose
    # acoustic realisation genuinely matches the tone the text calls for, so
    # the written tone is a trustworthy label for what was spoken.
    usable = [
        sample
        for sample in samples
        if sample.expected_tone in (1, 2, 3, 4) and all(sample.rater_labels)
    ]
    if not usable:
        print("no correctly-produced syllables available")
        return

    matrix = np.asarray([s.features for s in usable], dtype=float)[:, KEEP_INDICES]
    labels = np.asarray([s.expected_tone for s in usable], dtype=int)
    groups = np.asarray([s.speaker_id for s in usable])

    print(f"  {len(usable)} correctly-produced syllables, "
          f"{len(set(groups))} speakers, {matrix.shape[1]} features "
          f"({len(LABEL_COLUMNS)} label columns removed)")
    print(f"  tone distribution: {dict(sorted(Counter(labels.tolist()).items()))}")

    # Speaker-disjoint folds, so accuracy cannot come from memorising a voice.
    splitter = GroupKFold(n_splits=5)
    predicted = np.zeros(len(labels), dtype=int)
    for train_index, test_index in splitter.split(matrix, labels, groups):
        model = HistGradientBoostingClassifier(
            max_depth=6, max_iter=300, learning_rate=0.08,
            l2_regularization=1.0, min_samples_leaf=20, random_state=0,
        )
        model.fit(matrix[train_index], labels[train_index])
        predicted[test_index] = model.predict(matrix[test_index])

    accuracy = float((predicted == labels).mean())
    majority = float(Counter(labels.tolist()).most_common(1)[0][1] / len(labels))

    print()
    print("=== 4-WAY TONE IDENTIFICATION (speaker-disjoint CV) ===")
    print(f"accuracy            : {accuracy * 100:.1f}%")
    print(f"chance (uniform)    : 25.0%")
    print(f"majority-class rate : {majority * 100:.1f}%")
    print(f"published on native : >90%")
    print()
    print("per tone (recall):")
    for tone in (1, 2, 3, 4):
        mask = labels == tone
        if mask.sum():
            print(f"  T{tone}: {float((predicted[mask] == tone).mean()) * 100:5.1f}%"
                  f"   (n={int(mask.sum())})")
    print()
    print("confusion, rows = spoken, cols = predicted:")
    print("        " + "".join(f"{f'T{c}':>7}" for c in (1, 2, 3, 4)))
    for tone in (1, 2, 3, 4):
        row = [int(((labels == tone) & (predicted == p)).sum()) for p in (1, 2, 3, 4)]
        print(f"  T{tone}   " + "".join(f"{v:>7}" for v in row))

    print()
    if accuracy >= 0.70:
        print("The features DO carry tone identity. The single-slope comparison was")
        print("the bottleneck, and a posterior-based score is the way forward.")
    elif accuracy >= 0.45:
        print("Partial signal: better than chance but far below what tone")
        print("recognition achieves. Features are lossy rather than empty.")
    else:
        print("The features do not carry tone identity. No scoring rule built on")
        print("them can work, and the fault is upstream of the scorer.")


if __name__ == "__main__":
    main()
